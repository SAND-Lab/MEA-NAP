
System Requirements
===================


Operating system 
^^^^^^^^^^^^^^^^^^^

The pipeline can be run on Windows, Mac, or Linux operating systems with a minimum of 16 GB RAM.  Typical data file sizes we have used the pipeline with range from 1-3 GB per recording. If your computer does not have sufficient RAM for timing processing of the data, options for reducing the system requirements include: 

- Truncating data length (e.g., clipping recordings to analyse 1 min at a time)
- Downsampling (e.g., we acquire MEA data at 25 kHz with the Multi-channel Systems MEA2100 system, for faster processing we can downsample our time series to 12.5 kHz)
- Reducing number of repeats for probabilistic thresholding


MathWorks account and license
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

MATLAB is a product of MathWorks and requires a license and personal MATLAB account.  Many Universities have institutional licenses.  If there is anyone interested in adapting the MATLAB scripts to an open source programming language (e.g., Julia, Python), please let us know.  We want the pipeline to be an open source resource to the neuroscience community.
  
MATLAB versions and required packages
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

This pipeline was written for the current  MATLAB version 2021b.  

The following packages provided by MATLAB need to be installed in order for the pipeline scripts to run:

- Signal Processing Toolbox

- Parallel Computing Toolbox

- Statistics and Machine Learning Toolbox

- Wavelet Toolbox

- Curve Fitting Toolbox (for the calcium imaging pipeline)


The following package must also be downloaded from the Brain Connectivity Toolbox (Rubinov & Sporns, 2010) website: https://sites.google.com/site/bctnet/ 

- Brain Connectivity Toolbox - This toolbox must be saved to the same folder as the network analysis pipeline folder, typically the user path folder, and added to the search path.


.. list-table:: MEA-NAP Timing Benchmarks
   :widths: 25 25 25 25 25 25 25 25 25 25
   :header-rows: 1

   * - Computer CPU 
     - Computer RAM
     - Operating System
     - Matlab version
     - Number of files
     - Length of each MEA recording (minutes)
     - Step 1 Duration (s)
     - Step 2 Duration (s)
     - Step 3 Duration (s)
     - Step 4 Duration (s)
   * - 11th Gen Intel i7-11700K (16) @ 4.9GHz
     - 64
     - Ubuntu 22.04.3 LTS
     - R2021a
     - 1
     - 10
     - 203
     - 17
     - 8
     - 305
   * - Apple M1 Pro
     - 32
     - macOS 14.0
     - R2021b
     - 1 
     - 10
     - 183
     - 50
     - 37
     - 597