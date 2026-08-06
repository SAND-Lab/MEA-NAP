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
        if r.bytes(len(MAGIC)) != MAGIC:
            raise ValueError(f"{path.name}: not an Axion file (missing 'AxionBio' magic word)")

        r.u16()                              # PrimaryDataType
        version_major = r.u16()
        version_minor = r.u16()
        r.i64()                              # legacy notes start
        notes_length = r.u32()
        if version_major != 1:
            raise ValueError(
                f"{path.name}: Axis file header version {version_major}.{version_minor} "
                "is not supported (only version 1.x); convert this file with the "
                "MATLAB File Conversion tab instead."
            )
        if notes_length != _EXPECTED_NOTES_LENGTH:
            raise ValueError(f"{path.name}: bad legacy notes length field ({notes_length})")

        entries_start = r.i64()
        records = _entry_records(r.array("<u8", _PRIMARY_HEADER_MAX_ENTRIES))

        r.seek(entries_start)
        terminated = False
        while not terminated:
            for entry_type, length in records:
                if entry_type == _ENTRY_TERMINATE:
                    terminated = True
                    break

                start = r.tell()
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

                if length < 0:
                    # "Read to end" — only ever the final entry, and only for the
                    # sample region, which we locate from the header instead.
                    terminated = True
                    break
                r.seek(start + length)

            if terminated:
                break

            # Next page of entry records: magic, 126 slots, CRC, 4 reserved bytes.
            if r.bytes(len(MAGIC)) != MAGIC:
                raise ValueError(f"{path.name}: bad sub-header magic word")
            records = _entry_records(r.array("<u8", _SUBHEADER_MAX_ENTRIES))
            r.skip(8)

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
