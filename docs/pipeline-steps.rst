Pipeline steps
==============

.. _overview: 

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

Before running the script, please enter/ensure the following variables are correct:

Required user input in the first section
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The first section sets many of the parameters that instruct the pipeline where to find your data, select which parts of the analysis pipeline to run, and where to save the output. Follow the prompts to set-up the pipeline for analysing a single or multiple MEA recording files in the same experiment. All of the recordings to be compared should be saved in the same folder. Below line numbers requiring your input (red) or review.

.. list-table:: 
   :widths: 15 25 50
   :header-rows: 1

   * - Line
     - Variable
     - User input required
   *  - 14
      -  HomeDir
      - Set the location of the folder with the AnalysisPipeline scripts.  N.B.  Best not to save in Program Files.
   * - 31, 36
     - spreadsheet  file type file name
     - Input file with list of recordings with their age and genotype. Set as ``*.csv`` or ``*.xlsx``. Name with location for the spreadsheet.
   * - 39 - 40
     - sheet xlRange (optional)
     - If using an .xlsx file type, you can specify all or a subset of the filenames to analyse by changing the sheet number (if more than one sheet in spreadsheet) and/or xlRange (e.g., A2:C3 would analyze the first two files listed in the sheet).
   * - 47
     - Params.output_spreadsheet file_type
     - Option to choose .csv or .xlsx as output file type for your data analysis from the pipeline.  Default is .csv
   * - 51
     - Params.fs
     - Confirm the sampling frequency is correct for your recording.  We acquire data on the MCS 60 channel system at 25000 Hz and on the Axion Maestro at 12500 Hz.



Options to start pipeline at different steps
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
(e.g., save time by running functional connectivity for different time lags without having to rerun the spike detection). 


.. list-table:: 
   :widths: 15 25 50
   :header-rows: 1

   * - Line
     - Variable
     - User input required
   * - 56, 59, 62
     - Params.priorAnalysis, …Path, …Date
     - If you have already run the pipeline previously and wish to use some of the outputs from the earlier steps, set equal to 1 and give the location and date for the prior analysis (this format should match the folder name of the previous data analysis). N.B. If a previous OutputData folder for the Date already exists, the pipeline will prompt you when running to add a suffix to the previous version (e.g. “v1”). The pipeline will then rename the old folder and remove it from the path.
   * - 67
     - Params.startAnalysisStep
     - If you would like to start running the pipeline at a later step than spike detection (step 1) using the prior data, change to the corresponding number (see lines 63-66).  See Section 3.1 for overview of pipeline functions.  N.B. Steps 2-4 all require spike detection to run.  Step 4 requires Step 3.
       


Spike detection settings (lines 69 - 121)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. list-table:: 
   :widths: 15 25 50
   :header-rows: 1

   * - Line
     - Variable
     - User input required
   * - 70
     - detectSpikes
     - If you are starting with a .mat file of a raw recording, set to “1” to run spike detection.  If starting with a .mat file of detected spikes, or have previously run spike detection, set to “0”.
   * - 75
     - rawData
     - This is the folder where your recordings are (*.mat format). Mac uses / for filenames.  PC uses \ for file names.
   * - 78
     - biAdvancedSettings
     - Experienced users can open this *.m file to change more parameters for the spike detection.  (Optional step)
   * - 83
     - Params.threshold
     - Choose one or more standard deviations (SD) if running threshold-based spike detection. This method identifies negative voltage deflections that exceed the threshold set based on the SD of the mean voltage signal. This method is fast. It works well for electrodes with a high signal:noise ratio and for recordings with similar firing rates. Threshold-based methods can underestimate spikes in electrodes with high firing rates and are susceptible to counting large artifacts as spikes, as the spike waveform is not considered.  For 2D & 3D cultures recorded with the MCS 60 channel system, we recommend the 4.5 SD multiplier.  Axion recommends 5.0 for the data acquired on their system. The pipeline allows you to run multiple thresholds and compare the spike detection.
   * - 93
     - Params.wnameList
     - Choose one or more of the MATLAB wavelets if running our template-based spike detection. This method identifies spikes based on the similarity of the spike waveform to the templates (wavelets). For 2D murine cortical cultures recorded with the MCS system, we recommend bior1.5 or running bior1.5, bior1.3, and db and merging the spikes detected for increased sensitivity. Note, these 3 templates do not work as well with 3D human cerebral organoid recordings.
   * - 102
     - Params.costList
     - You have the option to choose one or more cost parameters to run for the templated-based method (line 65).  Lines 65-74 discuss range.  Recommend running for first time users at -0.12. If missing spikes make more negative (e.g., -0.2).  If false positives, make less negative (e.g., -0.10).
   * - 105
     - spikeDetectedData
     - If you are using previous spike detection .mat files for the pipeline, put folder location here.  This allows you to run downstream parts of the pipeline again without having to redo spike detection (saves computational time). Spike detection files are also much smaller file size than raw so easier to share/run on less powerful computers.
   * - 118
     - Params.SpikeMethod
     - Here you choose the spike detection method for the downstream analysis. For the threshold method, please use syntax described in lines 109-111. We have a custom method called “mea” that first uses the threshold method to select spikes to make electrode-specific wavelets for use with the template-based spike detection.  Select “merged” to combine spikes from all wavelets you select to improve sensitivity for detecting multi-unit activity with different waveforms.



