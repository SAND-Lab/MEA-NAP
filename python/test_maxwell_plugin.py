"""Getting MaxWell's HDF5 decompression plugin (meanap.pipeline.maxwell), offline.

Nothing here touches the network: the download is replaced by a fake that
returns a library's bytes, or an error page.
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent))

from meanap.pipeline import maxwell  # noqa: E402


@pytest.mark.parametrize("system, machine, tail", [
    ("Linux", "x86_64", "Linux%2Flibcompression.so&dl=1"),
    ("Darwin", "arm64", "Mac_arm64%2Flibcompression.dylib&dl=1"),
    ("Darwin", "x86_64", "Mac_x86_64%2Flibcompression.dylib&dl=1"),
    ("Windows", "AMD64", "Windows%2Fcompression.dll&dl=1"),
])
def test_each_platform_gets_maxwells_own_download(system, machine, tail):
    url = maxwell.plugin_download_url(system, machine)
    assert url.startswith("https://share.mxwbio.com/") and url.endswith(tail)


def test_no_download_where_maxwell_publish_none():
    assert maxwell.plugin_download_url("Linux", "aarch64") is None


def _fake(data: bytes):
    return lambda url: io.BytesIO(data)


def test_install_saves_a_library_and_refuses_an_error_page(tmp_path, monkeypatch):
    import h5py

    monkeypatch.setattr(h5py.h5pl, "prepend", lambda p: None)
    monkeypatch.setattr(h5py.h5z, "filter_avail", lambda fid: True)
    monkeypatch.setattr(maxwell, "plugin_download_url", lambda: "https://example.invalid/lib")
    lib = b"\x7fELF" + bytes(2000)
    path = maxwell.install_maxwell_plugin(tmp_path, opener=_fake(lib))
    assert path.parent == tmp_path and path.read_bytes() == lib
    assert not list(tmp_path.glob("*.part"))

    with pytest.raises(OSError, match="did not send a library"):
        maxwell.install_maxwell_plugin(tmp_path, opener=_fake(b"<html>moved</html>"))
    assert path.read_bytes() == lib                 # the good copy is untouched


def test_install_says_so_when_hdf5_will_not_load_it(tmp_path, monkeypatch):
    import h5py

    monkeypatch.setattr(h5py.h5pl, "prepend", lambda p: None)
    monkeypatch.setattr(h5py.h5z, "filter_avail", lambda fid: False)
    monkeypatch.setattr(maxwell, "plugin_download_url", lambda: "https://example.invalid/lib")
    with pytest.raises(OSError, match="does not load it"):
        maxwell.install_maxwell_plugin(tmp_path, opener=_fake(b"\x7fELF" + bytes(10)))


def test_download_failure_says_where_to_get_it_by_hand(tmp_path, monkeypatch):
    monkeypatch.setattr(maxwell, "plugin_download_url", lambda: "https://example.invalid/lib")

    def offline(url):
        raise OSError("no network")
    with pytest.raises(OSError, match="by hand from https://example.invalid/lib"):
        maxwell.install_maxwell_plugin(tmp_path, opener=offline)


def test_folder_probe_finds_only_filter_401_maxwell_files(tmp_path, monkeypatch):
    import sorted_import_fixture as fx

    n = int(fx.DURATION_S * fx.FS)
    sub = tmp_path / "plate"
    sub.mkdir()
    fx.write_maxwell_raw(sub / "a.raw.h5", voltage=np.full((len(fx.CHANNELS), n), 512, np.uint16),
                         ttl=False)
    assert not maxwell.folder_has_compressed_maxwell(tmp_path)          # gzip, not 401
    monkeypatch.setattr(maxwell, "_uses_filter", lambda dset, fid: fid == maxwell.MAXWELL_FILTER_ID)
    assert maxwell.folder_has_compressed_maxwell(tmp_path)
    assert not maxwell.folder_has_compressed_maxwell(tmp_path / "missing")


def test_cli_check_reports_and_exits_1_when_missing(monkeypatch, capsys):
    from meanap import cli

    monkeypatch.setattr(maxwell, "maxwell_plugin_available", lambda: False)
    assert cli.main(["maxwell-plugin", "--check"]) == cli.EXIT_FAILED
    monkeypatch.setattr(maxwell, "maxwell_plugin_available", lambda: True)
    assert cli.main(["maxwell-plugin", "--check"]) == cli.EXIT_OK


_APP = []      # the QApplication must outlive every window, or Qt aborts


def _window(monkeypatch):
    import os
    import tempfile

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtCore import QSettings
    from PyQt6.QtWidgets import QApplication

    # Never the user's own settings.
    settings = tempfile.mkdtemp(prefix="meanap-settings-")
    for fmt in (QSettings.Format.NativeFormat, QSettings.Format.IniFormat):
        QSettings.setPath(fmt, QSettings.Scope.UserScope, settings)
    if not _APP:
        _APP.append(QApplication.instance() or QApplication([]))
    import meanap.gui.main_window as mw

    return mw, mw.MainWindow("meanap")


def test_run_offers_the_decoder_only_when_maxwell_voltage_needs_it(monkeypatch, tmp_path):
    from meanap.params import Params

    mw, window = _window(monkeypatch)
    asked, installed = [], []
    monkeypatch.setattr(mw, "ask_yes_no", lambda *a: asked.append(a[1]) or True)
    monkeypatch.setattr(maxwell, "install_maxwell_plugin",
                        lambda: installed.append(1) or tmp_path / "lib.so")
    monkeypatch.setattr(maxwell, "plugin_download_url", lambda: "https://example.invalid")
    monkeypatch.setattr(maxwell, "maxwell_plugin_available", lambda: False)
    monkeypatch.setattr(maxwell, "folder_has_compressed_maxwell", lambda f: True)

    detect = Params(raw_data=str(tmp_path), spike_source="detect")
    window._offer_maxwell_plugin(detect)
    assert asked == ["MaxWell decoder needed"] and installed == [1]

    # An import that will not read the voltage, a later start step, or no
    # MaxWell files: nothing to ask.
    window._offer_maxwell_plugin(Params(raw_data=str(tmp_path), spike_source="import",
                                        signal_quality_check=False))
    window._offer_maxwell_plugin(Params(raw_data=str(tmp_path), start_analysis_step=2))
    monkeypatch.setattr(maxwell, "folder_has_compressed_maxwell", lambda f: False)
    window._offer_maxwell_plugin(detect)
    assert len(asked) == 1

    # Saying no runs anyway, without downloading.
    monkeypatch.setattr(maxwell, "folder_has_compressed_maxwell", lambda f: True)
    monkeypatch.setattr(mw, "ask_yes_no", lambda *a: False)
    window._offer_maxwell_plugin(detect)
    assert installed == [1]
    window.close()
