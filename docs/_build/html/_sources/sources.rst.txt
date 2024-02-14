

Code Sources
==============

The network analysis pipeline is both built on code and packages written by other users in the spike detection and network analysis community, and by our authors. In the methods section we cite packages used for corresponding analysis. Here are references, descriptions, and links for code sources and/or methods utilized in the pipeline.

=========================

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
     -  http://cbmspc.eng.uci.edu/SOFTWARE/SPIKEDETECTION/detect_spikes_wavelet.m
   * - Benitez R & Nenadic Z (2008). Robust unsupervised detection of action potentials with probabilistic models. IEEE T Bio-med Eng, 55(4), 1344-1354.
     - Continuous wavelet transform (CWT) method for template-based spike detection using the MATLAB function detect_Spikes_wavelet.m
     - detectSpike.m, getTemplate.m, customWavelet.m, detectSpikesWavelet.m  (optional step in MEA-NAP)
     - | http://cbmspc.eng.uci.edu/SOFTWARE/SPIKEDETECTION/detect_spikes_wavelet.m
   * - Lieb F et al. (2017). A stationary wavelet transform and a time-frequency based spike detection algorithm for extracellular recorded data. J Neural Eng, 14(3), 036013.
     - Stationary wavelet transform (SWTTEO) method for template-based spike detection.
     - detectSpike.m (optional step in MEA-NAP)
     - | https://github.com/flieb/SpikeDetection-Toolbox

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
     - https://www.frontiersin.org/articles/file/downloadfile/61635_supplementary-materials_presentations_1_pdf/octet-stream/Presentation%201.PDF/1/61635

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
     - https://github.com/CCutts/Detecting_pairwise_correlations_in_spike_trains/blob/master/spike_time_tiling_coefficient.c
    
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
     - http://www.brain-connectivity-toolbox.net/
   * - Pedersen M et al. (2019). Reducing module size bias of participation coefficient. BioRxiv. doi: 10.1101/747162. Retrieved December 8, 2021.
     - Normalizing the participation coefficient using random networks to preserve degree distribution
     - participation_coef_norm.m
     - https://github.com/omidvarnia/Dynamic_brain_connectivity_analysis
   * - Bettinardi RG (2017). getCommunicability(W,g,nQexp)MATLAB Central File Exchange. Retrieved June 6, 2022.
     - Communicability function. (Used in fcn_find_hubs_wu.m for ExtractNetMet.m)
     - getCommunicability.m
     - https://www.mathworks.com/matlabcentral/fileexchange/62987-getcommunicability-w-g-nqexp

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
     - https://www.mathworks.com/matlabcentral/fileexchange/5576-rmaov1
   * - Schurger A (2005). Two-way repeated measures ANOVA. MATLAB Central File Exchange. Retrieved August 3, 2023.
     - Two-factor, within-subject repeated measures ANOVA
     - rm_anova2.m
     - https://www.mathworks.com/matlabcentral/fileexchange/6874-two-way-repeated-measures-anova

Tools - Data Conversion
---------------------------------------

.. list-table:: 
   :widths: 25 25 25 25
   :header-rows: 1 

   * - References 
     - Description 
     - Location in MEA-NAP 
     - Source code 
   * - Stahl D & Hayes H (2022). AxionFileLoader: A Matlab library capable of reading Axion's RAW and SPK files. GitHub. Retrieved February 10, 2024. 
     - Reads Axion .raw multi-well recording to extract individual MEA recordings using the AxIS MATLAB function AxisFile.m.
     - rawConvert.m utilizes functions from AxIS MATLAB Files folder
     - https://github.com/axionbio/AxionFileLoader
  

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
     - https://www.mathworks.com/matlabcentral/fileexchange/6922-progressbar

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
     - https://www.mathworks.com/matlabcentral/fileexchange/55407-loess-regression-smoothing
   * - Lee T (2006). Kernel density estimation of 2 dim with SJ bandwidth. MATLAB Central File Exchange. Retrieved June 23, 2023.
     - Kernel density estimator with Sheater Jones (SJ) bandwidth
     - bandwidth_SJ.m, KDE2.m
     - https://www.mathworks.com/matlabcentral/fileexchange/10921-kernel-density-estimation-of-2-dim-with-sj-bandwidth
   * - Botev Z (2015). Kernel density estimator. MATLAB Central File Exchange. Retrieved June 23, 2023.
     - Faster kernel density estimator
     - improvedSJkde.m
     - https://www.mathworks.com/matlabcentral/fileexchange/14034-kernel-density-estimator
   * - Thyng KM, et al. (2016). True colors of oceanography. Oceanography, 29(3), 10.
     - Colormap generator
     - cmocean.m
     - https://matplotlib.org/cmocean/
   * - Kumpulainen K (2016). tight_subplot. MATLAB Central File Exchange. Retrieved June 19, 2023.
     - Creates axes subplots with adjustable margins and gaps between the axes
     - tight_subplot.m
     - https://www.mathworks.com/matlabcentral/fileexchange/27991-tight_subplot-nh-nw-gap-marg_h-marg_w
   * - Schwizer J (2015). Scalable vector graphics export of figures (fig2svg). GitHub. Retrieved June 16, 2022.
     - Converts MATLAB plots to the scalable vector format (SVG)
     - Functions in fig2svg folder
     - https://github.com/jschwizer99/plot2svg
   * - Campbell R (2020). notBoxPlot. GitHub. Retrieved December 8, 2021.
     - Plots raw data as a jitter, mean, s.e.m., and 95% confidence intervals (modified)
     - notBoxPlotRF.m
     - https://github.com/raacampbell/notBoxPlot
      
