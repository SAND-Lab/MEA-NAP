"""Reader for Axion Biosystems ``.raw`` recordings.

Lets the pipeline run on Axion Maestro files directly, instead of first running
``Functions/convertRawToMat/rawConvertFunc.m`` to split a plate into one ``.mat``
per well. This is a port of the read path of Axion's bundled MATLAB toolbox
(``Functions/AxionFileLoader/``), covering just what the pipeline needs:
``AxisFile`` → ``RawVoltageData`` → ``LoadData`` → ``GetVoltageVector``.

An Axion ``.raw`` holds a whole *plate* — every well recorded at once — whereas
MEA-NAP treats one well as one recording. So a single file supplies many
recordings, addressed as ``<file stem>_<well>`` (e.g. ``Plate2_DIV75_A1``), the
same names ``rawConvertFunc.m`` gives the ``.mat`` files it writes. Existing
spreadsheets therefore keep working unchanged.

File layout, from the toolbox source:

* an 8-byte magic word ``AxionBio``, then a primary header holding 123 *entry
  records* (one uint64 each: 1 byte type + 7 bytes length);
* entries describe the plate's channel array and the block-vector metadata
  (sampling rate, voltage scale, where the samples live);
* when a page of entry records runs out, another 1024-byte page follows, again
  starting with the magic word;
* the sample region is plain interleaved int16: for each time point, one value
  per channel in the order given by the metadata's channel IDs. A voltage is
  ``sample * VoltageScale`` volts.

Scope: continuous ("combined") block-vector headers, which is what AxIS writes
for raw voltage recordings. Spike files and the legacy split
header/data entry pair are not handled — see :func:`read_axion_metadata`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np

MAGIC = b"AxionBio"
_PRIMARY_HEADER_MAX_ENTRIES = 123
_SUBHEADER_MAX_ENTRIES = 126
_EXPECTED_NOTES_LENGTH = 600

# EntryRecordID values
_ENTRY_TERMINATE = 0x00
_ENTRY_CHANNEL_ARRAY = 0x02
_ENTRY_BLOCK_VECTOR_HEADER = 0x03
_ENTRY_COMBINED_BLOCK_VECTOR_HEADER = 0x07

# BlockVectorDataType / BlockVectorSampleType values we support
_DATA_TYPE_NAMED_CONTINUOUS = 2
_SAMPLE_TYPE_SHORT = 0

_LENGTH_READ_TO_END = 0x00FFFFFFFFFFFFFF

_WELL_ROW_NAMES = "ABCDEFGH"


@dataclass(frozen=True)
class AxionChannel:
    """One electrode's position on the plate, plus its amplifier address."""

    well_row: int
    well_col: int
    elec_col: int
    elec_row: int
    achk: int          # amplifier ("artichoke") number
    index: int         # channel number within that amplifier

    @property
    def well(self) -> str:
        return f"{_WELL_ROW_NAMES[self.well_row - 1]}{self.well_col}"

    @property
    def meanap_channel(self) -> int:
        """Electrode ID in MEA-NAP's convention, ``column * 10 + row``.

        Matches ``rawConvertFunc.m``, and lines up with the ``Axion16`` /
        ``Axion64`` layouts in :mod:`meanap.pipeline.channel_layout`.
        """
        return self.elec_col * 10 + self.elec_row


@dataclass(frozen=True)
class AxionMetadata:
    """Everything needed to read samples out of an Axion ``.raw``."""

    path: Path
    sampling_frequency: float
    voltage_scale: float
    plate_type: int
    channels: tuple[AxionChannel, ...]        # plate-wide channel array
    data_columns: tuple[int, ...]             # column i of the data region is channels[data_columns[i]]
    data_start: int
    data_length: int

    @property
    def n_data_columns(self) -> int:
        return len(self.data_columns)

    @property
    def n_samples(self) -> int:
        return self.data_length // (2 * self.n_data_columns)

    @property
    def duration_s(self) -> float:
        return self.n_samples / self.sampling_frequency

    def wells(self) -> list[str]:
        """Well names present in the recording, in plate order (A1, A2, …)."""
        seen = {self.channels[c].well for c in self.data_columns}
        return sorted(seen, key=lambda w: (w[0], int(w[1:])))

    def columns_for_well(self, well: str) -> list[int]:
        """Data-region column indices belonging to ``well``, in electrode order.

        Ordered by ``(electrode row, electrode column)`` so the returned channel
        list matches what ``rawConvertFunc.m`` writes. MATLAB indexes its cell
        array as ``AllData{wellRow, wellCol, elecCol, elecRow}`` and flattens
        ``[AllData{j1,j2,:,:}]`` column-major, so the *column* dimension varies
        fastest: 11, 21, 31, 41, 12, 22, … — i.e. row is the outer key.
        """
        want = well.upper()
        cols = [c for c in self.data_columns if self.channels[c].well == want]
        cols.sort(key=lambda c: (self.channels[c].elec_row, self.channels[c].elec_col))
        return cols


