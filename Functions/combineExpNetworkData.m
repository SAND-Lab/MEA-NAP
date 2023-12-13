function combinedData = combineExpNetworkData(ExpName, Params, NetMetricsE, NetMetricsC, experimentMatFileFolder, NetworkDataFolder)
% This function collects data from individual experiment analysis files and
% combine them to create a dataset containing all of the metrics from each
% experiment.

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


if strcmp(char(Grps{1}),'HET') && strcmp(char(Grps{2}),'KO') && strcmp(char(Grps{3}),'WT')
   clear Grps
   Grps{1} = 'WT'; Grps{2} = 'HET'; Grps{3} = 'KO';
end


%% Data concerning the entire recording 

% initialise the structure to store data
for g = 1:length(Grps)
    % create structure for each group
    VN1 = cell2mat(Grps(g));
    % eval([VN1 '= [];']);
    combinedData.(VN1) = [];
    
    % add substructure for each DIV range
    for d = 1:length(AgeDiv)
        VN2 = strcat('TP',num2str(d));
        
        % add variable name
        for e = 1:length(NetMetricsE)
            VN3 = cell2mat(NetMetricsE(e));
            % eval([VN1 '.' VN2 '.' VN3 '= [];']);
            combinedData.(VN1).(VN2).(VN3) = [];
            
            clear VN3
        end
        clear VN2
    end
    clear VN1
end

% allocate numbers to relevant matrices
for i = 1:length(ExpName)
     % Exp = strcat(char(ExpName(i)),'_',Params.Date,'.mat');
     Exp = char(ExpName(i));

     % if previously used showOneFig, then this prevents saved oneFigure 
     % handle from showing up when loading the matlab variable
     if Params.showOneFig 
         % Make it so figure handle in oneFigure don't appear
         set(0, 'DefaultFigureVisible', 'off')
     end 
    
     % ExpFilePath = fullfile(NetworkDataFolder, Exp);
     ExpFPathSearchName = dir(fullfile(experimentMatFileFolder, [Exp, '*.mat'])).name;
     ExpFpath = fullfile(experimentMatFileFolder, ExpFPathSearchName);
     ExpData = load(ExpFpath); % mat file contains Info, NetMet 
    
     % TODO: no need loop here I think
     for g = 1:length(Grps)
         if strcmp(cell2mat(Grps(g)),cell2mat(ExpData.Info.Grp))
             eGrp = cell2mat(Grps(g));
         end       
     end
     for d = 1:length(AgeDiv)
         if cell2mat(ExpData.Info.DIV) == AgeDiv(d)
             eDiv = strcat('TP',num2str(d));
         end    
     end
     for e = 1:length(NetMetricsE)
            eMet = cell2mat(NetMetricsE(e));
            groupTypeCounter = size(combinedData.(eGrp).(eDiv).(eMet), 1); % count occurences of a specific Grp-DIV
            for l = 1:length(Params.FuncConLagval)
                %VNs = strcat('NetMet.adjM',num2str(Params.FuncConLagval(l)),'mslag.',eMet);
                %eval(['DatTemp(l) =' VNs ';']);
                lagValStr = strcat('adjM', num2str(Params.FuncConLagval(l)),'mslag');
                % DatTemp(l) = NetMet.(lagValStr).(eMet);
                if isfield(ExpData.NetMet.(lagValStr), eMet)  % this is to exclude small networks where NCpn1 is not defined
                    combinedData.(eGrp).(eDiv).(eMet)(groupTypeCounter+1, l) = ExpData.NetMet.(lagValStr).(eMet);
                end 
                %clear VNs
            end
            %VNe = strcat(eGrp,'.',eDiv,'.',eMet);
            %eval([VNe '= [' VNe '; DatTemp];']);
            % combinedData.(eGrp).(eDiv).(eMet)(i, l) = NetMet.(lagValStr).(eMet);
            % clear DatTemp
     end
     
     % add recording name 
     fileNameSplit = split(Exp, '_');
     recordingName = join(fileNameSplit(1:end-1), '_');
     combinedData.(eGrp).(eDiv).recordingName{groupTypeCounter+1} = recordingName{1};
end

%% Data concerning single electrodes

% initialise structures
for g = 1:length(Grps)
    % create structure for each group
    VN1 = cell2mat(Grps(g));

    % add substructure for each DIV range
    for d = 1:length(AgeDiv)
        VN2 = strcat('TP',num2str(d));
        
        % add variable name
        for e = 1:length(NetMetricsC)
            VN3 = cell2mat(NetMetricsC(e));
            eval([VN1 '.' VN2 '.' VN3 '= [];']);
            combinedData.(VN1).(VN2).(VN3) = [];
            clear VN3
        end
        clear VN2
    end
    clear VN1
end