Functional connectivity settings
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^


.. list-table:: 
   :widths: 15 25 50
   :header-rows: 1
                 
   * - Line
     - Variable
     - User input required
   * - 122
     - Params.FuncConLagval
     - The pipeline uses the spike time tiling coefficient (STTC; Cutts & Eglen, 2014) to estimate pairwise correlations between spiking activity observed in electrodes. Select one or more lag values (in milliseconds) for detecting coincident activity.  For MCS-acquired data, 25 ms is a good starting point. Pipeline works best if you choose 2 or 3 different lags to compare (although the computational time is longer).
   * - 123, 124
     - Params. TrunRec, TrunLength
     - Calculating the functional connectivity can be computationally intensive. If you wish to shorten (truncate) the recording change TrunRc to 1 and select a length in seconds. N.B. Shortening the recording can significantly change the connectivity estimates.
   * - 127, 128, 129, 130
     - Params. ProbThres... RepNum, Tail, PlotChecks, PlotChecksN
     - Probabilistic thresholding is a method for determining above-chance correlation between activity observed in the electrodes.  It works by shuffling the real data many times (RepNum default = 200) and then calculating the STTC. If the STTC value for the real data is greater than expected by chance for a given electrode pair from the shuffles (e.g., Tail 0.1, aka 90%-tile), that pair is functionally connected. Depending on the number of shuffles and STTC lag, we may use Tail=0.01 (aka 99%-tile). To determine whether the number of shuffles (RepNum) is sufficient in a sample of the recordings, set PlotChecks =1 (otherwise 0) and indicate the number of recordings to examine (PlotChecksN).
   * - 133
     - Params.adjMtype
     - We use weighted networks. The strength of the connectivity between two electrodes is determined by the STTC. Changing to binary would treat weak and strong connections the same. 



Pipeline output preferences
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. list-table:: 
   :widths: 15 25 50
   :header-rows: 1
                 
   * - Line
     - Variable
     - User input required
   * - 161
     - Params.figExt
     - The pipeline output includes a large number of figures which allow you to look at network features within individual networks and to compare across multiple recordings.  You can have these figures in .fig (can edit in MATLAB), .png (standard image), and/or .svg (can edit colors, font sizes in graphics programs). Specify which extensions to include as a cell array in this line.  More file types selected increases pipeline run time.



Run and wait
^^^^^^^^^^^^^^

After completing this list, no further changes are necessary to run the pipeline. Save your changes.  Press RUN and then wait!  The length of time will depend on the acquisition rate, length of recordings, number of files and processing power of the computer. Cluster computing when available is recommended for larger batch datasets.



Pipeline settings
------------------

Overview
^^^^^^^^^^

Spike detection:

:ref:`Params.detectSpikes <params.detectspikes>`

Reference to `Params.detectSpikes`_
Reference to `overview`_

Reference to :ref:`overview`
           

Spike detection
^^^^^^^^^^^^^^^^^^^


.. _params.detectspikes:

``Params.detectSpikes``
""""""""""""""""""""""""""""""

 * determines whether to run spike detection in the pipeline
 * argument type: boolean 
 * options: 0 : do not detect spikes, 1 : detect spikes
 
