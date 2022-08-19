Introduction
============

The pipeline: a diagnostic tool for studying network function
----------------------------------------------------------------------------------------

The aim of this MATLAB-based network analysis pipeline is to facilitate comparing the development of functional connectivity and other network features at the cellular scale from microelectrode array (MEA) recordings of spontaneous neuronal activity in neuronal cultures.  An overview of the pipeline is represented here:


.. image:: ../imgs/MEApipelineSteps2.png
    :width: 500
    :align: center

The inputs to the pipeline are MEA recordings (raw or filtered time series) imported to MATLAB (blue box in diagram).  Spike detection is performed (green boxes) to identify action potentials detected from the multi-unit activity at individual electrodes (aka nodes). The above-chance functional connectivity between nodes (aka edges) is inferred by correlating multi-unit spiking activity between pairs of electrodes to generate an adjacency matrix. Graph theoretical analysis is next performed (yellow boxes). Plots are then produced to compare age and genotype features of network connectivity and topology (orange box).  The outputs are intended to be a diagnostic tool for examining network activity in the MEA recordings and include figures of neuronal and network activity at the individual electrode and whole recording levels and summary spreadsheets on which statistical analyses can be performed.

Note that the pipeline can be run as a whole from raw MEA data to comparison of network features.  Alternatively, the functions can be run independently. For example, the functions for analysing network activity (yellow) and comparing network features (orange) can be run on spike detected data.

The documentation
--------------------------------

This document is a short guide for running the pipeline and interpreting the outputs of network analysis and age-genotype comparisons.  For new MATLAB users, there are helpful tips for an introduction to MATLAB.  There is also more extensive document available for experienced MATLAB users.

Applications for basic and translational research
----------------------------------------------------------------------------

Alterations in synaptic function, and other cellular processes that affect neuronal communication, can alter the trajectory of network development.  However, currently there is a gap for tools for studying network function at the cellular-scale accessible to cellular neuro- and stem cell biologists working with 2D and 3D rodent and human neuronal cultures. This pipeline combines methods for studying network function using graph theoretical and other network metrics that are commonly used at the whole brain level (e.g., fMRI data) and in other fields of network science.  The aim of the pipeline is to facilitate comparisons in network function at the cellular scale from MEA recordings.  Network function at the cellular scale can provide a platform for testing new therapeutic strategies including pharmacologic therapies and stimulating specific nodes in the network to modulate network function.  
