function saveEphysStats(ExpName, Params)
% Saves data related to spike and bursts to two csv files 
% One csv contains node level metrics : NeuronalActivity_NodeLevel
% One csv contains network level metrics : NeuronalActivity_RecordingLevel
% INPUT 
% -----
% ExpName : cell array 
%      cell array with size N x 1 where N is the number of recordings 
%      each entry is the name of a recording file without the extension 
%      eg. MPT_220603_10A_DIV14
% Params : struct
%      Parameter structure 

%% groups and DIV

Grps = Params.GrpNm;
AgeDiv = Params.DivNm;

%% Variable names

% whole experiment metrics (1 value per experiment)

% names of metrics
ExpInfoE = {'Grp','DIV'}; % info for both age and genotype
if Params.suite2pMode == 0
    activityStatsFieldName = 'Ephys';  
    % list of metrics 
    NetMetricsE = {'numActiveElec','FRmean','FRmedian','NBurstRate','meanNumChansInvolvedInNbursts', ... 
                   'meanNBstLengthS','meanISIWithinNbursts_ms','meanISIoutsideNbursts_ms','CVofINBI','fracInNburst'}; 
else 
    activityStatsFieldName = 'activityStats';
    NetMetricsE = {'numActiveElec','FRmean','FRmedian', 'recHeightMean', 'recPeakDurMean', 'recEventAreaMean'}; 
end

% -------------------------------------------------
% single cell/node metrics (1 value per cell/node)

% names of metrics
ExpInfoC = {'Grp','DIV'}; % info for both age and genotype
% list of metrics 
if Params.suite2pMode == 0
    NetMetricsC = {'FR'};
else 
     NetMetricsC = {'FR', 'unitHeightMean', 'unitPeakDurMean', 'unitEventAreaMean'};
end 

%% Import data from all experiments - whole experiment  

experimentMatFolderPath = fullfile(Params.outputDataFolder, ...
        Params.outputDataFolderName, 'ExperimentMatFiles');

allRecordingLevelData = struct();
allElectrodeLevelData = struct();

% allocate numbers to relevant matrices
for i = 1:length(ExpName)
     Exp = strcat(char(ExpName(i)),'_',Params.outputDataFolderName,'.mat');
     ExpFilePath = fullfile(experimentMatFolderPath, Exp);
     % Load to variable
     expData = load(ExpFilePath);
     
     if i == 1
         allRecordingLevelData.FileName  = {};
         allRecordingLevelData.Grp = {};
         allRecordingLevelData.DIV = [];
         
         allElectrodeLevelData.FileName = {};
         allElectrodeLevelData.Grp = {};
         allElectrodeLevelData.DIV = [];
         allElectrodeLevelData.Channel = [];
     end 
     
     
     allRecordingLevelData.FileName = [allRecordingLevelData.FileName; expData.Info.FN{1}];
     allRecordingLevelData.Grp = [allRecordingLevelData.Grp; expData.Info.Grp{1}];
     allRecordingLevelData.DIV = [allRecordingLevelData.DIV; expData.Info.DIV{1}];
     
     % add to electrode level data 
     numElectrodes = length(expData.spikeTimes); 
     allElectrodeLevelData.FileName = [allElectrodeLevelData.FileName; repmat({expData.Info.FN{1}}, numElectrodes, 1)];
     allElectrodeLevelData.Grp = [allElectrodeLevelData.Grp; repmat({expData.Info.Grp{1}}, numElectrodes, 1)];
     allElectrodeLevelData.DIV = [allElectrodeLevelData.DIV; repmat(expData.Info.DIV{1}, numElectrodes, 1)];
     
     if size(expData.Info.channels, 1) == 1
        allElectrodeLevelData.Channel = [allElectrodeLevelData.Channel; expData.Info.channels'];
     else
        allElectrodeLevelData.Channel = [allElectrodeLevelData.Channel; expData.Info.channels];
     end
     
     % recording level data 
     for e = 1:length(NetMetricsE)
         eMet = cell2mat(NetMetricsE(e));
         
         if i == 1
             allRecordingLevelData.(eMet) = [];
         end 
         
         allRecordingLevelData.(eMet) = [allRecordingLevelData.(eMet); expData.(activityStatsFieldName).(eMet)];
     end 
     
     % electrode level data 
     for e = 1:length(NetMetricsC)
         
         eMet = cell2mat(NetMetricsC(e));
         
         if i == 1
             allElectrodeLevelData.(eMet) = [];
         end 
         
         allElectrodeLevelData.(eMet) = [allElectrodeLevelData.(eMet); expData.(activityStatsFieldName).(eMet)'];
         
     end 
     
     
end

% transpose Channel when there is only one file 
if length(ExpName) == 1 && size(allElectrodeLevelData.Channel, 1) == 1
    allElectrodeLevelData.Channel = allElectrodeLevelData.Channel';
end 

outputDataDateFolder = fullfile(Params.outputDataFolder, ...
        Params.outputDataFolderName);
    
% save recording level data 
allRecordingLevelDataTable = struct2table(allRecordingLevelData);
spreadsheetFname = strcat('NeuronalActivity_RecordingLevel', '.csv');
spreadsheetFpath = fullfile(outputDataDateFolder, spreadsheetFname);
writetable(allRecordingLevelDataTable, spreadsheetFpath);

% save electrode level data
allElectrodeLevelDataTable = struct2table(allElectrodeLevelData);
electrodeSpreadsheetFname = strcat('NeuronalActivity_NodeLevel','.csv');
electrodeSpreadsheetFpath = fullfile(outputDataDateFolder, electrodeSpreadsheetFname);
writetable(allElectrodeLevelDataTable, electrodeSpreadsheetFpath);




end 