References 
-----------

1. Bassett, D. S., & Bullmore, E. T. (2009). Human brain networks in health and disease. Current Opinion in Neurology, 22(4), 340–347. https://doi.org/10.1097/WCO.0b013e32832d93dd
2. Brandes, U. (2001). A faster algorithm for betweenness centrality. The Journal of Mathematical Sociology, 25(2), 163–177. https://doi.org/10.1080/0022250X.2001.9990249
3. Brandes, U., Delling, D., Gaertler, M., Gorke, R., Hoefer, M., Nikoloski, Z., & Wagner, D. (2008). On Modularity Clustering. IEEE Transactions on Knowledge and Data Engineering, 20(2), 172–188. https://doi.org/10.1109/TKDE.2007.190689
4. Cutts, C. S., & Eglen, S. J. (2014). Detecting pairwise correlations in spike trains: An objective comparison of methods and application to the study of retinal waves. The Journal of Neuroscience, 34(43), 14288–14303. https://doi.org/10.1523/JNEUROSCI.2767-14.2014
5. Elsayed, G. F., & Cunningham, J. P. (2017). Structure in neural population recordings: An expected byproduct of simpler phenomena? Nature Neuroscience, 20(9), 1310–1318. https://doi.org/10.1038/nn.4617
6. Fornito, A., Zalesky, A., & Bullmore, E. T. (Eds.). (2016). Chapter 11—Statistical Connectomics. In Fundamentals of Brain Network Analysis (pp. 383–419). Academic Press. https://doi.org/10.1016/B978-0-12-407908-3.00011-X
7. Guimerà, R., & Nunes Amaral, L. A. (2005). Functional cartography of complex metabolic networks. Nature, 433(7028), 895–900. https://doi.org/10.1038/nature03288
8. Humphries, M.D., Gurney, K., Prescott TJ. (2006). The brainstem reticular formation is a small-world, not scale-free, network. Proc Biol Sci 273(1585):503–11.
9. Humphries, M.D., Gurney, K. (2008). Network ‘Small-World-Ness’: A Quantitative Method for Determining Canonical Network Equivalence. PLoS ONE 3(4): e0002051. https://doi.org/10.1371/journal.pone.0002051
10. Latora, V., & Marchiori, M. (2001). Efficient Behavior of Small-World Networks. Physical Review Letters, 87(19), 198701. https://doi.org/10.1103/PhysRevLett.87.198701
11. Lancichinetti, A., Fortunato, S. Consensus clustering in complex networks. Sci Rep 2, 336 (2012). https://doi.org/10.1038/srep00336
12. Roy, O. & Vetterli, M. (2007), The effective rank: A measure of effective dimensionality. In ‘2007 15th European Signal Processing Conference’, pp. 606–610.
13. Rubinov, M., & Sporns, O. (2010). Complex network measures of brain connectivity: Uses and interpretations. NeuroImage, 52(3), 1059–1069. https://doi.org/10.1016/j.neuroimage.2009.10.003
14. Schroeter, M. S., Charlesworth, P., Kitzbichler, M. G., Paulsen, O., & Bullmore, E. T. (2015). Emergence of rich-club topology and coordinated dynamics in development of hippocampal functional networks in vitro. The Journal of Neuroscience, 35(14), 5459–5470. https://doi.org/10.1523/JNEUROSCI.4259-14.2015
15. Serrano, M. Á., Boguñá, M., & Vespignani, A. (2009). Extracting the multiscale backbone of complex weighted networks. Proceedings of the National Academy of Sciences, 106(16), 6483–6488. https://doi.org/10.1073/pnas.0808904106
16. Telesford, Q. K., Joyce, K. E., Hayasaka, S., Burdette, J. H., & Laurienti, P. J. (2011). The Ubiquity of Small-World Networks. Brain Connectivity, 1(5), 367–375. https://doi.org/10.1089/brain.2011.0038

