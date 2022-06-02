
System Requirements
===================


System requirements and installing MATLAB
---------------------------------------------------------------------

System requirements
^^^^^^^^^^^^^^^^^^^^^^^^^^

The pipeline can be run on Windows, Mac, or Linux operating systems with a minimum of 16 GB RAM.  Typical data file sizes we have used the pipeline with range from 1-3 GB per recording. If your computer does not have sufficient RAM for timing processing of the data, options for reducing the system requirements include: 

- Truncating data length (e.g., clipping recordings to analyse 1 min at a time)
- Downsampling (e.g., we acquire MEA data at 25 kHz with the Multi-channel Systems MEA2100 system, for faster processing we can downsample our time series to 12.5 kHz)
- Reducing number of repeats for probabilistic thresholding



MathWorks account and license
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

MATLAB is a product of MathWorks and requires a license and personal MATLAB account.  Many Universities have institutional licenses.  If there is anyone interested in adapting the MATLAB scripts to an open source programming language (e.g., Julia, Python), please let us know.  We want the pipeline to be an open source resource to the neuroscience community.
  
MATLAB Versions and Required Packages
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

This pipeline was written for the current  MATLAB version 2021b.  
The following packages provided by MATLAB need to be installed in order for the pipeline scripts to run:
Signal Processing Toolbox
Parallel Computing Toolbox
Statistics and Machine Learning Toolbox
Curve Fitting Toolbox (for the calcium imaging pipeline)

The following package must also be downloaded from the Brain Connectivity Toolbox (Rubinov & Sporns, 2010) website: https://sites.google.com/site/bctnet/ 


Brain Connectivity Toolbox - This toolbox must be saved to the same folder as the network analysis pipeline folder, typically the user path folder, and added to the search path.

For assistance, please see our new MATLAB users help guide.

Preparing MEA data for the pipeline
----------------------------------------------------------

This pipeline currently has been tuned for single MEA recordings made on the Multi-channel Systems MEA2100 60-channel MEA system and for multi-well plates using the Axion Maestro MEA System.  Users wishing to adapt data recordings acquired with other MEA systems may find the more extensive documentation for more experienced MATLAB users helpful.


Converting raw files acquired from MEA system to MATLAB
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^


- For Multi-channel Systems (MCS) MEA2100 recordings made with MCRack, we use the MC_DataTool software (MCS) to convert the ``*.mcd`` files to ``*.raw`` and the ``*.raw`` files to ``*.mat`` files.  The network analysis pipeline was created to first use on these ``*.mat`` files. 
- For Axion Maestro recordings from multiwell MEA plates, we use the AxIS MATLAB functions provided by Axion to convert the ``*.raw`` files for the whole plates into ``*.mat`` files and a custom MATLAB function (provided here) to create ``*.mat`` files for each MEA in the plate (e.g., 6, 48). The well is indicated by the suffix (e.g., “..._A1”, “..._A2”)
- N.B. All of the ``*.mat`` files (raw or spikes detected) that will be analyzed and compared in the pipeline should be saved in the same folder. 


Converting spike detection files from other sources to a spike matrix for input to this pipeline
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^


When microelectrode array (MEA) time series data are directly inputted into the pipeline, they are handled on the assumption each column represents the voltage difference (in microvolts) from a single electrode and each row represents the frames of recording (frame number can be converted to time based on the data acquisition rate of the recording).

Spike times are processed to create a spike matrix.


.. list-table:: 
   :widths: 25 50
   :header-rows: 1

   * - Variable
     - Description 
   *  - ``spikeTimes``
      -  column vector containing times (s) at which spike events detected
   * - ``spikeMatrix``
     - binary matrix with length equal to the total number of recording frames representing detected spike events across all electrodes

The ``spikeTimes`` variable for each recording is stored in the ‘ExperimentMatFiles’ folder (in the OutputData folder of the pipeline for each recording). Spike matrices are large arrays, even for short recording durations, due to the high sampling frequency of MEA systems. Thus, the spike matrices are not stored as outputs of the pipeline, nor are they visible as Workspace variables.  The spike matrix can easily be visualised as a raster plot (see for individual recording folders in the OutputData folder \2_NeuronalActivity\2A_Individual…\). Spike counts are binned per second and plotted as firing rates (Hz) in a heatmap.
