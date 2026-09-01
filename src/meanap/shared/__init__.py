"""Running one analysis across several computers through a shared folder.

Most of a run is per-recording work that nothing else depends on — spike
detection, thresholding, the null models — and most people have more than one
computer. A *shared run* splits the recordings between the machines you have,
lets each work through its share, and pools the results on one of them, the
**main computer**, into an ordinary output folder.

The machines never talk to each other directly. They share a folder — a
Dropbox, OneDrive or Google Drive folder, a network drive, a USB stick moved by
hand — and everything goes through files in it: the run's description, who has
joined, how far each has got, and each machine's results. That is what makes
it work "out of the box": nothing to open in a firewall, no addresses to type,
and a machine that goes to sleep picks up where it stopped.

* :mod:`meanap.shared.workspace` — the folder's layout and the records in it.
* :mod:`meanap.shared.benchmark` — a short timing run, so recordings can be
  split in proportion to how fast each machine actually is.
* :mod:`meanap.shared.merge` — pooling every machine's results into one output
  folder, after which a *continued* run over the full spreadsheet redoes only
  what is computed across the batch (see ``docs/python/changing-a-batch.md``).
* :mod:`meanap.shared.roles` — what the main computer and a helper each do,
  start to finish.
* :mod:`meanap.shared.cli` — ``meanap-shared``, for joining from a terminal.
"""

from meanap.shared.workspace import (
    WORKSPACE_SUFFIX, MachineRecord, ProgressRecord, SharedRun, Workspace,
    create_workspace, open_workspace, split_recordings,
)

__all__ = [
    "WORKSPACE_SUFFIX", "MachineRecord", "ProgressRecord", "SharedRun",
    "Workspace", "create_workspace", "open_workspace", "split_recordings",
]
