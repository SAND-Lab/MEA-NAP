function saveNetMet(ExpName, Params, HomeDir)
%SAVENETMET Summary of this function goes here
% Parameters
% ----------
% ExpName : str 
% Params : struct 
% HomeDir : str
% Output 
% -------
% None


%% groups and DIV

Grps = Params.GrpNm;
AgeDiv = Params.DivNm;

if strcmp(char(Grps{1}),'HET')&&strcmp(char(Grps{2}),'KO')&&strcmp(char(Grps{3}),'WT')
   clear Grps
   Grps{1} = 'WT'; Grps{2} = 'HET'; Grps{3} = 'KO';
end

%% Variable names

% whole experiment metrics (1 value per experiment)

% names of metrics
ExpInfoE = {'Grp','DIV'}; % info for both age and genotype, TODO: this is not used
% list of metrics that are obtained at the network level
NetMetricsE = Params.networkLevelNetMetToPlot;
% 'NCpn1','NCpn2','NCpn3','NCpn4','NCpn5','NCpn6' are moved
% single cell/node metrics (1 value per cell/node)

% names of metrics
ExpInfoC = {'Grp','DIV'}; % info for both age and genotype, TODO: this is not used
% list of metrics that are obtained at the electrode level
NetMetricsC = Params.unitLevelNetMetToPlot;


%% Get recording and electrode level metrics
% and put them on separate tables 

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
         allRecordingLevelData.Lag = [];
         
         allElectrodeLevelData.FileName = {};
         allElectrodeLevelData.Grp = {};
         allElectrodeLevelData.DIV = [];
         allElectrodeLevelData.Channel = [];
         allElectrodeLevelData.Lag = [];
     end 
     
     numLagVals = length(Params.FuncConLagval);
     
     allRecordingLevelData.FileName = [allRecordingLevelData.FileName; repmat({expData.Info.FN{1}}, numLagVals, 1)];
     allRecordingLevelData.Grp = [allRecordingLevelData.Grp; repmat({expData.Info.Grp{1}}, numLagVals, 1)];
     allRecordingLevelData.DIV = [allRecordingLevelData.DIV; repmat({expData.Info.DIV{1}}, numLagVals, 1)];
     allRecordingLevelData.Lag = [allRecordingLevelData.Lag; Params.FuncConLagval'];
     
     % add to electrode level data 

     % recording level data 
     for e = 1:length(NetMetricsE)
         eMet = cell2mat(NetMetricsE(e));
         
         if i == 1
             allRecordingLevelData.(eMet) = [];
         end 
         
         for lag = Params.FuncConLagval
            lagField = strcat('adjM', num2str(lag), 'mslag');
            
            if e == 1
                numElectrodes = expData.NetMet.(lagField).aN;
                allElectrodeLevelData.FileName = [allElectrodeLevelData.FileName; repmat({expData.Info.FN{1}}, numElectrodes, 1)];
                allElectrodeLevelData.Grp = [allElectrodeLevelData.Grp; repmat({expData.Info.Grp{1}}, numElectrodes, 1)];
                allElectrodeLevelData.DIV = [allElectrodeLevelData.DIV; repmat(expData.Info.DIV{1}, numElectrodes, 1)];
                % NOTE: This is currently a temp fix, the electrode
                % identity is not correct here and will need to be included
                % in future implementations including the electrode numbers
                % in expData (Tim Sit 2023-01-07)
                if size(expData.Info.channels(1:numElectrodes), 1) == 1
                    allElectrodeLevelData.Channel = [allElectrodeLevelData.Channel; expData.Info.channels(1:numElectrodes)'];
                else
                    allElectrodeLevelData.Channel = [allElectrodeLevelData.Channel; expData.Info.channels(1:numElectrodes)];
                end
                
                allElectrodeLevelData.Lag = [allElectrodeLevelData.Lag; repmat(lag, numElectrodes, 1)]; 
     
            end 
            if strcmp(eMet, 'effRank')
                firstLagField = sprintf('adjM%.fmslag', Params.FuncConLagval(1));
                allRecordingLevelData.(eMet) = [allRecordingLevelData.(eMet); expData.('NetMet').(firstLagField).(eMet)];
            else
                allRecordingLevelData.(eMet) = [allRecordingLevelData.(eMet); expData.('NetMet').(lagField).(eMet)];
            end 
         end 
     end 
     
     % electrode level data 
     for e = 1:length(NetMetricsC)
         
         eMet = cell2mat(NetMetricsC(e));
         
         if i == 1
             allElectrodeLevelData.(eMet) = [];
         end 
         
         for lag = Params.FuncConLagval
            
            lagField = strcat('adjM', num2str(lag), 'mslag');
            numElectrodes = expData.NetMet.(lagField).aN;
            
            if sum(isnan(expData.('NetMet').(lagField).(eMet))) == length(expData.('NetMet').(lagField).(eMet))
                allElectrodeLevelData.(eMet) = [allElectrodeLevelData.(eMet); ...
                    repmat(nan, numElectrodes, 1)];
            else
                allElectrodeLevelData.(eMet) = [allElectrodeLevelData.(eMet); expData.('NetMet').(lagField).(eMet)];
            
            end 
            
           
         end 
     end 
     
     
end

outputDataDateFolder = fullfile(Params.outputDataFolder, ...
        strcat('OutputData',Params.Date));
    

% save recording level data 
allRecordingLevelDataTable = struct2table(allRecordingLevelData);
spreadsheetFname = strcat('NetworkActivity_RecordingLevel', '.csv');
spreadsheetFpath = fullfile(outputDataDateFolder, spreadsheetFname);
writetable(allRecordingLevelDataTable, spreadsheetFpath);

% save electrode level data
allElectrodeLevelDataTable = struct2table(allElectrodeLevelData);
electrodeSpreadsheetFname = strcat('NetworkActivity_NodeLevel','.csv');
electrodeSpreadsheetFpath = fullfile(outputDataDateFolder, electrodeSpreadsheetFname);
writetable(allElectrodeLevelDataTable, electrodeSpreadsheetFpath);




end