class _Reader:
    """Little-endian binary cursor over an open file."""

    def __init__(self, fh):
        self.fh = fh

    def tell(self) -> int:
        return self.fh.tell()

    def seek(self, pos: int) -> None:
        self.fh.seek(pos)

    def skip(self, n: int) -> None:
        self.fh.seek(n, 1)

    def bytes(self, n: int) -> bytes:
        data = self.fh.read(n)
        if len(data) != n:
            raise ValueError(f"unexpected end of file (wanted {n} bytes, got {len(data)})")
        return data

    def scalar(self, dtype: str):
        return np.frombuffer(self.bytes(np.dtype(dtype).itemsize), dtype=dtype)[0]

    def array(self, dtype: str, count: int) -> np.ndarray:
        return np.frombuffer(self.bytes(np.dtype(dtype).itemsize * count), dtype=dtype)

    def u8(self) -> int:
        return int(self.scalar("<u1"))

    def u16(self) -> int:
        return int(self.scalar("<u2"))

    def u32(self) -> int:
        return int(self.scalar("<u4"))

    def i32(self) -> int:
        return int(self.scalar("<i4"))

    def i64(self) -> int:
        return int(self.scalar("<i8"))

    def f64(self) -> float:
        return float(self.scalar("<f8"))


def _entry_records(slots: np.ndarray) -> list[tuple[int, int]]:
    """Decode uint64 entry slots into ``(type, length)`` pairs.

    Each slot packs a 1-byte type in the top byte and a 7-byte length below it.
    An all-ones length marks "read to end of file"; only the final entry may use
    it, and it becomes ``-1`` here.
    """
    out = []
    for slot in slots.tolist():
        entry_type = (slot >> 56) & 0xFF
        length = slot & _LENGTH_READ_TO_END
        out.append((entry_type, -1 if length == _LENGTH_READ_TO_END else length))
    return out


def _read_channel_array(r: _Reader) -> tuple[int, list[AxionChannel]]:
    """Parse a ChannelArray entry: plate type, then one 8-byte record each."""
    plate_type = r.u32()
    n_channels = r.u32()
    channels = []
    for _ in range(n_channels):
        well_col, well_row, elec_col, elec_row, achk, index = r.array("<u1", 6).tolist()
        r.u16()  # AuxData, unused
        channels.append(AxionChannel(
            well_row=well_row, well_col=well_col,
            elec_col=elec_col, elec_row=elec_row,
            achk=achk, index=index,
        ))
    return plate_type, channels


def _read_combined_block_vector_header(r: _Reader) -> dict:
    """Parse a CombinedBlockVectorHeader entry (and its continuous extension)."""
    version_major = r.u16()
    version_minor = r.u16()
    data_type = r.u16()
    sample_type = r.u16()
    sampling_frequency = r.f64()
    voltage_scale = r.f64()
    n_channels_per_block = r.u32()
    n_datasets_per_block = r.u32()
    r.u32()                      # NumSamplesPerBlock
    r.u32()                      # VectorHeaderSize
    r.u32()                      # BlockHeaderSize
    r.skip(4 * 14)               # four DateTimes, 7 x uint16 each
    if version_major > 1 or version_minor >= 1:
        r.f64()                  # Duration
    r.skip(r.i32())              # Name
    r.skip(r.i32())              # Description
    data_start = r.i64()
    data_length = r.i64()
    r.u32()                      # CRC over the above

    # The continuous extension follows immediately: one channel ID per data
    # column, then the data set names. Channel IDs give the *column order* of
    # the sample region, which need not match the plate's channel array order.
    channel_ids = [r.u16() for _ in range(n_channels_per_block)]
    for _ in range(n_datasets_per_block):
        r.skip(r.i32())          # data set name
    r.u32()                      # CRC over the extension

    return {
        "data_type": data_type,
        "sample_type": sample_type,
        "sampling_frequency": sampling_frequency,
        "voltage_scale": voltage_scale,
        "channel_ids": channel_ids,
        "data_start": data_start,
        "data_length": data_length,
    }


