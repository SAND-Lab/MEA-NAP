
Frequently asked questions
=============================


How do I make sure I have the correct / latest version of the pipeline?
----------------------------------------------------------------------------------

To make sure you have the latest version of the pipeline / to allow switching between pipeline versions easily, it is useful to familarise yourself with running github either via your command line or via the github desktop application. Installation on how to install git / github can be found here: https://github.com/git-guides/install-git. I recommend using the command line version where possible as most of the help you find online will be lines of code that you can run in the command window.

To install the latest version of the pipeline, open your command window, change to a directory you want to store your code (usually the home directory, which is the default location most command windows starts in, will suffice), and type in the following command:

``git clone https://github.com/SAND-Lab/AnalysisPipeline``

What this does is to create a copy of the current analysis pipeline files into a new folder called ``AnalysisPipeline``.

In the future, there may be updates to the code, in which case you need open the command window, change your directory ``AnalysisPipeline``, and type the following command:

``git pull``

What this does is to obtain the latest changes of the pipeline from the github repoistory and add them to your computer.

Sometimes, you may encounter an error when running this because some of your local changes (eg. your edits to the main ``MEApipeline.m``) scripts are in conflict with the version of the web, and github doesn't want to overwrite the changes you have made. In this case, rename the script you have changed, eg. ``MEApipeline_MyName.m``, and then run the command again. You can then copy back the changes you have made into the new script.









