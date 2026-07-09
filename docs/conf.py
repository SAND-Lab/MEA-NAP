# Configuration file for the Sphinx documentation builder.
#
# This file only contains a selection of the most common options. For a full
# list see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Path setup --------------------------------------------------------------

# If extensions (or modules to document with autodoc) are in another directory,
# add these directories to sys.path here. If the directory is relative to the
# documentation root, use os.path.abspath to make it absolute, like shown here.

import os
import sys

# So that `sphinx.ext.autodoc` can `import meanap` (the Python port lives at
# ../src/meanap relative to this file) for the API reference under
# docs/python/api/.
sys.path.insert(0, os.path.abspath('../src'))


# -- Project information -----------------------------------------------------

project = 'MEA pipeline'
copyright = '2022, Timothy Sit, Rachael Feord, Alexander Dunn, Jeremy Chabros, Susanna Mierau, and SAND group members'
author = 'Timothy Sit, Rachael Feord, Alexander Dunn, Jeremy Chabros, Susanna Mierau, and SAND group members'

# The full version, including alpha/beta/rc tags
release = '1.10.2'


# -- General configuration ---------------------------------------------------

# Add any Sphinx extension module names here, as strings. They can be
# extensions coming with Sphinx (named 'sphinx.ext.*') or your custom
# ones.
extensions = [
    'hoverxref.extension',
    # myst_nb subsumes myst_parser (Markdown support) and adds notebook
    # rendering on top - listing both raises a Sphinx transform-registration
    # conflict (myst_parser's setup runs twice), so only myst_nb is listed.
    'myst_nb',
    'sphinx_design',
    'sphinx_copybutton',
    'sphinx.ext.autodoc',
    'sphinx.ext.autosummary',
    'sphinx.ext.napoleon',
    'sphinx.ext.viewcode',
]

# .rst (existing MATLAB docs) continues to work as before; .md (new Python
# docs) is handled by myst_nb, which registers its own source-suffix mapping
# for both '.md' and '.ipynb' - don't override source_suffix here, that would
# clobber the parser name myst_nb registered.

# Add any paths that contain templates here, relative to this directory.
templates_path = ['_templates']

# List of patterns, relative to source directory, that match files and
# directories to ignore when looking for source files.
# This pattern also affects html_static_path and html_extra_path.
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']

# -- MyST (Markdown) ----------------------------------------------------------
myst_enable_extensions = [
    'colon_fence',   # ::: fences, needed for sphinx-design directives in .md
    'deflist',
    'attrs_inline',
]
myst_heading_anchors = 3

# -- MyST-NB (rendered Jupyter notebooks) -------------------------------------
# Notebooks are executed once and the result cached; re-executed only when the
# notebook (or its dependencies) change. Commit the notebook with its outputs
# so a docs build never has to execute it from scratch on a machine without
# the example data.
nb_execution_mode = 'cache'
nb_execution_timeout = 300

# -- autodoc / autosummary (Python API reference) -----------------------------
autosummary_generate = True
autodoc_default_options = {
    'members': True,
    'undoc-members': False,
    'show-inheritance': True,
}
autodoc_typehints = 'description'
napoleon_google_docstring = True
napoleon_numpy_docstring = True
napoleon_include_init_with_doc = True

# -- sphinx-copybutton ---------------------------------------------------------
copybutton_prompt_text = r'>>> |\.\.\. |\$ '
copybutton_prompt_is_regexp = True


# -- Options for HTML output -------------------------------------------------

# The theme to use for HTML and HTML Help pages.  See the documentation for
# a list of builtin themes.
#
html_theme = 'furo'

# Add any paths that contain custom static files (such as style sheets) here,
# relative to this directory. They are copied after the builtin static files,
# so a file named "default.css" will overwrite the builtin "default.css".
# html_static_path = ['_static']
html_static_path = ['_build/html/_static']

# 2025-02-15 TIM: Trying to add custom css to get bold itatlics
# These paths are either relative to html_static_path
# or fully qualified paths (eg. https://...)
html_css_files = [
    'css/custom.css',
]

def setup(app):
  app.add_css_file("css/custom.css")


# -- hoverxref --
hoverxref_auto_ref = True
