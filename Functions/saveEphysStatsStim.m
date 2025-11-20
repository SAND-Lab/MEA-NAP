function saveEphysStatsStim(ExpName, Params)
% Saves stimulation activity data to CSV files
% One csv contains node level metrics : StimActivity_NodeLevel
% INPUT 
% -----
% ExpName : cell array 
%      cell array with size N x 1 where N is the number of recordings 
%      each entry is the name of a recording file without the extension 
%      eg. MPT_220603_10A_DIV14
% Params : struct
%      Parameter structure 

%% Variable names for stimulation analysis

% Node-level metrics (1 value per electrode per pattern)
StimMetricsC = {'channel_id', 'file_index', 'pattern_id', ...
                'auc_response', 'auc_baseline_mean', 'auc_corrected', ...
                'peak_firing_rate_hz', 'peak_time_ms', 'halfRmax_time_ms', ...
                'd_prime', 'zscore', 'psth_window_s'};

%% Import data from all experiments

experimentMatFolderPath = fullfile(Params.outputDataFolder, ...
        Params.outputDataFolderName, 'ExperimentMatFiles');

allStimNodeLevelData = struct();

% Initialize metadata fields
allStimNodeLevelData.FileName = {};
allStimNodeLevelData.Grp = {};
allStimNodeLevelData.DIV = [];

% Initialize metric fields
for metricIdx = 1:length(StimMetricsC)
    metricName = StimMetricsC{metricIdx};
    allStimNodeLevelData.(metricName) = [];
end

% Process each experiment
for i = 1:length(ExpName)
    Exp = strcat(char(ExpName(i)),'_',Params.outputDataFolderName,'.mat');
    ExpFilePath = fullfile(experimentMatFolderPath, Exp);
    
    % Check if file exists and contains stimData
    if ~exist(ExpFilePath, 'file')
        fprintf('Warning: Experiment file not found: %s\n', ExpFilePath);
        continue;
    end
    
    % Load experiment data
    expData = load(ExpFilePath);
    
    % Check if stimData exists
    if ~isfield(expData, 'stimData')
        fprintf('Warning: No stimData found in %s\n', ExpFilePath);
        continue;
    end
    
    % Get the number of patterns for this experiment
    stimDataFields = fieldnames(expData.stimData);
    patternFields = stimDataFields(startsWith(stimDataFields, 'electrodeLevelResponse_pattern_'));
    
    % Process each pattern
    for patternFieldIdx = 1:length(patternFields)
        patternFieldName = patternFields{patternFieldIdx};
        patternData = expData.stimData.(patternFieldName);
        
        % Get number of electrodes for this pattern
        numElectrodes = length(patternData);
        
        if numElectrodes == 0
            continue;
        end
        
        % Add metadata for each electrode
        allStimNodeLevelData.FileName = [allStimNodeLevelData.FileName; ...
                                         repmat({expData.Info.FN{1}}, numElectrodes, 1)];
        allStimNodeLevelData.Grp = [allStimNodeLevelData.Grp; ...
                                    repmat({expData.Info.Grp{1}}, numElectrodes, 1)];
        allStimNodeLevelData.DIV = [allStimNodeLevelData.DIV; ...
                                    repmat(expData.Info.DIV{1}, numElectrodes, 1)];
        
        % Extract and append electrode-level metrics
        for metricIdx = 1:length(StimMetricsC)
            metricName = StimMetricsC{metricIdx};
            
            % Extract metric values for all electrodes in this pattern
            metricValues = [];
            for elecIdx = 1:numElectrodes
                if isfield(patternData(elecIdx), metricName)
                    metricValues = [metricValues; patternData(elecIdx).(metricName)];
                else
                    metricValues = [metricValues; NaN];
                end
            end
            
            % Append to accumulated data
            allStimNodeLevelData.(metricName) = [allStimNodeLevelData.(metricName); metricValues];
        end
    end
end

%% Save node level data to CSV
outputDataDateFolder = fullfile(Params.outputDataFolder, ...
        Params.outputDataFolderName);

% Create output directory if it doesn't exist
if ~exist(outputDataDateFolder, 'dir')
    mkdir(outputDataDateFolder);
end

% Convert to table and save
allStimNodeLevelDataTable = struct2table(allStimNodeLevelData);
stimSpreadsheetFname = 'StimActivity_NodeLevel.csv';
stimSpreadsheetFpath = fullfile(outputDataDateFolder, stimSpreadsheetFname);
writetable(allStimNodeLevelDataTable, stimSpreadsheetFpath);

fprintf('Stimulation activity data saved to: %s\n', stimSpreadsheetFpath);

end
