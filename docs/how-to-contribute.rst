Contributing to the Project
=============================


Documentation
--------------------------------------------

The documentation is created using `sphinx <https://www.sphinx-doc.org/en/master/>`_ and `read-the-docs <https://readthedocs.org/>`_, which uses the reStructuredText format to create documents. To add documentation, go to the ``docs`` folder, where you will find a list of ``.rst`` files, the home page is written in ``index.rst``, and links to the other subpages which are in the other ``.rst`` files.

These documents can be opened in any text editor of your choice, to learn more about how to write in reStructuredText, you can read:

* https://www.sphinx-doc.org/en/master/usage/restructuredtext/basics.html
* https://sublime-and-sphinx-guide.readthedocs.io/en/latest/index.html

A brief guide to building the documentation website on your computer before pushing changes to github: 

 - (Optional by recommended) Set up a virtual python environment (eg. using anaconda)
 - Install the required python packages: change your directory to ``pip install MEA-NAP/docs/requirements.txt``
 - To build the website fromthe ``.rst`` files, change your directory to ``MEA-NAP/docs``, then do ``make html``
 - If there are no error messages, the website is built, you can open ``docs/_build/html/index.html``, which should open a website on your default internet browser, and navigate as normal. Note, this does not mean you have updated the online documentation, to do that, you need to push the changes of your rst files to github.


Code
-------------------------------------

To contribute code to the project, create a new branch of the analysis pipeline from the `github site <https://github.com/SAND-Lab/AnalysisPipeline/>`_, make your changes, and create a `pull request <https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/proposing-changes-to-your-work-with-pull-requests/about-pull-requests/>`_.



Releases and development builds
-------------------------------------

MEA-NAP has two kinds of version.

**Official releases** (``v1.11.0``, ``v1.12.0``, ...) are made by hand when a
set of changes is ready to recommend:

 - bump ``version.txt`` in a pull request. MATLAB compares this file with the
   copy on GitHub to tell users they are out of date, so change it only for
   an official release.
 - write the release notes in ``release_notes/``.
 - once that pull request is merged, tag the merge commit and publish a
   GitHub release with the notes. This one is marked *Latest*.

**Development builds** (``v1.11.0-dev.23``, ...) are made automatically by
``.github/workflows/dev-build.yml`` every time something is merged into
``main``. The number counts merges since the last official release. Each build
gets a tag and a GitHub *pre-release*, whose notes are the list of pull
requests merged since the previous build, so nothing needs writing. The pull
request descriptions are where the detail lives. Development builds never
change ``version.txt`` and are never marked *Latest*.

Every development build can be opened, or set as the default, from the Python
GUI's versions dialog, like an official release. Python runs also record the
exact build and commit in ``params.json`` and in the bundle manifest. So a
result produced between releases can always be traced to the code that made
it.

Pushing to a feature branch does not make a build. Only merges into ``main``
do. If an official release's tag is pushed after its merge has already been
built, that commit has both tags. MEA-NAP then calls it by the official one.


Suggestions / Troubleshooting
---------------------------------------------------

For general code suggestions, such as adding new features, or troubleshooting, open up a new issue in the `issues page <https://github.com/SAND-Lab/AnalysisPipeline/issues/>`_ of the github site. You can see an example issue `here <https://github.com/SAND-Lab/AnalysisPipeline/issues/1/>`_.

