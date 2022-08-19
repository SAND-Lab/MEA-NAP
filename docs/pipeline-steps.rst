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

1.  ``*.mat`` files converted from the raw acquisition files from the MEA recordings. 

 - Each file should have three variables: ``fs`` : an integer which specifies the sampling rate, ``channel`` : a 1 x nChannel vector which gives an integer ID for each channel, and ``dat`` : a nSample x nChannel matrix which contains the potential difference (voltage) of each channel over time samples
 - For details about how to convert your raw data into this format, see:  :ref:`this section <preparing_data_for_pipeline>`
 - For data acquired with Multi-channel Systems MCRack, use the MCTool to convert to ``.mat``.
 - For data acquired with Axion Maestro, please use our custom conversion script with the AxIS MATLAB files functions (also available from Axion).
 - N.B. it is also possible to use ``*.mat`` files with spike times instead of raw data for the network analysis (steps 2-4 in the pipeline)

Here is an example of the variables you should see in matlab for an input .mat file with 64 channels, recorded at with a sampling frequency of 12500 Hz. 

.. image:: ../imgs/example-input-file-workspace.png
   :width: 500
      
   
2. ``*.csv`` or ``*.xlsx`` file with the first column containing the filenames of the raw ``*.mat`` files for analysis, second column the age (this should be a number), third column genotype (e.g., WT or KO, do not put numbers in your names), and fourth column including any electrodes that should be grounded (for MCS 60 channel data, electrode 15 should be included here as it is the reference electrode).

Here is an example spreadsheet csv file opened in Microsoft excel: 
 
.. image:: ../imgs/example-spreadsheet-input.png
   :width: 500


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

Folder paths:

* :ref:`HomeDir <HomeDir>`
* :ref:`rawData <rawData>`
* :ref:`Params.priorAnalysisPath <Params.priorAnalysisPath>`
* :ref:`spikeDetectedData <spikeDetectedData>`
* :ref:`spreadsheet_filename <spreadsheet_filename>`

Input and output filetypes:

* :ref:`spreadsheet_file_type <spreadsheet_file_type>`
* :ref:`Params.output_spreadsheet_file_type <Params.output_spreadsheet_file_type>`

Analysis step settings:

* :ref:`Params.priorAnalysisDate <Params.priorAnalysisDate>`
* :ref:`Params.priorAnalysis <Params.priorAnalysis>`
* :ref:`Params.startAnalysisStep <Params.startAnalysisStep>`
* :ref:`Params.optionalStepsToRun <Params.optionalStepsToRun>`
* :ref:`Params.Date <Params.Date>`

Spike detection:

* :ref:`Params.detectSpikes <params.detectspikes>`
* :ref:`Params.fs <Params.fs>`
* :ref:`Params.dSampF <Params.dSampF>`
* :ref:`Params.potentialDifferenceUnit <Params.potentialDifferenceUnit>`
* :ref:`Params.channelLayout <Params.channelLayout>`
* :ref:`Params.coords <Params.coords>`
* :ref:`Params.wnameList <Params.wnameList>`
* :ref:`Params.SpikesMethod <Params.SpikesMethod>`
* :ref:`Params.costList <Params.costList>`
* :ref:`Params.refPeriod <Params.refPeriod>`
* :ref:`Params.filterLowPass <Params.filterLowPass>`
* :ref:`Params.filterHighPass <Params.filterHighPass>`
* :ref:`Params.runSpikeCheckOnPrevSpikeData <Params.runSpikeCheckOnPrevSpikeData>`
* :ref:`Params.threshold_calculation_window <Params.threshold_calculation_window>`
* :ref:`Params.remove_artifacts <Params.remove_artifacts>`
* :ref:`Params.minPeakThrMultiplier <Params.minPeakThrMultiplier>`
* :ref:`Params.maxPeakThrMultiplier <Params.maxPeakThrMultiplier>`
* :ref:`Params.posPeakThrMultiplier <Params.posPeakThrMultiplier>`
* :ref:`Params.multiplier <Params.multiplier>`


Functional connectivity:

