function saveEphysStats(ExpName, Params, HomeDir)

%% groups and DIV

Grps = Params.GrpNm;
AgeDiv = Params.DivNm;

if strcmp(char(Grps{1}),'HET') && strcmp(char(Grps{2}),'KO') && strcmp(char(Grps{3}),'WT')
   clear Grps
   Grps{1} = 'WT'; Grps{2} = 'HET'; Grps{3} = 'KO';
end

%% Variable names

% whole experiment metrics (1 value per experiment)

% names of metrics
ExpInfoE = {'Grp','DIV'}; % info for both age and genotype
% list of metrics 
NetMetricsE = {'numActiveElec','FRmean','FRmedian','NBurstRate','meanNumChansInvolvedInNbursts', ... 
               'meanNBstLengthS','meanISIWithinNbursts_ms','meanISIoutsideNbursts_ms','CVofINBI','fracInNburst'}; 

% single cell/node metrics (1 value per cell/node)

% names of metrics
ExpInfoC = {'Grp','DIV'}; % info for both age and genotype
% list of metrics 
NetMetricsC = {'FR'};

%% Import data from all experiments - whole experiment  

experimentMatFolderPath = fullfile(Params.outputDataFolder, ...
        strcat('OutputData',Params.Date), 'ExperimentMatFiles');

allRecordingLevelData = struct();
allElectrodeLevelData = struct();

% allocate numbers to relevant matrices
for i = 1:length(ExpName)
     Exp = strcat(char(ExpName(i)),'_',Params.Date,'.mat');
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
         
         allRecordingLevelData.(eMet) = [allRecordingLevelData.(eMet); expData.('Ephys').(eMet)];
     end 
     
     % electrode level data 
     for e = 1:length(NetMetricsC)
         
         eMet = cell2mat(NetMetricsC(e));
         
         if i == 1
             allElectrodeLevelData.(eMet) = [];
         end 
         
         allElectrodeLevelData.(eMet) = [allElectrodeLevelData.(eMet); expData.('Ephys').(eMet)'];
         
     end 
     
     
end

% transpose Channel when there is only one file, I haven't figured out what is the source of this (why
% it is not an issue when there are multiple files)
if length(ExpName) == 1 && size(allElectrodeLevelData.Channel, 1) == 1
    allElectrodeLevelData.Channel = allElectrodeLevelData.Channel';
end 

outputDataDateFolder = fullfile(Params.outputDataFolder, ...
        strcat('OutputData',Params.Date));
    
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