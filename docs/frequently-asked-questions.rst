
Frequently Asked Questions
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

What do I do if I am experiencing issues with the pipeline? 
----------------------------------------------------------------------------------------

Begin by visiting the GitHub repository. You can find the repository by searching for it on the GitHub website. Once you are on the repository's page, click on the **Issues** tab located in the top menu. This is where you can report problems, ask questions, or request new features.

Next click the green "New Issue" button to initiate the process of submitting a new issue. Describe your problem in detail, including the steps to reproduce the issue and any error messages you encountered. If relevant, include screenshots or code snippets to provide additional context to the issue. Also use appropriate formatting to enhance readability and comprehension. See an example of a detailed, properly formatted GitHub issue here.

**Before submitting your issue**, it is advisable to search for similar problems in the repository's archived issues. This can help you find solutions or gain a better grasp of the problem.

By submitting an issue on GitHub, you are not only seeking assistance but also contributing to the community's knowledge base. Other pipeline users facing comparable issues can consult your issue and any ensuing discussions or resolutions, promoting collaboration and simplifying the process of troubleshooting and resolving pipeline-related problems. 








