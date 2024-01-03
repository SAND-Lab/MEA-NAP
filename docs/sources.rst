Code Sources
==============

The network analysis pipeline is both built on code and packages written by other users in the spike detection and network analysis community, and by our authors. In the methods section we cite packages used for corresponding analysis. Here are references, descriptions, and links for code sources and/or methods utilized in the pipeline.

Methods - Spike Detection
-------------------------

.. list-table:: 
   :widths: 25 25 25 25
   :header-rows: 1

   * - Reference(s)
     - Description
     - Location in MEA-NAP
     - Source code
   * - Nenadic Z & Burdick JW (2005). Spike detection using the continuous wavelet transform. IEEE T Bio-med Eng, 52, 74-87.
     - Continuous wavelet transform (CWT) method for template-based spike detection using the MATLAB function detect_Spikes_wavelet.m
     - detectSpike.m, getTemplate.m, customWavelet.m, detectSpikesWavelet.m  (optional step in MEA-NAP)
     - `detect_spikes_wavelet.m <http://cbmspc.eng.uci.edu/SOFTWARE/SPIKEDETECTION/detect_spikes_wavelet.m>`__
   * - Benitez R & Nenadic Z (2008). Robust unsupervised detection of action potentials with probabilistic models. IEEE T Bio-med Eng, 55(4), 1344-1354.
     - Continuous wavelet transform (CWT) method for template-based spike detection using the MATLAB function detect_Spikes_wavelet.m
     - detectSpike.m, getTemplate.m, customWavelet.m, detectSpikesWavelet.m  (optional step in MEA-NAP)
     - `detect_spikes_wavelet.m <http://cbmspc.eng.uci.edu/SOFTWARE/SPIKEDETECTION/detect_spikes_wavelet.m>`__
   * - Lieb F et al. (2017). A stationary wavelet transform and a time-frequency based spike detection algorithm for extracellular recorded data. J Neural Eng, 14(3), 036013.
     - Stationary wavelet transform (SWTTEO) method for template-based spike detection.
     - detectSpike.m (optional step in MEA-NAP)
     - `SpikeDetection-Toolbox <https://github.com/flieb/SpikeDetection-Toolbox>`__

Methods - Burst analysis
------------------------

.. list-table:: 
   :widths: 25 25 25 25
   :header-rows: 1

   * - Reference(s)
     - Description
     - Location in MEA-NAP
     - Source code
   * - Bakkum DJ, et al. (2014). Parameters for burst detection. Front Comput Neurosci, 7(193).
     - Method for burst detection. Based on ISI_N burst detector (Bakkum, 2013) using BurstDetectISIn.m &    HistogramISIn.m (modified)
     - BurstDetectISIn.m, getISInTh.m
     - `Parameters for burst detection <https://www.frontiersin.org/articles/file/downloadfile/61635_supplementary-materials_presentations_1_pdf/octet-stream/Presentation%201.PDF/1/61635>`__

Methods - Functional connectivity
---------------------------------

.. list-table:: 
   :widths: 25 25 25 25
   :header-rows: 1

   * - Reference(s)
     - Description
     - Location in MEA-NAP
     - Source code
   * - Cutts CS & Eglen SJ (2014). Detecting pairwise correlations in spike trains: An objective comparison of methods and application to the study of retinal waves. J Neurosci, 34(43), 14288–14303.
     - Spike-time tiling coefficient (STTC)
     - get_sttc.m
     - `spike_time_tiling_coefficient.c <https://github.com/CCutts/Detecting_pairwise_correlations_in_spike_trains/blob/master/spike_time_tiling_coefficient.c>`__
    
Methods - Network features
--------------------------

.. list-table::
   :widths: 25 25 25 25
   :header-rows: 1

   * - Reference(s)
     - Description
     - Location in MEA-NAP
     - Source code
   * - Rubinov M & Sporns O (2010). Complex network measures of brain connectivity: Uses and interpretations. NeuroImage, 52(3), 1059–1069.
     - Brain Connectivity Toolbox (BCT) for calculating graph theoretical metrics and null models.
     - Functions in  2019_03_03_BCT folder, CC_PL_SW folder
     - `Brain Connectivity Toolbox <http://www.brain-connectivity-toolbox.net/>`__
   * - Pedersen M et al. (2019). Reducing module size bias of participation coefficient. BioRxiv. doi: 10.1101/747162. Retrieved December 8, 2021.
     - Normalizing the participation coefficient using random networks to preserve degree distribution
     - participation_coef_norm.m
     - `Dynamic_brain_connectivity_analysis <https://github.com/omidvarnia/Dynamic_brain_connectivity_analysis>`__
   * - Bettinardi RG (2017). getCommunicability(W,g,nQexp)MATLAB Central File Exchange. Retrieved June 6, 2022.
     - Communicability function. (Used in fcn_find_hubs_wu.m for ExtractNetMet.m)
     - getCommunicability.m
     - `getCommunicability <https://www.mathworks.com/matlabcentral/fileexchange/62987-getcommunicability-w-g-nqexp>`__

