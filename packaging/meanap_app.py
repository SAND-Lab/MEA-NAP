"""Entry point of the packaged MEA-NAP app (PyInstaller builds this file).

One executable does several jobs, picked by its first argument:

* nothing (a double-click) — the GUI, exactly as ``meanap-gui``;
* ``--smoke-test`` — :mod:`meanap.app_smoke`, the build's self-check;
* ``--run-module NAME ...`` — run a module as ``python -m NAME ...`` would. The
  pipeline starts some children that way (:func:`meanap.frozen.python_command`),
  and a frozen app has no ``python`` to start them with;
* the worker processes ``multiprocessing`` spawns, which
  ``freeze_support`` recognises and runs before anything else.
"""

import multiprocessing
import runpy
import sys


def main() -> None:
    from meanap import frozen

    # Before freeze_support, so spawned workers also have somewhere to print
    # on a console-less Windows build.
    frozen.prepare_runtime()
    multiprocessing.freeze_support()

    args = sys.argv[1:]
    if args[:1] == [frozen.RUN_MODULE_FLAG] and len(args) >= 2:
        sys.argv = [args[1], *args[2:]]
        runpy.run_module(args[1], run_name="__main__", alter_sys=True)
        return
    if args[:1] == ["--smoke-test"]:
        from meanap.app_smoke import main as smoke

        sys.exit(smoke())

    from meanap.gui.app import main as gui

    gui()


if __name__ == "__main__":
    main()
