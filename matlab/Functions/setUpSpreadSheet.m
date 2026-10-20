% This script imports data about the recordings ("meta-data") from csv /
% excel files to the matlab variables

if strcmp(spreadsheet_file_type, 'excel')
    [num,txt,~] = xlsread(spreadsheet_filename,sheet,xlRange);
    ExpName = txt(:,1); % name of recording
    ExpGrp = txt(:,3); % name of experimental group
    ExpDIV = num(:,1); % DIV number
elseif strcmp(spreadsheet_file_type, 'csv')
    opts = detectImportOptions(spreadsheet_filename);
    opts.Delimiter = ',';
    opts.VariableNamesLine = 1;
    opts.VariableTypes{1} = 'char';  % this should be the recoding file name
    opts.VariableTypes{2} = 'double';  % this should be the DIV
    opts.VariableTypes{3} = 'char'; % this should be Group 
    if length(opts.VariableNames) > 3
        opts.VariableTypes{4} = 'char'; % this should be Ground
    end 
    
    if length(opts.VariableNames) > 4
        opts.VariableTypes{5} = 'char'; % this should be channelLayout
    end 
    
    opts.DataLines = csvRange; % read the data in the range [StartRow EndRow]
    % csv_data = readtable(spreadsheet_filename, 'Delimiter','comma');
    
    % We will modify the column headers so that they are valid matlab
    % variable names (and so we will suppress the warning for that)
    opts.VariableNamingRule = 'modify';
    warning('OFF', 'MATLAB:table:ModifiedAndSavedVarnames')
    
    csv_data = readtable(spreadsheet_filename, opts);
    
    
    ExpName = csv_data{:, 1};
    ExpGrp = csv_data{:, 3};
    ExpDIV = csv_data{:, 2};

    Params.electrodesToGroundPerRecordingUseName = 1;  % use name (instead of index) to ground electrodes

    if sum(strcmp('Ground',csv_data.Properties.VariableNames))
        Params.electrodesToGroundPerRecording = csv_data.('Ground'); % this should be a 1 x N cell array 
        if ~iscell(Params.electrodesToGroundPerRecording)
            Params.electrodesToGroundPerRecording = {Params.electrodesToGroundPerRecording};
        end 
    else 
        Params.electrodesToGroundPerRecording = [];
    end 
    
    if 1 - sum(strcmp('ChannelLayout', csv_data.Properties.VariableNames))
        Params.channelLayoutPerRecording = cellstr(repmat(Params.channelLayout, size(csv_data, 1), 1));
    else
        Params.channelLayoutPerRecording = csv_data.('ChannelLayout');
    end
    
    % Get coords and channels for each recording 
    if Params.priorAnalysis == 1
        prevParamFpath = fullfile(Params.priorAnalysisFolderName, Params.priorAnalysisSubFolderName, ...
            sprintf('Parameters_%s.mat', Params.priorAnalysisSubFolderName));
        prevParamFpathFound = isfile(prevParamFpath);
    else 
        prevParamFpathFound = 0;
    end 

    if Params.priorAnalysis == 0 && (Params.suite2pMode == 0)
        Params.channels = {};
        Params.coords = {};
        for nRecording = 1:size(csv_data, 1)
            [channels, coords] = getCoordsFromLayout(Params.channelLayoutPerRecording{nRecording});
            recordingChannelData = load(fullfile(rawData, [ExpName{nRecording} '.mat']), 'channels');
            recordingChannels = recordingChannelData.channels;
            subsetIndex = find(ismember(channels, recordingChannels));
            Params.channels{nRecording} = recordingChannels;
            Params.coords{nRecording} = coords(subsetIndex, :);
        end
    elseif (prevParamFpathFound == 1)
        prevParamData = load(prevParamFpath);
        Params.channels = prevParamData.Params.channels;
        Params.coords = prevParamData.Params.coords;
    else 
        % TODO: read channels and coordinates from spike detected data
        todo = 1;
    end
    
    % Ensure channels and coordinates are cell (old versions of MEANAP have
    % them as matrices)
    if ~iscell(Params.channels)
        channels = Params.channels; 
        coords = Params.coords;
        Params.channels = {};
        Params.coords = {};
        for nRecording = 1:size(csv_data, 1)
            Params.channels{nRecording} = channels;
            Params.coords{nRecording} = coords;
        end
    end
    
end 