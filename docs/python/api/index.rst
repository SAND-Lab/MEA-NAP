API reference
==============

Auto-generated reference for the ``meanap`` package, built from the
docstrings in ``src/meanap/``. This covers the parts of the package meant to
be scripted against directly:

- ``meanap.params`` — the ``Params`` dataclass every pipeline step reads from.
- ``meanap.pipeline`` — the pipeline steps themselves (spike detection,
  firing rates/bursts, STTC, network metrics, the HTML report generator, ...).
- ``meanap.network_plot`` — loading a MEA-NAP output ``.mat`` file and
  rendering network plots (what powers the Network Viewer GUI tab).
- ``meanap.catnap`` — the calcium-imaging (CAT-NAP) scanner, loader, and
  denoising pipeline.

.. note::

   ``meanap.gui`` (the PyQt6 desktop app) is intentionally not included here
   — its classes are UI widgets, not a scripting API. See the
   :doc:`../gui-guide` for how to use the GUI itself.

.. autosummary::
   :toctree: generated
   :recursive:
   :caption: Package reference

   meanap.params
   meanap.network_plot
   meanap.pipeline
   meanap.catnap
