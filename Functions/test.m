%% Get stats table 
Params.pValThreshold = 0.01;
nodeLevelData = 0;
Params.showOneFig = 1;
Params.usePvalColormap = 1;
Params.usePvalDirection = 1;
Params.figExts = {'.png'};
Params.fullSVG = 0;
HomeDir = nan;
Params.outputDataFolder = nan;
Params.fs = 25000;
Params.channelLayout = 'MCS60old';
addpath(genpath('/Users/timothysit/AnalysisPipeline/Functions'));
biAdvancedSettings;

% for testing one-way ANOVA
% nodeLevelData = 
% recordingLevelData = readtable('/Users/timothysit/Dropbox/tempData/temp_HPC/NetworkActivity_RecordingLevel.csv');
% plotSaveFolder = '/Users/timothysit/Desktop/testStats/hpc';

% for testing two-way ANOVA 
recordingLevelData = readtable('/Users/timothysit/Dropbox/tempData/mecp2-network-csv/NetworkActivity_RecordingLevel2.csv');
plotSaveFolder = '/Users/timothysit/Desktop/testStats/mecp2';

statsTable = doStats(nodeLevelData, recordingLevelData, Params);

%% Plot 
oneFigureHandle = NaN;
oneFigureHandle = checkOneFigureHandle(Params, oneFigureHandle);

plotStats(statsTable, plotSaveFolder, Params, oneFigureHandle)


