Pipeline steps
==============

Overview of the network analysis pipeline
----------------------------------------------------------------

The pipeline has the following steps:

1. Spike detection (this step can be skipped if done previously)
2. Comparison of the neuronal activity (e.g., firing rates, burst rates)
3. Inferring the functional connectivity
4. Comparison of the network activity (i.e., graph theoretical metric)

   
Starting the pipeline
--------------------------------

The Analysis Pipeline folder must be downloaded from our GitHub repository, opened in MATLAB and added with its subfolders to the path. 

The input files required for the pipeline are:

-  ``*.mat`` files converted from the raw acquisition files from the MEA recordings.  For data acquired with Multi-channel Systems MCRack, use the MCTool to convert to ``.mat``.  For data acquired with Axion Maestro, please use our custom conversion script with the AxIS MATLAB files functions (also available from Axion). N.B. it is also possible to use ``*.mat`` files with spike times (see line 79) instead of raw data (see line 51) for the network analysis (steps 2-4 in the pipeline)

- ``*.csv`` or ``*.xlsx`` file with the first column containing the filenames of the raw ``*.mat`` files for analysis, second column the age (this should be a number), third column genotype (e.g., WT or KO, do not put numbers in your names), and fourth column including any electrodes that should be grounded (for MCS 60 channel data, electrode 15 should be included here as it is the reference electrode). See lines 20-36. 

To use the pipeline, open ``MEApipeline.m`` in MATLAB.


