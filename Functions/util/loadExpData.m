function expData = loadExpData(ExpName, Params, usePriorNetMet)
%LOADEXPDATA Summary of this function goes here
%   Detailed explanation goes here
    if Params.priorAnalysis==1 && Params.startAnalysisStep==4 && usePriorNetMet
        experimentMatFileFolder = fullfile(Params.priorAnalysisPath, 'ExperimentMatFiles');
        experimentMatFilePath = fullfile(experimentMatFileFolder, strcat(char(ExpName),'_',Params.priorAnalysisSubFolderName,'.mat'));
    else
        experimentMatFileFolder = fullfile(Params.outputDataFolder, Params.outputDataFolderName, 'ExperimentMatFiles');
        experimentMatFilePath = fullfile(experimentMatFileFolder, strcat(char(ExpName),'_',Params.outputDataFolderName,'.mat'));
    end
    
    expData = load(experimentMatFilePath);


end

