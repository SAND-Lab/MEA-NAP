.. _python-index:

MEA-NAP for Python
====================

MEA-NAP's analysis pipeline — spike detection, neuronal activity, functional
connectivity, and network topology — is being ported from MATLAB to Python,
living alongside the original MATLAB codebase in the same repository. It ships
as an installable package (``meanap``) with a desktop GUI, a Python API you can
script against directly, and a self-contained HTML report viewer for browsing
results.

.. tip::

   New here? Start with :doc:`installation`, then :doc:`quickstart` — from a
   fresh clone to a rendered network plot in about five minutes, using the
   bundled example dataset.

.. grid:: 2
   :gutter: 3
   :margin: 0

   .. grid-item-card:: 🚀 Installation
      :link: installation
      :link-type: doc

      Install with ``uv`` and launch the ``meanap-gui`` desktop app.

   .. grid-item-card:: ⚡ Quickstart
      :link: quickstart
      :link-type: doc

      Run the bundled example dataset end-to-end and open the HTML report.

   .. grid-item-card:: 🖥️ GUI guide
      :link: gui-guide
      :link-type: doc

      Every tab in the desktop app — Paths, Recording, Spike detection,
      Connectivity, Pipeline — field by field.

   .. grid-item-card:: 🔬 CAT-NAP (calcium imaging)
      :link: catnap
      :link-type: doc

      Analyze suite2p calcium-imaging recordings: denoising, peak detection,
      trace preview.

   .. grid-item-card:: 🕸️ Network Viewer
      :link: network-viewer
      :link-type: doc

      Interactively explore functional connectivity from a completed run,
      with cell-type overlays.

   .. grid-item-card:: 📓 Notebook tutorial
      :link: notebooks/network-plotting-tutorial
      :link-type: doc

      Load a real MEA-NAP output file and drive the plotting API directly
      from Python — runnable, with real output baked in.

   .. grid-item-card:: 📊 Output report
      :link: output-report
      :link-type: doc

      The self-contained, deep-linkable ``report.html`` viewer generated
      after every run.

   .. grid-item-card:: 🔀 MATLAB vs. Python
      :link: matlab-vs-python
      :link-type: doc

      What's ported with exact parity, what's approximate, and what's not
      there yet — read this before relying on the Python port for real
      analysis.

   .. grid-item-card:: 📚 API reference
      :link: api/index
      :link-type: doc

      Auto-generated reference for the ``meanap`` package: pipeline steps,
      network plotting, CAT-NAP.

How the Python port relates to MATLAB
---------------------------------------

The Python port (``src/meanap/``) mirrors MATLAB's four core analysis steps —

1. Spike detection
2. Neuronal activity (firing rates, burst detection)
3. Functional connectivity (spike time tiling coefficient)
4. Network metrics (graph theory, node cartography, small-worldness, ...)

— and writes the same output folder structure the MATLAB pipeline produces,
so a Python run and a MATLAB run of the same data land in a comparable shape.
It is a genuine reimplementation, not a wrapper around MATLAB: no MATLAB
license or installation is required to use it.

The Python port is younger than the MATLAB pipeline and does not yet cover
every feature (statistical group comparisons across ages/genotypes, for
example, are not implemented yet). See :doc:`matlab-vs-python` for the
current, honest state of parity before you rely on it for a publication
figure.

.. toctree::
   :maxdepth: 2
   :hidden:

   installation
   quickstart
   gui-guide
   catnap
   network-viewer
   notebooks/network-plotting-tutorial
   output-report
   matlab-vs-python
   api/index