* :ref:`Params.FuncConLagval <Params.FuncConLagval>`
* :ref:`Params.TruncRec <Params.TruncRec>`
* :ref:`Params.TruncLength <Params.TruncLength>`
* :ref:`Params.adjMtype <Params.adjMtype>`
* :ref:`Params.ProbThreshRepNum <Params.ProbThreshRepNum>`
* :ref:`Params.ProbThreshTail <Params.ProbThreshTail>`
* :ref:`Params.ProbThreshPlotChecks <Params.ProbThreshPlotChecks>`
* :ref:`Params.ProbThreshPlotChecksN <Params.ProbThreshPlotChecksN>`
  
Network analysis:

* :ref:`Params.netMetToCal <Params.netMetToCal>`
* :ref:`Params.minNumberOfNodesToCalNetMet <Params.minNumberOfNodesToCalNetMet>`
* :ref:`Params.autoSetCartographyBoundaries <Params.autoSetCartographyBoundaries>`
* :ref:`Params.networkLevelNetMetToPlot <Params.networkLevelNetMetToPlot>`
* :ref:`Params.networkLevelNetMetLabels <Params.networkLevelNetMetLabels>`
* :ref:`Params.includeNMFcomponents <Params.includeNMFcomponents>`
* :ref:`Params.effRankCalMethod <Params.effRankCalMethod>`
* :ref:`Params.NMFdownsampleFreq <Params.NMFdownsampleFreq>`
* :ref:`Params.hubBoundaryWMdDeg <Params.hubBoundaryWMdDeg>`
* :ref:`Params.periPartCoef <Params.periPartCoef>`
* :ref:`Params.proHubpartCoef <Params.proHubpartCoef>`
* :ref:`Params.nonHubconnectorPartCoef <Params.nonHubconnectorPartCoef>`
* :ref:`Params.connectorHubPartCoef <Params.connectorHubPartCoef>`

  
Plot settings

* :ref:`Params.figExt <Params.figExt>`
* :ref:`Params.fullSVG <Params.fullSVG>`
* :ref:`Params.showOneFig <Params.showOneFig>`
* :ref:`Params.groupColors <Params.groupColors>`
* :ref:`Params.GrpNm <Params.GrpNm>`
* :ref:`Params.DivNm <Params.DivNm>`
 
  

Folder paths
^^^^^^^^^^^^^^^^^^^

.. _HomeDir:

``HomeDir``
""""""""""""""""""""

 * Argument type : char 
 * The location of the folder with the AnalysisPipeline scripts
 * This will also be the default location in which the analysis pipeline outputs will be saved

.. _rawData:

``rawData``
""""""""""""""""""""

 * Argument type : char
 * The location of the folder with the raw .mat files to be analyzed


.. _Params.priorAnalysisPath:


``Params.priorAnalysisPath``
""""""""""""""""""""""""""""""""

 * Optional (can leave as empty string)
 * Argument type : char
 * Path to previous network pipeline analysis folder


.. _spikeDetectedData:

``spikeDetectedData``
"""""""""""""""""""""""""""

 * Optional (can leave as empty string)
 * Argument type : char
 * Path to previously spike-detected data

.. _spreadsheet_filename:

``spreadsheet_filename``
"""""""""""""""""""""""""""""""

 * the name of spreadsheet containing information about the data to be analysed, including the file extension, usually in the form of 'spreadhsheet.csv' or 'spreadsheet.xlsx'
 * this spreadsheet file is assumed to be located in the main analysis pipeline folder
 * argument type: string or character array

   
Input and output filetypes
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. _spreadsheet_file_type:

``spreadsheet_file_type``
"""""""""""""""""""""""""""

 * Filetype of file which contains a table of recording data
 * Options: 'csv' or 'excel'
 * Default: 'csv'

.. _Params.output_spreadsheet_file_type:

``Params.output_spreadsheet_file_type``
"""""""""""""""""""""""""""""""""""""""""

 * Filetype of output file to create which contains a table of calculated features
 * Options: 'csv' or 'xlsx'
 * Default: 'csv'

Analysis step settings
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. _Params.priorAnalysisDate:

``Params.priorAnalysisDate``
""""""""""""""""""""""""""""""

 * Date of prior analysis, can leave empty or ignore this line if no prior analysis was performed
 * Format: 'DDMonthYYYY', eg. '27Sep2021'


.. _Params.priorAnalysis:

``Params.priorAnalysis``
""""""""""""""""""""""""""""""

 * Whether to use previously analysed data
 * Options : 1 = yes, 0 = no


.. _Params.startAnalysisStep:

``Params.startAnalysisStep``
""""""""""""""""""""""""""""""

 * Which step to start analysis 
 * Options : 1 = spike detection, 2 = neuronal activity, 3 = functional connectivity, 4 = network activity
 * Default : 1


.. _Params.optionalStepsToRun:

``Params.optionalStepsToRun``
"""""""""""""""""""""""""""""

 * Which optional steps to run (after the main steps are performed)
 * Argument type : cell array with strings / characters
 * Options : 'runstats' = obtained feature correlations and do classification, 'getDensityLandscape' = get density landscape plot of participation coefficient and within module z-score
 * Default : {}


.. _Params.Date:

``Params.Date``
""""""""""""""""""""

 * This specifies the date in which the analysis was performed
 * Normally, no user input is required for this parameter, it is automatically set to the date detected on the computer's system clock
 * This also informs what to name the output folder of the pipeline, which will be of the form 'OutputDataDDMonthYYYY'

  
Spike detection
^^^^^^^^^^^^^^^^^^^


.. _params.detectspikes:

``Params.detectSpikes``
""""""""""""""""""""""""""""""

 * determines whether to run spike detection in the pipeline
 * argument type: boolean 
 * options: 0 : do not detect spikes, 1 : detect spikes

.. _Params.fs:

``Params.fs``
""""""""""""""""""""""""""""""""'

 * the sampling rate of the recording electrodes, in samples per second (Hz)
 * argument type: int
 * default : 25000


.. _Params.dSampF:

``Params.dSampF``
""""""""""""""""""""""""""""""""""

 * the down sample frequency for spike detection check
 * normally, this should be kept as the same value as `Params.fs`
 * argument type: int 
 * default: 25000


.. _Params.potentialDifferenceUnit:

``Params.potentialDifferenceUnit``
"""""""""""""""""""""""""""""""""""""""

 * the unit of potential difference in which you are recording electrical signals
 * options: 'mV' for millivolt, 'uV' for microvolt
 * default : 'uV'
 

.. _Params.channelLayout:

``Params.channelLayout``
"""""""""""""""""""""""""""""""

 * which channel layout to use for plotting firing rate heatmaps, and other plots related to the layout of the electrodes
 * options: 'MCS60' = multichannel systems layout with 59 recording electrodes + 1 grounding electrode, 'Axion64' = axion recording layout in a 8 x 8 grid with 64 electrodes, 'Custom' = provide own custom layout by specifying the coordinate of each electrode in biAdvantedSettings.m, you will need to edit the block of code under strcmp(Params.channelLayout, 'Custom')

.. _Params.coords:

``Params.coords``
""""""""""""""""""""""""""""""

 * the x and y coordinates of each electrode to be used for visualisation purposes
 * this is automatically set of Params.channelLayout is one of the provided options 'MCS60' or 'Axion64', but will require to be set by the user if the option chosen the 'Custom' option
 * argument type : nUnit x 2 matrix where nUnit is the number of recorded units, such that each row contains the x and y coordinate of the corresponding recorded unit
 

.. _Params.wnameList:

``Params.wnameList``
""""""""""""""""""""""""""""""

 * determines which wavelets to run the spike detection with 
 * argument type: either string or a cell array of strings
 * options: bior1p5, bior1p3, db2, mea,


.. _Params.SpikesMethod:

``Params.SpikesMethod``
""""""""""""""""""""""""""""""

 * the spike method to used in downstream analysis
 * argument type : char
 * options : 'bior1p5', 'bior1p3', 'merged', 'thr3p0', or other available wavelet names

 If 'merged' is used, then all wavelet-based spike detection methods are combined.
 'mea' uses spikes from electrode-specific custom wavelets (adapted from putative spikes detected using the threshold method)
 'thr3p0' means using a threshold-based method with a multiplier of 3.0, you can specify other thresholds by replacing the decimal place '.' with 'p', eg. 'thr4p5' means a threhold multiplier of 4.5.


