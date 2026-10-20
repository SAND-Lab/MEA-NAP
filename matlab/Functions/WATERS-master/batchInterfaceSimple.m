%% Interface for batch spike detection - simple version
%{
This is the main script for running spike detection in multiple files ("in
batch") with most advanced settings hidden away to make this easier to use.

The things you need to modify are:

dataPath (str) : where your .mat files containing electrode recordings are
savePath (str) : where you want to save the spike detection results 
files (cell) : list of file names that you want to run spike detection on

The things you may need to modify are:

param.wnameList (cell) : list of wavelet methods you want to run spike 
detection with, the options include 'bio1.5', 'db2', 'mea'
params.costList (double vector) : list of cost parameters you want to 
run spike detection with, negative numbers means being more generous
(higher false positives, lower false negative), 0 means unbiased. The 
range that provide usable results are within -0.3 and 0.3
params.thresholds (cell) : list of thresholds (in the form of strings) 
you want to run spike detection with
plotDetectionResults (bool) : 0 = do not plot spike detection results
(default), 1 = plot spike detectoin results

The advanced settings are located in the script "biAdvancedSettings.m"

%}

dataPath = '/media/timsit/T7/test-detection/';
savePath = '/media/timsit/T7/test-detection/results/';

addpath(dataPath)

files = { ...
     '2000803_slice3_6.mat', ...
     '2000803_slice3_7_TTX.mat', ... 
};

biAdvancedSettings

params.wnameList = {'bior1.5'}'; 
params.costList = [-0.2, -0.1, 0];
params.thresholds = {'2.5', '3.5', '4.5'}; 
params.plotDetectionResults = 0;

batchDetectSpikes(dataPath, savePath, option, files, params);

if params.plotDetectionResults 
    plotDetectionResults(savePath, savePath);
end 