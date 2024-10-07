function combinedData = combineExpNetworkData(ExpName, Params, NetMetricsE, NetMetricsC, experimentMatFileFolder)
% This function collects data from individual experiment analysis files and
% combine them to create a dataset containing all of the metrics from each
% experiment.
% NOTE: This function also saves a csv file
% Parameters
% ----------
% ExpName : cell
% Params : struct
% NetMetricsE : cell 
%   cell where each entry is the name (str) of an electrode-level metric to
%   save
% NetMetricsC : cell 

% NetworkDataFolder : path to directory
% Returns 
% -------
% combinedData : struct 
%     structu containing as fields first the different genotypes / groups, 
%     eg. WT, KO, HET
%     then within each field are the different age groups:
%     WT.TP1, WT.TP2, ... 
%     which in turn contains network level or node level metrics 
%     which are vectors 
%     2023-07-12 Tim : seems to be saving matrices rather than vectors..
%
% Some tidying up of input 

Grps = Params.GrpNm;
AgeDiv = Params.DivNm;
output_spreadsheet_file_type = Params.output_spreadsheet_file_type;
combinedData = struct();

% Also add activeChannel to NetMetricsC
NetMetricsC{end+1} = 'activeChannel';

if strcmp(char(Grps{1}),'HET') && strcmp(char(Grps{2}),'KO') && strcmp(char(Grps{3}),'WT')
   clear Grps
   Grps{1} = 'WT'; Grps{2} = 'HET'; Grps{3} = 'KO';
end


%% Data concerning the entire recording 

combineNetworkData = compileAllExpData(ExpName, experimentMatFileFolder, Params, 'network'); 
combinedData = combineNetworkData;

%% Data concerning single electrodes

combineNodeData = compileAllExpData(ExpName, experimentMatFileFolder, Params, 'node'); 


%% export to spreadsheet (excel or csv)
csv_save_folder = fullfile(Params.outputDataFolder, Params.outputDataFolderName);

if strcmp(output_spreadsheet_file_type, 'csv')
    % make one main table for storing all data 
    main_table = {};  
    n_row = 1; 
end 


% network metrics table
for g = 1:length(Grps)
    eGrp = cell2mat(Grps(g));
    for d = 1:length(AgeDiv)
        eDiv = strcat('TP',num2str(d));
        VNe = strcat(eGrp,'.',eDiv);
        % VNe = eGrp.(eDiv);
        %VNet = strcat('TempStr.',eDiv);
        for l = 1:length(Params.FuncConLagval)
            for e = 1:length(NetMetricsE)
                % Only do the asignment if metricVal is not empty
                %eval(['metricVal' '=' VNe '.' char(NetMetricsE(e)) ';'])
                metricVal = combineNetworkData.(eGrp).(eDiv).(char(NetMetricsE(e)));
                if ~isempty(metricVal)
                    %eval([VNet '.' char(NetMetricsE(e)) '='  'metricVal(:,l);']);
                    if size(metricVal, 2) > 1  % lag dependent metrics
                        TempStr.(eDiv).(char(NetMetricsE(e))) = metricVal(:, l);
                    else
                        % lag-independent metrics
                        TempStr.(eDiv).(char(NetMetricsE(e))) = metricVal(:);
                    end
                else 
                    TempStr.(eDiv).(char(NetMetricsE(e))) = [];
                    % eval([VNet '.' char(NetMetricsE(e)) '='  '0;']);
                end 
                % netMetricToGet = char(NetMetricsE(e));
                % VNet.(netMetricToGet) = VNe.(netMetricToGet)
            end
            % eval(['DatTemp = ' VNet ';']); 
            DatTemp = TempStr.(eDiv);
            if strcmp(output_spreadsheet_file_type, 'csv')
                %numEntries = length(DatTemp.(NetMetricsE{1}));
                DatTempFieldNames = fieldnames(DatTemp);
                numEntries = length(DatTemp.(DatTempFieldNames{1}));
                DatTemp.eGrp = repmat(convertCharsToStrings(eGrp), numEntries, 1);
                DatTemp.AgeDiv = repmat(AgeDiv(d), numEntries, 1);
                DatTemp.Lag = repmat(Params.FuncConLagval(l), numEntries, 1);
                % DatTemp.recordingName = convertCharsToStrings(combineNetworkData.(eGrp).(eDiv).recordingName)';
                if numEntries > 0
                    DatTemp.recordingName = combineNetworkData.(eGrp).(eDiv).recordingName;
                end

                table_obj = struct2table(DatTemp);
                for table_row = 1:numEntries
                    main_table{n_row} = table_obj(table_row, :);
                    n_row = n_row + 1;
                end 
            else
                table_obj = struct2table(DatTemp);
            end 

            if strcmp(output_spreadsheet_file_type, 'excel')
                table_savepath = strcat('NetworkActivity_RecordingLevel_',eGrp,'.xlsx');
                writetable(table_obj, table_savepath, ... 
                    'FileType','spreadsheet','Sheet', ... 
                    strcat('Age',num2str(AgeDiv(d)), ... 
                    'Lag',num2str(Params.FuncConLagval(l)),'ms'));
            end 
        end
    end
