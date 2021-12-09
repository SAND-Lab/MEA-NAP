function [] = CreateOutputFolders(HomeDir,Date,GrpNm)

% this function creates the following output folder structure:
%
%   OutputData+Date
%       ExperimentMatFiles
%       1_SpikeDetection
%       2_NeuronalActivity
%       3_EdgeThresholdingCheck
%       4_NetworkActivity

%% make sure we start in the home directory
cd(HomeDir)

%% does an output folder already exist for that date?

if exist(strcat('OutputData',Date),'dir')
    % if so, choose a suffix to rename previous analysis folder
    NewFNsuffix = inputdlg({'An output data folder already exists for the date today, enter a suffix for the old folder to differentiate (i.e. v1)'});
    NewFN = strcat('OutputData',Date,char(NewFNsuffix));
    % rename the old folder
    movefile(strcat('OutputData',Date),NewFN)
end

%% now we can create the output folders

mkdir(strcat('OutputData',Date))
cd(strcat('OutputData',Date))
mkdir('ExperimentMatFiles')
mkdir('1_SpikeDetection')
cd('1_SpikeDetection')
mkdir('1A_SpikeDetectedData')
mkdir('1B_SpikeDetectionChecks')
cd('1B_SpikeDetectionChecks')
for i = 1:length(GrpNm)
    mkdir(char(GrpNm{i}))
end
cd(HomeDir); cd(strcat('OutputData',Date));
mkdir('2_NeuronalActivity')
cd('2_NeuronalActivity')
mkdir('2A_IndividualNetworkAnalysis')
cd('2A_IndividualNetworkAnalysis')
for i = 1:length(GrpNm)
    mkdir(char(GrpNm{i}))
end
cd(HomeDir); cd(strcat('OutputData',Date)); cd('2_NeuronalActivity')
mkdir('2B_GroupComparisons')
cd('2B_GroupComparisons')
mkdir('1_NodeByGroup')
mkdir('2_NodeByAge')
mkdir('3_RecordingsByGroup')
cd('3_RecordingsByGroup')
mkdir('HalfViolinPlots')
mkdir('NotBoxPlots')
cd(HomeDir); cd(strcat('OutputData',Date)); 
cd('2_NeuronalActivity'); cd('2B_GroupComparisons')
mkdir('4_RecordingsByAge')
cd('4_RecordingsByAge')
mkdir('HalfViolinPlots')
mkdir('NotBoxPlots')
cd(HomeDir)
cd(strcat('OutputData',Date))
mkdir('3_EdgeThresholdingCheck')
mkdir('4_NetworkActivity')
cd('4_NetworkActivity')
mkdir('4A_IndividualNetworkAnalysis')
cd('4A_IndividualNetworkAnalysis')
for i = 1:length(GrpNm)
    mkdir(char(GrpNm{i}))
end
cd(HomeDir); cd(strcat('OutputData',Date)); cd('4_NetworkActivity')
mkdir('4B_GroupComparisons')
cd('4B_GroupComparisons')
mkdir('1_NodeByGroup')
mkdir('2_NodeByAge')
mkdir('3_RecordingsByGroup')
cd('3_RecordingsByGroup')
mkdir('HalfViolinPlots')
mkdir('NotBoxPlots')
cd(HomeDir); cd(strcat('OutputData',Date)); 
cd('4_NetworkActivity'); cd('4B_GroupComparisons')
mkdir('4_RecordingsByAge')
cd('4_RecordingsByAge')
mkdir('HalfViolinPlots')
mkdir('NotBoxPlots')
cd(HomeDir); cd(strcat('OutputData',Date)); 
cd('4_NetworkActivity'); cd('4B_GroupComparisons')
mkdir('5_GraphMetricsByLag')
mkdir('6_NodeCartographyByLag')
cd(HomeDir)
addpath(genpath(strcat('OutputData',Date)))

end