%% Load data

% expData = load('D:\MEA-NAP\OutputData14Apr2025(AllPolled&Truncated)\ExperimentMatFiles\OPME231206_11_20231220_P1_pup2E_Het_MOI50000_DIV14_OutputData14Apr2025.mat');
% NetMet = getNodeCartGroup(expData.NetMet, expData.Params);


%% Go through a folder and generate csv

expMatFolder = '"D:\MEA-NAP\OutputData26Apr2025(ProbThresh)\ExperimentMatFiles"';
csvSavePath = 'D:\MEA-NAP\OutputData26Apr2025(ProbThresh)\NCnodes.csv';


matFpaths = dir(fullfile(expMatFolder, '*.mat'));

% initialise structure that we are going to turn into
% a table, and later save as a csv
dataStruct = struct();
dataStruct.recordingName = {};
dataStruct.Group = {};
dataStruct.AgeDiv = [];
dataStruct.Lag = [];
dataStruct.Channel = [];
dataStruct.NodeCartographyGroup = [];


for fileIdx = 1:length(matFpaths)
    fname = matFpaths(fileIdx).name;
    fpath = fullfile(expMatFolder, fname);
    expData = load(fpath);
    NetMet = getNodeCartGroup(expData.NetMet, expData.Params);

    FN = expData.Info.FN;
    Grp = expData.Info.Grp;
    AgeDiv = expData.Info.DIV{1};
    lagVals = expData.Params.FuncConLagval;

    for lagIdx = 1:length(lagVals)

        lagUsed = lagVals(lagIdx);
        lagFieldName = sprintf('adjM%.fmslag', lagUsed);
        NetMetWlag = NetMet.(lagFieldName);
        numNodes = length(NetMetWlag.activeChannel);

        dataStruct.recordingName = [dataStruct.recordingName;
            repmat(FN, numNodes, 1)];
        dataStruct.Group = [dataStruct.Group;
            repmat(Grp, numNodes, 1)];
        dataStruct.AgeDiv = [dataStruct.AgeDiv;
            repmat(AgeDiv, numNodes, 1)];
        dataStruct.Lag = [dataStruct.Lag;
            repmat(lagUsed, numNodes, 1)];
        dataStruct.Channel = [dataStruct.Channel;
            NetMetWlag.activeChannel'];
        dataStruct.NodeCartographyGroup = [dataStruct.NodeCartographyGroup;
            NetMetWlag.nodeCartGrp];

    end



end

table_obj = struct2table(dataStruct);
writetable(table_obj, csvSavePath);
fprintf('Saved NCnodes CSV with NetMet NC to: %s\n', csvSavePath);

%% Add CellType columns for each node for that csv
% === CONFIG ===
ncCsvPath = 'D:\MEA-NAP\OutputData26Apr2025(ProbThresh)\NCnodes.csv';
cellTypecsvFolder = 'Z:\Yin (yy433)\StatisticalTest\splitNPY\CellType_Priority1&2By20250505';
outputCsvPath = 'D:\MEA-NAP\OutputData26Apr2025(ProbThresh)\NC_CellType.csv';

% Path to save the unmatched log
logFilePath = 'D:\MEA-NAP\OutputData26Apr2025(ProbThresh)\Missing IDs from CellTypeCSVFile unmatched to MEANAPchannels.txt';
% Delete the log file if it already exists
if exist(logFilePath, 'file')
    delete(logFilePath);
end

% === Step 1: Load NCnodes ===
ncTable = readtable(ncCsvPath);

% Step 1.2: Initialize new columns
ncTable.Mecp2CellTypeID = nan(height(ncTable), 1);
ncTable.Mecp2CellType = repmat({'Unknown'}, height(ncTable), 1);

% Step 2: Compute Mecp2CellTypeID = Channel - 1
ncTable.Mecp2CellTypeID = ncTable.Channel - 1;

% === Step 3: Get unique recordings and loop ===
recordingNames = unique(ncTable.recordingName);

% Open the file for writing the unmatched IDs
fid = fopen(logFilePath, 'w');  % Open the log file in write mode to create a new file

for i = 1:length(recordingNames)
    recName = recordingNames{i};
    cellTypeCsvFile = fullfile(cellTypecsvFolder, [recName, '.csv']);

    if isfile(cellTypeCsvFile)
        cellTypeTable = readtable(cellTypeCsvFile, 'VariableNamingRule', 'preserve');

        % Step 4: Check for relevant columns
        if ismember('Mecp2_Positive', cellTypeTable.Properties.VariableNames) && ...
                ismember('Mecp2_Negative', cellTypeTable.Properties.VariableNames)

            posIDs = cellTypeTable.Mecp2_Positive(~isnan(cellTypeTable.Mecp2_Positive));
            negIDs = cellTypeTable.Mecp2_Negative(~isnan(cellTypeTable.Mecp2_Negative));

            % Step 5: Find rows in ncTable for this recording
            matchIdx = strcmp(ncTable.recordingName, recName);

            % Step 5: Match rows in ncTable for this recording
            recIndices = find(strcmp(ncTable.recordingName, recName));
            recIDs = ncTable.Mecp2CellTypeID(recIndices);

            % Keep track of matched IDs
            matchedPos = ismember(posIDs, recIDs);
            matchedNeg = ismember(negIDs, recIDs);

            % Loop and assign types
            for j = 1:length(recIndices)
                idx = recIndices(j);
                id = ncTable.Mecp2CellTypeID(idx);

                if any(posIDs == id)
                    ncTable.Mecp2CellType{idx} = 'Mecp2_Positive';
                elseif any(negIDs == id)
                    ncTable.Mecp2CellType{idx} = 'Mecp2_Negative';
                end
            end

            % Warn if any IDs in CSV file weren't matched
            unmatchedPos = posIDs(~matchedPos);
            unmatchedNeg = negIDs(~matchedNeg);
            if ~isempty(unmatchedPos)
                fprintf('⚠️  %s: %d Mecp2_Positive IDs not matched: [%s]\n', ...
                    recName, numel(unmatchedPos), num2str(unmatchedPos'));
            end
            if ~isempty(unmatchedNeg)
                fprintf('⚠️  %s: %d Mecp2_Negative IDs not matched: [%s]\n', ...
                    recName, numel(unmatchedNeg), num2str(unmatchedNeg'));
            end
            % Save the unmatched log
            fid = fopen(logFilePath, 'a');  % Append mode
            if fid == -1
                warning('Could not open file for writing unmatched IDs log.');
            else
                if ~isempty(unmatchedPos)
                    fprintf(fid, '%s: %d Mecp2_Positive IDs not matched: [%s]\n', ...
                        recName, numel(unmatchedPos), num2str(unmatchedPos'));
                end
                if ~isempty(unmatchedNeg)
                    fprintf(fid, '%s: %d Mecp2_Negative IDs not matched: [%s]\n', ...
                        recName, numel(unmatchedNeg), num2str(unmatchedNeg'));
                end
                fclose(fid);
            end

        else
            warning('Missing Mecp2_Positive or Mecp2_Negative columns in file: %s', cellTypeCsvFile);
        end
        % else
        %     warning('Cell type file not found for: %s', recName);
    end
end

% === Step 6: Save the updated table ===
writetable(ncTable, outputCsvPath);
fprintf('Saved updated CSV with Mecp2 info to: %s\n', outputCsvPath);
