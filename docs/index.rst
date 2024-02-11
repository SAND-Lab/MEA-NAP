.. MEA network analysis pipeline (MEA-NAP)  documentation master file, created by
   sphinx-quickstart on Fri May 27 16:30:07 2022.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Welcome to the MEA network analysis pipeline (MEA-NAP) documentation!
======================================================================

MEA-NAP is a diagnostic tool for studying microscale functional connectivity, topology, and network dynamics
----------------------------------------------------------------------------------------------------------------------------------------------

The aim of MEA-NAP is to facilitate comparing the development of functional connectivity and other network features at the microscale from microelectrode array (MEA) recordings of spontaneous neuronal activity in 3D human cerebral organoids or 2D human-derived or murine neuronal cultures.  An overview of the MEA-NAP is represented here:


.. image:: imgs/MEANAPoverview.png
    :width: 800
    :align: center

The inputs to the pipeline are MEA recordings (raw or filtered time series) imported to MATLAB.  Spike detection is performed to identify action potentials detected from the multi-unit activity at individual electrodes (aka nodes). The significant functional connections between nodes (aka edges) are inferred by correlating multi-unit spiking activity between pairs of electrodes to generate an adjacency matrix. Next, analysis of the network topology and dynamics are performed. Plots are then produced to compare age and group (e.g., genotype) features of functional connectivity, topology, and network dynamics. Finally, statistical comparisons are performed to select key features.  The outputs are intended to be a diagnostic tool for examining microscale functional network activity in the MEA recordings. The outputs include figures of neuronal and network activity at the individual electrode and whole recording levels and summary spreadsheets on which statistical analyses can be performed.

Note that the pipeline can be run as a whole from raw MEA data to comparison of network features.  Alternatively, the functions can be run independently. For example, the functions for analysing network activity and comparing network features can be run on spike detected data.

The documentation
-------------------

This document is a short guide for running the pipeline and interpreting the outputs of network analysis and age-genotype comparisons.  For new MATLAB users, there are helpful tips for an introduction to MATLAB.  There is also more extensive document available for experienced MATLAB users.

Applications for basic and translational research
----------------------------------------------------------------------------

Alterations in synaptic function, and other cellular processes that affect neuronal communication, can alter the trajectory of network development.  However, currently there is a gap for tools for studying network function at the microscale accessible to cellular neuro- and stem cell biologists working with 2D and 3D rodent and human neuronal cultures. This pipeline combines methods for studying network function using graph theoretical and other network metrics that are commonly used at the whole brain level (e.g., fMRI data) and in other fields of network science.  The aim of the pipeline is to facilitate comparisons in network function at the microscale in MEA recordings.  Network function at the microscale can provide a platform for testing new therapeutic strategies including pharmacologic therapies and stimulating specific nodes in the network to modulate network function.  Applications to 2D or 3D, mouse or human-derived neuronal cultures are illustrated in our paper featuring MEA-NAP, now available at bioRxiv!

Citing MEA-NAP
----------------------------------------------------------------------------

Timothy PH Sit, Rachael C Feord, Alexander WE Dunn, Jeremi Chabros, David Oluigbo, Hugo H Smith, Lance Burn, Elise Chang, Alessio Boschi, Yin Yuan, George M Gibbons, Mahsa Khayat-Khoei, Francesco De Angelis, Erik Hemberg, Martin Hemberg, Madeline A Lancaster, Andras Lakatos, Stephen J Eglen, Ole Paulsen, Susanna B Mierau. **MEA-NAP compares microscale functional connectivity, topology, and network dynamics in organoid or monolayer neuronal cultures.** _bioRxiv_ 2024.02.05.578738. doi: [https://doi.org/10.1101/2024.02.05.578738](https://doi.org/10.1101/2024.02.05.578738) 

.. toctree::
   :maxdepth: 2
   :caption: Contents:
   :hidden:

   setting-up-matlab
   setting-up-meanap
   guide-for-new-users 
   guide-for-advanced-users
   running-MEANAP-on-HPC
   meanap-methods
   meanap-outputs
   system-requirements
   frequently-asked-questions
   how-to-contribute
   sources
   cite-MEANAP
