"""Reading raw data that isn't on this machine.

The pipeline consumes raw recordings through a tiny read-only protocol
(:mod:`meanap.remote.base`), so the same code path serves a local directory and
a remote source. :mod:`meanap.remote.cache` bounds how much of a remote dataset
is resident at once, which is what allows a batch larger than the local disk.
"""

from meanap.remote.base import RemoteEntry, RemoteStore, store_id_for
from meanap.remote.cache import CacheFull, FileCache, resolve_budget
from meanap.remote.dropbox_link import (
    DropboxInterfaceChanged, DropboxLinkStore, parse_share_url,
)
from meanap.remote.local import LocalStore
from meanap.remote.preflight import PreflightReport, run_preflight, find_spreadsheet
from meanap.remote.source import RecordingSource

__all__ = [
    "RemoteEntry", "RemoteStore", "store_id_for",
    "FileCache", "CacheFull", "resolve_budget",
    "LocalStore",
    "DropboxLinkStore", "DropboxInterfaceChanged", "parse_share_url",
    "open_store",
    "PreflightReport", "run_preflight", "find_spreadsheet",
    "RecordingSource",
]


def open_store(params) -> "RemoteStore":
    """The store a run reads raw data from.

    ``Params.raw_data`` doubles as the source: a Dropbox folder share link when
    it looks like a URL, a local directory otherwise. One field rather than two
    means there is no way to set them inconsistently, and nothing else in the
    pipeline has to branch on where the data lives.
    """
    from meanap.params import is_remote_url

    if is_remote_url(params.raw_data):
        return DropboxLinkStore(params.raw_data)
    return LocalStore(params.raw_data)
