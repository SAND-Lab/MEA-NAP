![Visitors](https://api.visitorbadge.io/api/visitors?path=https%3A%2F%2Fgithub.com%2FSAND-Lab%2FAnalysisPipeline&label=Visitors&countColor=%23263759)
[![Documentation Status](https://readthedocs.org/projects/analysis-pipeline/badge/?version=latest)](https://analysis-pipeline.readthedocs.io/en/latest/?badge=latest)

# MEA Network Analysis Pipeline (MEA-NAP)

[**What is MEA-NAP?**](#mea-pipeline)
| [**Features**](#features)
| [**Installation**](#installation)
| [**How to use the pipeline**](#how-to-use-the-pipeline)
| [**Troubleshooting**](#troubleshooting)
| [**Contributing**](#contributing)


## What is the MEA-NAP?

The microelectrode array network analysis pipeline (MEA-NAP) is a streamlined diagnostic and analytic tool for cellular scale network activity data obtained using microelectrode arrays (MEAs). MEA-NAP provides a straight forward way for new and experienced MATLAB users to quickly compare spike detection methods, neuronal activity (including firing rate and burst detection), and functional connectivity (including network metrics from graph and control theories). MEA-NAP performs batch analysis of an experimental dataset (e.g., MEA recordings from wild-type and knock-out cultures at multiple developmental time points). MEA-NAP produces summary plots and performs statistics on these features and organizes the output figures in a convenient file structure. The user can then identify network-level developmental or genotypic differences in their MEA dataset. The pipeline is written in `MATLAB` and was designed for experimentalists with little or no experience with network analysis.  Experienced users will find the batch analysis and automatic figure generation convenient for examining both individual network and group comparisons. 

Please see our [detailed documentation for MEA-NAP users at our read-the-docs page](https://analysis-pipeline.readthedocs.io/en/latest/).


## Features


![Network pipeline steps](/imgs/MEANAPoverview.png)

Alterations in synaptic function, and other cellular processes that affect neuronal communication, can alter the trajectory of network development. However, currently there is a gap for tools for studying network function at the cellular-scale accessible to cellular neuro- and stem cell biologists working with 2D and 3D rodent and human neuronal cultures. MEA-NAP combines methods for studying network function using graph theoretical and other network metrics that are commonly used at the whole brain level (e.g., fMRI data) and in other fields of network science. The aim of the pipeline is to facilitate comparisons in network function at the cellular scale from MEA recordings. Network function at the cellular scale can provide a platform for testing new therapeutic strategies including pharmacologic therapies and stimulating specific nodes in the network to modulate network function.

Features include implementation of graph theoretical metrics from the Brain Connectivity Toolbox (commonly applied to study networks at the whole brain macro scale) to cellular-scale functional networks from MEA recordings of neuronal cultures or brain slices. The pipeline also includes new network features applied at the cellular-scale including node cartography for classifying nodal roles within the network and effective rank for calculating the number of subcommunities within the cellular-scale networks based on their activity patterns.  New features also include control theoretical metrics to identify nodes that can drive network activity and dimensionality reduction using non-negative matrix factorization to characterize patterns of activity observed in the network.  Expected new features to come include feature selection.

Importantly, MEA-NAP analyses the MEA experiments through batch analysis automatically adjusting scaling and production of comparison plots to the whole dataset.  This allows users new to network neuroscience to identify the most interesting network-level features in their dataset to explore further.  The plots can also be exported as png (for adding to presentations or posters) or svg (for adjusting font, color, etc) in Illustrator or Affinity Designer.

## Installation

To install MEA-NAP, clone the github repository to a location of your choice (e.g., your desktop folder):

```
git clone https://github.com/SAND-Lab/AnalysisPipeline -b v1.1.0
```

To confirm you have the appropriate version of Matlab and Matlab toolboxes installed, please [see the MEA-NAP systems requirments](https://analysis-pipeline.readthedocs.io/en/latest/system-requirements.html). Our [detailed documentation for MEA-NAP](https://analysis-pipeline.readthedocs.io/en/latest/) provides step-by-step instructions for formatting your data and running MEA-NAP.

To get the cutting edge of the pipeline, which includes the latest features / bug fixes but may introduce new errors, do:

```
git clone https://github.com/SAND-Lab/AnalysisPipeline 
```

## How to use the pipeline

To quickly get started, open `MEApipeline.m` in matlab, and read through the instructions in section 1
and modify the parameters. You can find the [full documentation on our MEA-NAP read-the-docs website](https://analysis-pipeline.readthedocs.io/en/latest/).


## Troubleshooting

For most issues, please use the Issues tab on github and open a new issue,
e.g., see an example issue [here](https://github.com/SAND-Lab/AnalysisPipeline/issues/1).

For SAND Lab users or collaborators: If it is urgent or requires long discussion with multiple lab members, you can also send a message on Slack or email.

## Contributing

### Code

We are always keen to have collaborators who are interested in contributing to the application of network metrics and/or code in MEA-NAP.  Please let us know if you are interested.  

For current SAND users and collaborators, please see [contributing code instructions](https://analysis-pipeline.readthedocs.io/en/latest/how-to-contribute.html) in the MEA-NAP documentation.

### Documentation: How to build read-the-docs website locally

The documentation of this toolbox is managed using read-the-docs and sphinx. To build and test the website on your local computer, you first need a python environment (eg. see [anaconda](https://www.anaconda.com/products/distribution)), then you want to install sphinx

```
pip install sphinx
```

and some extra packages used in this documentation

```
pip install sphinx-hoverxref
```

and also install the theme used for the documentation website:

```
pip install furo
```

then navigate to the folder containing the documentation, which should be in `/your/path/to/AnalysisPipeline/docs/`, then do:

```
make html
```

you can then open your website in `_build/html/index.html`, and read the "How to contribute" section of the website to learn more about editing the documentation.