def _walk_entries(r: _Reader, name: str):
    """Yield ``(entry type, start offset, length)`` for every header entry.

    Port of the entry loop of ``AxisFile.m``. The caller may read from
    ``start`` when it is handed an entry; the walk seeks past the entry itself
    before moving on. A "read to end" entry (length ``-1``) is always the last.
    """
    if r.bytes(len(MAGIC)) != MAGIC:
        raise ValueError(f"{name}: not an Axion file (missing 'AxionBio' magic word)")

    r.u16()                              # PrimaryDataType
    version_major = r.u16()
    version_minor = r.u16()
    r.i64()                              # legacy notes start
    notes_length = r.u32()
    if version_major != 1:
        raise ValueError(
            f"{name}: Axis file header version {version_major}.{version_minor} "
            "is not supported (only version 1.x); convert this file with the "
            "MATLAB File Conversion tab instead."
        )
    if notes_length != _EXPECTED_NOTES_LENGTH:
        raise ValueError(f"{name}: bad legacy notes length field ({notes_length})")

    entries_start = r.i64()
    records = _entry_records(r.array("<u8", _PRIMARY_HEADER_MAX_ENTRIES))

    r.seek(entries_start)
    while True:
        for entry_type, length in records:
            if entry_type == _ENTRY_TERMINATE:
                return
            start = r.tell()
            yield entry_type, start, length
            if length < 0:
                # "Read to end" — only ever the final entry, and only for the
                # sample region, which is located from its header instead.
                return
            r.seek(start + length)

        # Next page of entry records: magic, 126 slots, CRC, 4 reserved bytes.
        if r.bytes(len(MAGIC)) != MAGIC:
            raise ValueError(f"{name}: bad sub-header magic word")
        records = _entry_records(r.array("<u8", _SUBHEADER_MAX_ENTRIES))
        r.skip(8)


def read_axion_metadata(path: str | Path) -> AxionMetadata:
    """Read an Axion ``.raw`` header without touching the sample data.

    Raises ``ValueError`` if the file isn't an Axion recording, or if it uses a
    variant this reader doesn't cover (spike data, or the pre-"combined" split
    header/data entries) — in which case convert it with the MATLAB GUI's File
    Conversion tab as before.
    """
    path = Path(path)
    plate_type: int | None = None
    channels: list[AxionChannel] | None = None
    block: dict | None = None

    with open(path, "rb") as fh:
        r = _Reader(fh)
        for entry_type, _start, _length in _walk_entries(r, path.name):
            if entry_type == _ENTRY_CHANNEL_ARRAY:
                plate_type, channels = _read_channel_array(r)
            elif entry_type == _ENTRY_COMBINED_BLOCK_VECTOR_HEADER:
                block = _read_combined_block_vector_header(r)
            elif entry_type == _ENTRY_BLOCK_VECTOR_HEADER:
                raise ValueError(
                    f"{path.name}: this file uses the older split block-vector "
                    "header/data layout, which this reader doesn't cover. Convert it "
                    "with the MATLAB File Conversion tab instead."
                )

    if channels is None:
        raise ValueError(f"{path.name}: no channel array found in header")
    if block is None:
        raise ValueError(
            f"{path.name}: no continuous voltage data found — this may be a spike "
            "(.spk) file rather than a raw voltage recording."
        )
    if block["data_type"] != _DATA_TYPE_NAMED_CONTINUOUS:
        raise ValueError(
            f"{path.name}: unsupported block vector data type {block['data_type']} "
            "(expected continuous raw voltage data)"
        )
    if block["sample_type"] != _SAMPLE_TYPE_SHORT:
        raise ValueError(
            f"{path.name}: unsupported sample type {block['sample_type']} "
            "(only 16-bit samples are handled)"
        )

    by_address = {(c.achk, c.index): i for i, c in enumerate(channels)}
    data_columns = []
    for channel_id in block["channel_ids"]:
        key = ((channel_id >> 8) & 0xFF, channel_id & 0xFF)
        if key not in by_address:
            raise ValueError(f"{path.name}: data references unknown channel {key}")
        data_columns.append(by_address[key])

    return AxionMetadata(
        path=path,
        sampling_frequency=block["sampling_frequency"],
        voltage_scale=block["voltage_scale"],
        plate_type=plate_type if plate_type is not None else 0,
        channels=tuple(channels),
        data_columns=tuple(data_columns),
        data_start=block["data_start"],
        data_length=block["data_length"],
    )