% allocate numbers to relevant matrices
for i = 1:length(ExpName)
     % Exp = strcat(char(ExpName(i)),'_',Params.Date,'.mat');
     Exp = char(ExpName(i));
     
     groupTypeCounterElectrode = 1;
     % if previously used showOneFig, then this prevents saved oneFigure 
     % handle from showing up when loading the matlab variable
     if Params.showOneFig 
         % Make it so figure handle in oneFigure don't appear
         set(0, 'DefaultFigureVisible', 'off')
     end 
     % ExpFilePath = fullfile(NetworkDataFolder, Exp);
     ExpFPathSearchName = dir(fullfile(experimentMatFileFolder, [Exp, '*.mat'])).name;
     ExpFpath = fullfile(experimentMatFileFolder, ExpFPathSearchName);
     
     ExpData = load(ExpFpath);
     for g = 1:length(Grps)
         if strcmp(cell2mat(Grps(g)),cell2mat(ExpData.Info.Grp))
             eGrp = cell2mat(Grps(g));
         end       
     end
     for d = 1:length(AgeDiv)
         if cell2mat(ExpData.Info.DIV) == AgeDiv(d)
             eDiv = strcat('TP',num2str(d));
         end    
     end
     
     

     for e = 1:length(NetMetricsC)
            eMet = cell2mat(NetMetricsC(e));
            DatTemp = cell(length(Params.FuncConLagval), 1);
            mL = zeros(length(Params.FuncConLagval), 1);
            for l = 1:length(Params.FuncConLagval)
                % VNs = strcat('NetMet.adjM',num2str(Params.FuncConLagval(l)),'mslag.',eMet);
                lagValStr = strcat('adjM', num2str(Params.FuncConLagval(l)),'mslag');
                
                % DatTemp = ExpData.NetMet.(lagValStr).(eMet);

                % eval(['DatTemp' num2str(l) '= ' VNs ';']);
                % metric should be nNode x 1, for some reason sometimes
                % it's transposed...
                metricVector = ExpData.NetMet.(lagValStr).(eMet);                
                DatTemp{l} = metricVector;
                
                % eval(['DatTemp' num2str(l) '= ' VNs ';']);
                % eval(['mL(l) = length(DatTemp' num2str(l) ');']);
                mL(l) = length(DatTemp{l});

                % clear VNs
            end
            % This is using the maximum number of nodes per recording
            % And filling data with fewer nodes than that with NaNs 
            % so that the node metric has the same size in all lags
            for l = 1:length(Params.FuncConLagval)
                % eval(['DatTempT = DatTemp' num2str(l) ';']);
                DatTempT = DatTemp{l};
                if length(DatTempT) < max(mL)
                    DatTempT(length(DatTempT+1):max(mL)) = nan;
                end
                
                if size(DatTempT, 1) == 1
                    DatTempT = DatTempT';
                end 
                
                % DatTemp(:,l) = DatTempT;
                DatTemp{l} = DatTempT; 
            end
            
            % Convert from cell back to matrix 
            DatTemp = cell2mat(DatTemp');
            % VNe = strcat(eGrp,'.',eDiv,'.',eMet);
            % eval([VNe '= [' VNe '; DatTemp];']);

            % Append to vector in field 
            combinedData.(eGrp).(eDiv).(eMet) = [combinedData.(eGrp).(eDiv).(eMet); DatTemp];
            clear DatTemp
     end
     
     % add recording name 
     % TODO: have not tested this yet...
     fileNameSplit = split(Exp, '_');
     recordingName = join(fileNameSplit(1:end-1), '_');
     numElectrode = length(combinedData.(eGrp).(eDiv).(eMet));
     combinedData.(eGrp).(eDiv).recordingNamePerElectrode(groupTypeCounterElectrode:groupTypeCounterElectrode+numElectrode-1) = repmat(recordingName, numElectrode, 1);
     groupTypeCounterElectrode = groupTypeCounterElectrode + numElectrode;
     
     clear Info NetMet adjMs
end

%% export to spreadsheet (excel or csv)
csv_save_folder = fullfile(Params.outputDataFolder, strcat('OutputData', Params.Date));

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
                metricVal = combinedData.(eGrp).(eDiv).(char(NetMetricsE(e)));
                if ~isempty(metricVal)
                    %eval([VNet '.' char(NetMetricsE(e)) '='  'metricVal(:,l);']);
                    TempStr.(eDiv).(char(NetMetricsE(e))) = metricVal(:, l);
                else 
                    TempStr.(eDiv).(char(NetMetricsE(e))) = 0;
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
                DatTemp.recordingName = convertCharsToStrings(combinedData.(eGrp).(eDiv).recordingName)';

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
                metricVal = combinedData.(eGrp).(eDiv).(char(NetMetricsC(e)));
                if length(metricVal) ~= 0
                    % eval([VNet '.' char(NetMetricsC(e)) '=' 'metricVal(:,l);']);
                    TempStr.(eDiv).(char(NetMetricsC(e))) = metricVal(:, l);
                else 
                    % eval([VNet '.' char(NetMetricsC(e)) '=' '0']);
                    TempStr.(eDiv).(char(NetMetricsC(e))) = 0;
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
                DatTemp.recordingName = convertCharsToStrings(combinedData.(eGrp).(eDiv).recordingNamePerElectrode)';
                electrode_table_obj = struct2table(DatTemp);
                for table_row = 1:numEntries
                    electrode_main_table{n_row} = electrode_table_obj(table_row, :);
                    n_row = n_row + 1;
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