end

if strcmp(output_spreadsheet_file_type, 'csv')
    combined_table = vertcat(main_table{:});
    table_savepath = fullfile(csv_save_folder, 'NetworkActivity_RecordingLevel.csv');
    writetable(combined_table, table_savepath);
end 

clear DatTemp TempStr

%% electrode specific
if strcmp(output_spreadsheet_file_type, 'csv')
    % make one main table for storing all data 
    electrode_main_table = {};  
    n_row = 1; 
end 


for g = 1:length(Grps)
    eGrp = cell2mat(Grps(g));
    for d = 1:length(AgeDiv)
        eDiv = strcat('TP',num2str(d));
        % VNe = strcat(eGrp,'.',eDiv);
        % VNet = strcat('TempStr.',eDiv);
        for l = 1:length(Params.FuncConLagval)
            for e = 1:length(NetMetricsC)
                % Only do the assignment if metricVal is not empty 
                % eval(['metricVal' '=' VNe '.' char(NetMetricsC(e)) ';'])
                metricVal = combineNodeData.(eGrp).(eDiv).(char(NetMetricsC(e)));
                if length(metricVal) ~= 0
                    TempStr.(eDiv).(char(NetMetricsC(e))) = metricVal(:, l);
                else 
                    TempStr.(eDiv).(char(NetMetricsC(e))) = [];
                end 
            end
            % eval(['DatTemp = ' VNet ';']);
            DatTemp = TempStr.(eDiv);
            
           if strcmp(output_spreadsheet_file_type, 'csv')
                DatTempFieldNames = fieldnames(DatTemp);
                numEntries = length(DatTemp.(DatTempFieldNames{1}));
                DatTemp.eGrp = repmat(convertCharsToStrings(eGrp), numEntries, 1);
                DatTemp.AgeDiv = repmat(AgeDiv(d), numEntries, 1);
                DatTemp.Lag = repmat(Params.FuncConLagval(l), numEntries, 1);
                % DatTemp.recordingName = convertCharsToStrings(combinedData.(eGrp).(eDiv).recordingNamePerElectrode)';
                % DatTemp.Channel = combinedData.(eGrp).(eDiv).Channel(:); % [allElectrodeLevelData.Channel; expData.Info.channels(nodeIndices)'];
                if numEntries > 0
                    DatTemp.recordingName = combineNodeData.(eGrp).(eDiv).recordingNamePerElectrode;
                else 
                    DatTemp.recordingName = [];
                end 
                % 2024-10-05 : checking for empty recordingName, to
                % indicate inactive node
                if ~isempty(DatTemp.recordingName)
                    electrode_table_obj = struct2table(DatTemp);
                    for table_row = 1:numEntries
                        electrode_main_table{n_row} = electrode_table_obj(table_row, :);
                        n_row = n_row + 1;
                    end 
                end 
            else
                electrode_table_obj = struct2table(DatTemp);
            end 


            if strcmp(output_spreadsheet_file_type, 'excel')
                writetable(electrode_table_obj, ... 
                    strcat('NetworkActivity_NodeLevel_',eGrp,'.xlsx'),... 
                    'FileType','spreadsheet','Sheet',strcat('Age',num2str(AgeDiv(d)), ...
                    'Lag',num2str(Params.FuncConLagval(l)),'ms'));
            end 

        end
    end
end


if strcmp(output_spreadsheet_file_type, 'csv')
    electrode_combined_table = vertcat(electrode_main_table{:});
    electrode_table_savepath = fullfile(csv_save_folder, 'NetworkActivity_NodeLevel.csv');
    writetable(electrode_combined_table, electrode_table_savepath);
end 


clear DatTemp TempStr



end 