def is_axion_raw(path: str | Path) -> bool:
    """True if ``path`` starts with the Axion magic word."""
    try:
        with open(path, "rb") as fh:
            return fh.read(len(MAGIC)) == MAGIC
    except OSError:
        return False


def split_well_suffix(filename: str) -> tuple[str, str] | None:
    """Split ``"Plate2_DIV75_A1"`` into ``("Plate2_DIV75", "A1")``, else ``None``."""
    match = re.match(r"^(.*)_([A-H])(\d{1,2})$", filename)
    if match is None:
        return None
    return match.group(1), f"{match.group(2)}{match.group(3)}"


def load_axion_well(
    path: str | Path,
    well: str,
    metadata: AxionMetadata | None = None,
) -> tuple[np.ndarray, np.ndarray, float]:
    """Load one well from an Axion ``.raw``.

    Returns ``(dat, channels, fs)`` matching what ``rawConvertFunc.m`` saves for
    that well: ``dat`` is (n_samples, n_electrodes) in **volts**, and
    ``channels`` are ``column * 10 + row`` electrode IDs.

    Only the requested well's electrodes are converted, so memory scales with
    one well rather than the whole plate — a 24-well 5-minute recording needs
    ~240 MB here instead of the ~11 GB MATLAB's ``LoadData`` uses for the plate.
    """
    meta = metadata if metadata is not None else read_axion_metadata(path)
    cols = meta.columns_for_well(well)
    if not cols:
        raise ValueError(
            f"{Path(path).name}: well {well!r} not found "
            f"(available: {', '.join(meta.wells())})"
        )

    n_samples = meta.n_samples
    n_cols = meta.n_data_columns
    col_index = np.array(cols, dtype=np.intp)
    dat = np.empty((n_samples, len(cols)), dtype=np.float32)

    # Read whole time blocks: a row spans every channel on the plate, so seeking
    # per electrode would re-read the same disk pages once per electrode.
    block = max(1, (256 << 20) // (n_cols * 2))
    with open(path, "rb") as fh:
        for start in range(0, n_samples, block):
            stop = min(start + block, n_samples)
            fh.seek(meta.data_start + start * n_cols * 2)
            raw = np.frombuffer(
                fh.read((stop - start) * n_cols * 2), dtype="<i2",
            ).reshape(stop - start, n_cols)
            dat[start:stop, :] = raw[:, col_index].astype(np.float64) * meta.voltage_scale

    channels = np.array([meta.channels[c].meanap_channel for c in cols], dtype=int)
    return dat, channels, float(meta.sampling_frequency)


# ── Stimulation events (tags) ─────────────────────────────────────────────────
#
# Port of the stimulation part of the toolbox's tag handling: ``TagEntry.m``,
# ``Tag.m`` (head revision), ``EventTag.m``, ``StimulationEvent.m`` (+ its
# ``Link``), ``StimulationWaveform.m`` / ``StimulationEventData.m``,
# ``StimulationChannels.m`` / ``ChannelMapping.m`` and ``StimulationLeds.m`` /
# ``LedPosition.m``. AxIS writes one tag per stimulation it delivers; each
# names a waveform tag (whose blocks say which channel groups each block
# drives) and a channel-group tag (whose groups list the electrodes). A tag is
# revised by writing a new entry with the same GUID and a higher revision.

_ENTRY_TAG = 0x06

# TagType values
_TAG_STIM_EVENT = 5
_TAG_STIM_CHANNEL_GROUP = 6
_TAG_STIM_WAVEFORM = 7
_TAG_STIM_LED_GROUP = 9

#: Type (uint16) + CreationDate (7 x uint16) + GUID (16) + revision (uint32):
#: the head of every tag entry, before its type's own fields.
_TAG_BASE_SIZE = 2 + 14 + 16 + 4
#: Smallest channel / LED group: ID, plate type and count (uint32 each), plus
#: one 8-byte mapping (``MinArraySize`` in the toolbox).
_MIN_GROUP_SIZE = 20
_ZERO_GUID = "00000000-0000-0000-0000-000000000000"


def _guid(raw: bytes) -> str:
    """A Microsoft-encoded GUID as text, as ``parseGuid.m`` writes it."""
    import uuid

    return str(uuid.UUID(bytes_le=raw))


def _well_name(well_row: int, well_col: int) -> str:
    if not 1 <= well_row <= len(_WELL_ROW_NAMES):
        return f"R{well_row}C{well_col}"
    return f"{_WELL_ROW_NAMES[well_row - 1]}{well_col}"


def _read_string(r: _Reader) -> str:
    """``freadstring.m``: an int32 byte count, then that many bytes of text.

    UTF-8, as the toolbox reads it — except that AxIS writes a waveform's
    stimulation program as UTF-16 XML (``encoding="utf-16"``), which the
    toolbox's UTF-8 decode turns to mojibake; that is recognised by its
    byte-order mark or interleaved zero bytes.
    """
    n = r.i32()
    if n <= 0:
        return ""
    raw = r.bytes(n)
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff") or (len(raw) >= 4 and raw[1:4:2] == b"\0\0"):
        return raw.decode("utf-16", errors="replace")
    return raw.decode("utf-8", errors="replace")


#: A channel array a stimulation program arms, in its ``achkset`` operations.
_PROGRAM_CHANNEL_ARRAY = re.compile(r'channelarrayid\s*=\s*"(\d+)"')


@dataclass(frozen=True)
class AxionStimEvent:
    """One stimulation AxIS delivered, as recorded in the ``.raw``.

    ``electrodes`` are the ``(well, electrode ID)`` pairs it drove, the
    electrode ID being ``column * 10 + row`` (as :attr:`AxionChannel.meanap_channel`).
    Empty when the event names no electrode: an LED (optical) stimulation,
    whose lit wells are in ``led_wells`` instead.
    """

    time_s: float
    block_id: int
    electrodes: tuple[tuple[str, int], ...] = ()
    led_wells: tuple[str, ...] = ()


@dataclass(frozen=True)
class AxionStimEvents:
    """The stimulation events of an Axion ``.raw``.

    ``events`` are the linked events, sorted by time. ``unlinked_times`` are the
    times of events whose waveform or channel tags are missing (all-zero GUIDs,
    or GUIDs, blocks or groups the file doesn't hold): AxisFile's
    ``UnlinkedStimulationEvents``, which it leaves out.
    """

    path: Path
    events: tuple[AxionStimEvent, ...]
    unlinked_times: tuple[float, ...] = ()

    @property
    def n_unlinked(self) -> int:
        return len(self.unlinked_times)

    @property
    def times(self) -> np.ndarray:
        """Every linked event's time (s), sorted."""
        return np.array([e.time_s for e in self.events], dtype=float)

    def stimulated_wells(self) -> list[str]:
        """Wells any event drove an electrode in, in plate order."""
        wells = {w for e in self.events for w, _ in e.electrodes}
        return sorted(wells, key=_well_sort_key)

    def names_electrodes(self) -> bool:
        """Whether any event records the electrode it was delivered to."""
        return any(e.electrodes for e in self.events)


def _well_sort_key(well: str):
    match = re.match(r"^([A-Z])(\d+)$", well)
    return (match.group(1), int(match.group(2))) if match else (well, 0)


@dataclass
class _TagHead:
    tag_type: int
    guid: str
    revision: int
    start: int
    length: int


def _read_tag_head(r: _Reader, start: int, length: int) -> _TagHead:
    tag_type = r.u16()
    r.skip(14)                                   # CreationDate
    guid = _guid(r.bytes(16))
    revision = r.u32()
    return _TagHead(tag_type, guid, revision, start, length)


def _read_stim_event(r: _Reader, head: _TagHead) -> dict | None:
    """``EventTag`` + ``StimulationEvent``: time, its waveform / channel tags, block."""
    r.seek(head.start + _TAG_BASE_SIZE)
    fs = r.f64()
    sample = r.i64()
    r.i64()                                      # EventDurationSamples
    if r.u16() != 0:                             # version
        return {"time_s": sample / fs if fs else float("nan"), "waveform": _ZERO_GUID,
                "channels": _ZERO_GUID, "block_id": 0xFFFF}
    r.u16()                                      # reserved
    waveform = _guid(r.bytes(16))
    channels = _guid(r.bytes(16))
    block_id = r.u16()                           # "EventData": the waveform block's ID
    r.u16()                                      # SequenceNumber
    return {"time_s": sample / fs, "waveform": waveform, "channels": channels,
            "block_id": block_id}


@dataclass
class _Waveform:
    #: Each block's ID → the channel-group IDs it lists (zeros, placeholders, dropped).
    blocks: dict[int, tuple[int, ...]]
    #: The channel arrays the waveform's stimulation program ("MicroOps") arms.
    program_groups: tuple[int, ...] = ()


def _read_stim_waveform(r: _Reader, head: _TagHead) -> _Waveform | None:
    """``StimulationWaveform``: its blocks, and the channel arrays its program arms."""
    r.seek(head.start + _TAG_BASE_SIZE)
    if r.u16() != 0:
        return None
    blocks: dict[int, tuple[int, ...]] = {}
    for _ in range(r.u16()):
        block_id = r.u16()
        r.u16()                                  # type, unused
        r.f64()                                  # StimDuration
        r.f64()                                  # ArtifactEliminationDuration
        groups = tuple(g for g in r.array("<u2", 2).tolist() if g != 0)   # 0 = placeholder
        _read_string(r)                          # description
        blocks.setdefault(block_id, groups)      # first match wins, as in Link
    program = _read_string(r)                    # MicroOps
    armed = tuple(dict.fromkeys(int(g) for g in _PROGRAM_CHANNEL_ARRAY.findall(program)))
    return _Waveform(blocks, armed)


def _read_groups(r: _Reader, head: _TagHead, record: int, parse,
                 counted: bool = False) -> dict[int, list] | None:
    """The groups of a ``StimulationChannels`` / ``StimulationLeds`` tag: ID → items.

    Channel groups are read while a whole group still fits (``MinArraySize``).
    An LED tag says how many groups it holds (``counted``), and exactly that
    many are read: a one-LED group is 16 bytes, under the 20 the toolbox's
    loop needs, so there it would stop early and reject the tag.
    """
    r.seek(head.start + _TAG_BASE_SIZE)
    if r.u16() != 0:
        return None
    expected = r.u16()                           # reserved (channels) / group count (LEDs)
    end = head.start + head.length
    groups: dict[int, list] = {}
    if counted:
        for _ in range(expected):
            group_id = r.u32()
            r.u32()                              # plate type
            n = r.u32()
            groups.setdefault(group_id, [parse(r.array("<u1", record)) for _ in range(n)])
        return groups
    while end - r.tell() >= _MIN_GROUP_SIZE:
        group_id = r.u32()
        r.u32()                                  # plate type
        n = r.u32()
        items = [parse(r.array("<u1", record)) for _ in range(n)]
        groups.setdefault(group_id, items)
    return groups


def _channel_mapping(b: np.ndarray) -> tuple[str, int]:
    """``ChannelMapping``: well column, well row, electrode column, electrode row, …"""
    well_col, well_row, elec_col, elec_row = (int(v) for v in b[:4])
    return _well_name(well_row, well_col), elec_col * 10 + elec_row


def _led_position(b: np.ndarray) -> str:
    """``LedPosition``: well column, well row, colour (uint16)."""
    return _well_name(int(b[1]), int(b[0]))


def read_axion_stim_events(path: str | Path) -> AxionStimEvents:
    """The stimulation events recorded in an Axion ``.raw``.

    Port of what ``AxisFile`` does with a file's tags: collect every tag entry,
    keep each GUID's highest revision, decode the stimulation events and the
    waveform, channel-group and LED-group tags they refer to, and link them as
    ``StimulationEvent.Link`` does — event → its waveform's block with the
    event's block ID → that block's (up to two) channel groups → their
    electrodes. An event's time is ``EventTimeSample / SamplingFrequency``.

    Events that can't be linked are counted in ``unlinked_times`` rather than
    returned. The voltage data is never read, so this is quick on any file,
    and works on files whose voltage layout :func:`read_axion_metadata` refuses.
    """
    path = Path(path)
    heads: dict[str, _TagHead] = {}
    events: list[AxionStimEvent] = []
    unlinked: list[float] = []

    with open(path, "rb") as fh:
        r = _Reader(fh)
        for entry_type, start, length in _walk_entries(r, path.name):
            if entry_type != _ENTRY_TAG or length < _TAG_BASE_SIZE:
                continue
            head = _read_tag_head(r, start, length)
            if head.guid not in heads or head.revision > heads[head.guid].revision:
                heads[head.guid] = head

        def decode(kind: int, read):
            out = {}
            for guid, head in heads.items():
                if head.tag_type != kind:
                    continue
                try:
                    value = read(r, head)
                except ValueError:               # a tag cut short: treat as missing
                    value = None
                if value is not None:
                    out[guid] = value
            return out

        raw_events = decode(_TAG_STIM_EVENT, _read_stim_event)
        waveforms = decode(_TAG_STIM_WAVEFORM, _read_stim_waveform)
        channel_groups = decode(_TAG_STIM_CHANNEL_GROUP,
                                lambda r_, h: _read_groups(r_, h, 8, _channel_mapping))
        led_groups = decode(_TAG_STIM_LED_GROUP,
                            lambda r_, h: _read_groups(r_, h, 4, _led_position, counted=True))

    for ev in raw_events.values():
        linked = _link(ev, waveforms, channel_groups, led_groups)
        if linked is None:
            unlinked.append(float(ev["time_s"]))
        else:
            events.append(linked)

    events.sort(key=lambda e: e.time_s)
    return AxionStimEvents(path=path, events=tuple(events),
                           unlinked_times=tuple(sorted(unlinked)))


def _link(ev: dict, waveforms: dict, channel_groups: dict, led_groups: dict
          ) -> AxionStimEvent | None:
    """``StimulationEvent.Link``; ``None`` when a tag it needs can't be found."""
    if ev["waveform"] == _ZERO_GUID or ev["channels"] == _ZERO_GUID:
        return None
    waveform = waveforms.get(ev["waveform"])
    if waveform is None:
        return None
    time_s, block_id = float(ev["time_s"]), int(ev["block_id"])
    group_ids = waveform.blocks.get(block_id)

    if ev["channels"] in channel_groups:
        groups = channel_groups[ev["channels"]]
        if group_ids is None:
            return None
        if not group_ids:
            # The block lists no group (both slots placeholders), as AxIS writes
            # some files: the stimulation program says which channel arrays it
            # drove instead (``<achkset channelarrayid="1" …/>``). The
            # toolbox's Link stops here and finds no electrode.
            group_ids = tuple(g for g in waveform.program_groups if g in groups)
        if any(g not in groups for g in group_ids):
            return None
        pairs = [p for g in group_ids for p in groups[g]]
        return AxionStimEvent(time_s, block_id, tuple(dict.fromkeys(pairs)))

    if ev["channels"] in led_groups:
        groups = led_groups[ev["channels"]]
        # With no matching block, Link takes every LED group of the tag.
        chosen = (list(groups.values()) if group_ids is None
                  else [groups[g] for g in group_ids if g in groups])
        wells = [w for group in chosen for w in group]
        return AxionStimEvent(time_s, block_id, (), tuple(dict.fromkeys(wells)))
    return None