.. _Params.costList: 

``Params.costList``
""""""""""""""""""""""""""""

 * the false positive / false negative tradeoff for wavelet spike detection
 * argument type : float value between -2 to 2
 * default value : -0.12

More negative values leads to less false negative but more false positives, recommended range is between -2 to 2, but usually we use -1 to 0. Note that this is in a log10 scale, meaning -1 will lead to 10 times more false positive compared to -0.1


.. _Params.threshold_calculation_window:

``Params.threshold_calculation_window``
"""""""""""""""""""""""""""""""""""""""""""

 * which part of the recording to do spike detection
 * 0 : start of recording, 0.5 : middle of recording, 1 : end of recording
 * argument type : a matlab double with 2 elements
 * This is an advanced setting, modify this in biAdvancedSettings.m
 


.. _Params.refPeriod:
   
``Params.refPeriod``
"""""""""""""""""""""""

 * the refractory period of spikes in milliseconds
 * spikes that are smaller than this time period apart will be excluded
 * argument type : float
 * default value : 0.2
 * This is an advanced setting, modify this in biAdvancedSettings.m


.. _Params.filterLowPass:

``Params.filterLowPass``
"""""""""""""""""""""""""""

 * the low pass frequency (Hz) to use on the raw signal before spike detection
 * argument type : float
 * default value : 600


.. _Params.filterHighPass:

``Params.filterHighPass``
"""""""""""""""""""""""""""

 * the high pass frequency (Hz) to use on the raw signal before spike detection
 * argument type : float
 * default value : 8000

.. _Params.runSpikeCheckOnPrevSpikeData:

``Params.runSpikeCheckOnPrevSpikeData``
""""""""""""""""""""""""""""""""""""""""""

 * Whether to run spike detection check without spike detection 
 * argument type : bool
 * default value : 0
 * options : 0 or 1

Note that setting this to 1 automatically sets `detectSpikes` to 0.

.. _Params.remove_artifacts:

``Params.remove_artifacts``
""""""""""""""""""""""""""""""

 * whether to run process to remove artifacts from recording
 * argument type : bool
 * options : 1 = yes, 0 = no
 * default : 0

.. _Params.minPeakThrMultiplier:

``Params.minPeakThrMultiplier``
""""""""""""""""""""""""""""""""""

 * The minimal spike amplitude that is used for artifact removal
 * After spike detection, spikes with an amplitude smaller than `Params.minPeakThrMultiplier` will be removed 
 * This is used in `alignPeaks.m`
 * This is only used if `Params.remove_artifacts = 1`

.. _Params.maxPeakThrMultiplier:

``Params.maxPeakThrMultiplier``
""""""""""""""""""""""""""""""""""""

 * The maximal spike amplitude in terms of negative peak that is used for artifact removal
 * After spike detection, spikes with a negative peak greater than `Params.maxPeakThrMultiplier` will be removed
 * This is used in `alignPeaks.m`
 * This is only used if `Params.remove_artifacts = 1`

.. _Params.posPeakThrMultiplier:

``Params.posPeakThrMultiplier``
"""""""""""""""""""""""""""""""""""""

 * The maximal spike amplitude in terms of positive peak that is used for artifact removal
 * After spike detection, spikes with a positive peak lower than this value will be removed
 * This is used in `alignPeaks.m`
 * This is only used if `Params.remove_artifacts = 1`

.. _Params.multiplier:
   
``Params.multiplier``
"""""""""""""""""""""""""""""

 * the multiplier to use for extracting spikes for wavelet adaptation method (not for the spike detection itself)
 * this is an advanced setting, and can be found in biAdvancedSettings.m
 * argument type: float
 * default: 3


Functional connectivity
^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. _Params.FuncConLagval:

``Params.FuncConLagval``
""""""""""""""""""""""""""

 * List of lag values (in ms) to use to infer correlation of spike trains
 * Default : [10, 15, 25]