Methods - Statistics
--------------------

.. list-table:: 
   :widths: 25 25 25 25
   :header-rows: 1

   * - Reference(s)
     - Description
     - Location in MEA-NAP
     - Source code
   * - Trujillo-Ortiz A., et al. (2004). RMAOV1:One-way repeated measures ANOVA. MATLAB Central File Exchange. Retrieved August 3, 2023.
     - One-way repeated measures ANOVA
     - RMAOV1.m
     - `RMAOV1 <https://www.mathworks.com/matlabcentral/fileexchange/5576-rmaov1>`__
   * - Schurger A (2005). Two-way repeated measures ANOVA. MATLAB Central File Exchange. Retrieved August 3, 2023.
     - Two-factor, within-subject repeated measures ANOVA
     - rm_anova2.m
     - `Two-way repeated measures ANOVA <https://www.mathworks.com/matlabcentral/fileexchange/6874-two-way-repeated-measures-anova>`__

Tools - GUI
-----------

.. list-table::
   :widths: 25 25 25 25
   :header-rows: 1

   * - Reference(s)
     - Description
     - Location in MEA-NAP
     - Source code
   * - Hoelzer S (2010). Progress bar. MATLAB Central File Exchange. Retrieved December 8, 2021.
     - Progress bar
     - progressbar.m
     - `progressbar <https://www.mathworks.com/matlabcentral/fileexchange/6922-progressbar>`__

Tools - Plotting
----------------

.. list-table:: 
   :widths: 25 25 25 25
   :header-rows: 1

   * - Reference(s)
     - Description
     - Location in MEA-NAP
     - Source code
   * - Marsh G (2016). LOESS regression smoothing. MATLAB Central File Exchange. Retrieved June 23, 2023.
     - Smoothing function using LOESS (locally weighted regression fitting using a 2nd order polynomial)
     - fLOESS.m, getISInTh.m
     - `LOESS regression smoothing <https://www.mathworks.com/matlabcentral/fileexchange/55407-loess-regression-smoothing>`__
   * - Lee T (2006). Kernel density estimation of 2 dim with SJ bandwidth. MATLAB Central File Exchange. Retrieved June 23, 2023.
     - Kernel density estimator with Sheater Jones (SJ) bandwidth
     - bandwidth_SJ.m, KDE2.m
     - `Kernel density Estimation of 2 Dim with SJ bandwidth <https://www.mathworks.com/matlabcentral/fileexchange/10921-kernel-density-estimation-of-2-dim-with-sj-bandwidth>`__
   * - Botev Z (2015). Kernel density estimator. MATLAB Central File Exchange. Retrieved June 23, 2023.
     - Faster kernel density estimator
     - improvedSJkde.m
     - `Kernel Density Estimator <https://www.mathworks.com/matlabcentral/fileexchange/14034-kernel-density-estimator>`__
   * - Thyng KM, et al. (2016). True colors of oceanography. Oceanography, 29(3), 10.
     - Colormap generator
     - cmocean.m
     - `cmocean <https://matplotlib.org/cmocean/>`__
   * - Kumpulainen K (2016). tight_subplot. MATLAB Central File Exchange. Retrieved June 19, 2023.
     - Creates axes subplots with adjustable margins and gaps between the axes
     - tight_subplot.m
     - `tightsubplot <https://www.mathworks.com/matlabcentral/fileexchange/27991-tight_subplot-nh-nw-gap-marg_h-marg_w>`__
   * - Schwizer J (2015). Scalable vector graphics export of figures (fig2svg). GitHub. Retrieved June 16, 2022.
     - Converts MATLAB plots to the scalable vector format (SVG)
     - Functions in fig2svg folder
     - `plot2svg <https://github.com/jschwizer99/plot2svg>`__
   * - Campbell R (2020). notBoxPlot. GitHub. Retrieved December 8, 2021.
     - Plots raw data as a jitter, mean, s.e.m., and 95% confidence intervals (modified)
     - notBoxPlotRF.m
     - `notBoxPlot <https://github.com/raacampbell/notBoxPlot>`__
      

