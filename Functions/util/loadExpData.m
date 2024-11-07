function expData = loadExpData(ExpName, Params, usePriorNetMet)
%LOADEXPDATA Summary of this function goes here
%   Detailed explanation goes here
    if Params.priorAnalysis==1 && Params.startAnalysisStep==4 && usePriorNetMet
        experimentMatFileFolder = fullfile(Params.priorAnalysisPath, 'ExperimentMatFiles');
        experimentMatFilePath = fullfile(experimentMatFileFolder, strcat(char(ExpName),'_',Params.priorAnalysisSubFolderName,'.mat'));
        expData = load(experimentMatFilePath);
    elseif Params.priorAnalysis==1 && Params.startAnalysisStep==3
        priorAnalysisExpMatFolder = fullfile(Params.priorAnalysisPath, 'ExperimentMatFiles');
        spikeDataFname = strcat(char(ExpName(ExN)),'_',Params.priorAnalysisSubFolderName, '.mat');
        spikeDataFpath = fullfile(priorAnalysisExpMatFolder, spikeDataFname);
        if isfile(spikeDataFpath)
            expData = load(spikeDataFpath, 'spikeTimes', 'Ephys', 'Info');
        else 
            % look for spike data in spike data folder 
            spikeDataFpath = fullfile(Params.spikeDetectedData, ...
                strcat([char(ExpName(ExN)) '_spikes.mat']));
            expData = load(spikeDataFpath, 'spikeTimes', 'Info');
        end 
    else
        experimentMatFileFolder = fullfile(Params.outputDataFolder, Params.outputDataFolderName, 'ExperimentMatFiles');
        experimentMatFilePath = fullfile(experimentMatFileFolder, strcat(char(ExpName),'_',Params.outputDataFolderName,'.mat'));
        expData = load(experimentMatFilePath);
    end
    
end

