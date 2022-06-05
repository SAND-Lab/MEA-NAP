# MEA pipeline

[**What is MEA pipeline?**](#mea-pipeline)
| [**Features**](#features)
| [**Installation**](#installation)
| [**How to use the pipeline**](#how-to-use-the-pipeline)
| [**Troubleshooting**](#troubleshooting)


## What is the MEA pipeline?

The MEA pipeline is a streamlined diagnostic and analytic tool for data obtained using microelectrode arrays, it provides a straightforward way for the user to quickly perform spike detection, firing rate analysis, burst detection, network analysis and makes summary plots and performs statistics on these features so that the user can identify developmental or genotypic trends and differences. The pipeline is written in `MATLAB` and is targeted at experimentalists who want have a convinient way to analyze their data without too much user input.

## Features

### Spike detection



## Installation

## How to use the pipeline

Open `MEApipeline.m` in matlab, read through the instructions in section 1
and modify the parameters (full documentation upcoming).


## Troubleshooting

For most issues, please use the Issues tab on github and open a new issue,
eg. see an example issue [here](https://github.com/SAND-Lab/AnalysisPipeline/issues/1).
In other cases (if it is urgent / require long discussion with multiple lab members), you can also send a message on Slack / email.

## Contributing

### Documentation: How to build read-the-docs website locally

The documentation of this toolbox is managed using read-the-docs and sphinx. To build and test the website on your local computer, you first need a python environment (eg. see [anaconda](https://www.anaconda.com/products/distribution)), then you want to install sphinx

```
pip install sphinx
```

then navigate to the folder containing the documentation, which should be in `/your/path/to/AnalysisPipeline/docs/`, then do:

```
make html
```

you can then open your website in `_build/index.html`, and read the "How to contribute" section of the website to learn more about editing the documentation.