.. _Params.TruncRec:

``Params.TruncRec``
""""""""""""""""""""""""""

 * Whether or not to truncate the recording
 * Options: 1 = yes, 0 = no
 * Default: 0

.. _Params.TruncLength:

``Params.TruncLength``
""""""""""""""""""""""""""

 * The duration (in seconds) of the recording to truncate 
 * Default: 120, but not applied since Params.TruncRec = 0

.. _Params.adjMtype:

``Params.adjMtype``
""""""""""""""""""""""""""

 * The type of adjacency matrix to obtain
 * Options: 'weighted' or 'binary'
 * Default : 'weighted'

.. _Params.ProbThreshRepNum:

``Params.ProbThreshRepNum``
""""""""""""""""""""""""""""""

 * Number of random shuffles to obtain for probabilistic thresholding
 * Default : 200

.. _Params.ProbThreshTail:

``Params.ProbThreshTail``
""""""""""""""""""""""""""""""

 * The percentile threshold to use for probabilistic thresholding
 * Argument type: float between 0 and 1
 * Default : 0.05

.. _ProbThreshPlotChecks:

``ProbThreshPlotChecks``
""""""""""""""""""""""""""""""""""""

 * Whether or not to plot probabilistic thresholding check
 * Options : 1 = yes, 0 = no
 * Default : 1


.. _Params.ProbThreshPlotChecks:

``Params.ProbThreshPlotChecks``
""""""""""""""""""""""""""""""""""""

 * Whether to randomly sample recordings to plot probabilistic thresholding check
 * Options : 1 = yes, 0 = no
 * Default : 1

.. _Params.ProbThreshPlotChecksN:

``Params.ProbThreshPlotChecksN``
""""""""""""""""""""""""""""""""""""""

 * Number of recordings to check (selected randomly) for probabilistic thresholding
 * Argument type : integer value greater than or equal to 1
 * Default : 5



 
Network analysis
^^^^^^^^^^^^^^^^^^^^^

.. _Params.netMetToCal:

``Params.netMetToCal``
"""""""""""""""""""""""""""

 * list of network metrics to calculate
 * argument type : cell containing strings
 * options : ND, EW, NS, aN, etc.

.. _Params.minNumberOfNodesToCalNetMet:

``Params.minNumberOfNodesToCalNetMet``
""""""""""""""""""""""""""""""""""""""""

 * minimum number of nodes required to calculate network metrics
 * argument type : int
 * options : any integer value from 2 to the maximum number of nodes in your network
 * default value : 25

.. _Params.networkLevelNetMetToPlot:

``Params.networkLevelNetMetToPlot``
"""""""""""""""""""""""""""""""""""""""""""

 * list of network metrics to plot, this should be the same or a subset as the list of network metrics to calculate, which is specified in Params.netMetToCal
 * argument type: cell array of strings / characters
 * eg. {'aN', 'Dens', 'effRank'}

.. _Params.networkLevelNetMetLabels:

``Params.networkLevelNetMetLabels``
""""""""""""""""""""""""""""""""""""""""""""

 * list of labels corresponding to the network level metrics to plot
 * eg. 'aN' denotes network size and so the label given is 'network size'
 * argument type: cell array of strings / characters with the same length as `Params.networkLevelNetMetToPlot`
   
.. _Params.includeNMFcomponents:

``Params.includeNMFcomponents``
""""""""""""""""""""""""""""""""""""

 * whether to include the components as output when performing non-negative matrix factorisation on the spike rate matrix, which outputs a matrix of size (num_components, num_time_samples) and a matrix of size (num_components, num_units)
 * argument type : bool
 * options : 0 = no, 1 = yes
 * default : 0

.. _Params.NMFdownsampleFreq:

``Params.NMFdownSampleFreq``
"""""""""""""""""""""""""""""""""""""

 * how mcuh to downsample the spike rate matrix before performing non-negative matrix factorisation
 * eg. 10 will mean downsampling from 25000 Hz to 2500 Hz
 * argument type : int 
 * default : 10 

.. _Params.effRankCalMethod:

``Params.effRankCalMethod``
"""""""""""""""""""""""""""""""

 * whether to use the covariance or correlation matrix for effective rank calculation
 * options: 'covariance' or 'correlation'
 * default: 'covariance'
 * this is an advanced setting and is located in biAdvancedSettings.m
 
  
.. _Params.autoSetCartographyBoundaries:

``Params.autoSetCartographyBoundaries``
"""""""""""""""""""""""""""""""""""""""""""""""

 * Whether or not to automatically determine bounds in the participation coefficient vs. within module z-score space to classify different nodes (eg. hubs versus non-hubs)
 * Options : 1 = yes, 0 = no, use either default or custom coded boundary values

.. _Params.hubBoundaryWMdDeg:

``Params.hubBoundaryWMdDeg``
""""""""""""""""""""""""""""""""""

 * boundary that separtes hub and non-hubs 
 * default value: 0.25
 * argument type: float
 * this argument has no effect if Params.autoSetCartographyBoundaries = 1

.. _Params.periPartCoef:

``Params.periPartCoef``
"""""""""""""""""""""""""""""

 * boundary (in terms of participation coefficient) that separates peripheral node and non-hub connector
 * default value: 0.525
 * argument type : float
 * this argument has no effect if Params.autoSetCartographyBoundaries = 1

.. _Params.proHubPartCoef:

``Params.proHubPartCoef``
""""""""""""""""""""""""""""""

 * boundary (in terms of participation coefficient) that separates provincial hub and connector hub
 * default value: 0.45
 * argument type: float
 * this argument has no effect if Params.autoSetCartographyBoundaries = 1

.. _Params.nonHubConnectorPartCoef:

``Params.nonHubConnectorPartCoef``
""""""""""""""""""""""""""""""""""""""

 * boundary (in terms of participation coefficient) that separates non-hub connector and non-hub kinless node
 * default value: 0.8
 * argument type: float
 * this argument has no effect if Params.autoSetCartographyBoundaries = 1

.. _Params.connectorHubPartCoef:

``Params.connectorHubPartCoef``
"""""""""""""""""""""""""""""""""""""""

 * boundary that separates connector hub and kinless hub
 * default value: 0.75
 * argument type : float
 * this argument has no effect if Params.autoSetCartographyBoundaries = 1


Plot settings
^^^^^^^^^^^^^^^^^

.. _Params.figExt:

``Params.figExt``
""""""""""""""""""""""""""

 * Which file formats to export figures as
 * Argument type : cell array for string / character arrays
 * Default : {'.png'}
 * Options : '.png', '.svg', '.fig'

.. _Params.fullSVG:

``Params.fullSVG``
""""""""""""""""""""""""""

 * Whether to insist matlab to export to SVG in plots with large number of elements, otherwise matlab will compress figure as an image before saving to an SVG file
 * Options : 1 = yes, 0 = no
 * Default : 1

.. _Params.showOneFig:

``Params.showOneFig``
""""""""""""""""""""""""""""""

 * Whether to do all the plotting in the pipeline in one figure handle, this prevents multiple figure from popping out as the code runs, which may interrupt the user using the computer
 * Options : 0 = pipeline show plots as it runs, 1 = only one plot, so pipeline runs in the background
 * Default : 1
  
.. _Params.groupColors:

``Params.groupColors``
""""""""""""""""""""""""""""""""

 * colors to use for each group in group comparison plots
 * this should be an nGroup x 3 matrix where nGroup is the number of groups you have, and each row is a RGB value (scaled from 0 to 1) denoting the color
   
.. _Params.GrpNm:

``Params.GrpNm``
""""""""""""""""""""""""

 * list of names corresponding to the different groups
 * this is automatically generated through the provided spreadsheet and requires no user input in most cases
 * argument type : cell array of string / characters with number of entries equal to the number of unique groups

   
.. _Params.DivNm:

``Params.DivNm``
""""""""""""""""""""""""""

 * list of numbers corresponding to the days in vitro (or any quantification of development time point)
 * this is automatically generated through the provided spreadsheet and requires no user input in most cases
 * argument type : cell array of integers or float with number of entries equal to the number of unique developmental time points 
