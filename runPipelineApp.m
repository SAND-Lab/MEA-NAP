%% Script to run pipeline app and propagate settings back to Params
clear app
app = AnalysisPipelineApp;
app.PipelineStatusTextArea.Value = {'Welcome!, Analysis Pipeline GUI is launched'};
app.colorUITable.Data = [ ...
   1, 0.996, 0.670, 0.318; ...
   2, 0.780, 0.114, 0.114; ... 
   3, 0.459, 0.000, 0.376; ...  
   4, 0.027, 0.306, 0.659; ...
   5, 0.5, 0.5, 0.5; ...
   6, 0, 0, 0; ...
   7, 0, 0, 0; ...
   8, 0, 0, 0; ...
   9, 0, 0, 0; ...
   10, 0, 0, 0; ...
];
app.colorUITable.ColumnEditable = [true, true, true, true];

% get Original parents to hide/show them later 
advancedSpikeDetectionTabParent = app.AdvancedSpikeDetectionTab.Parent;
advancedBurstDetectionTabParent = app.AdvancedBurstDetectionTab.Parent; 
advancedDimensionalityTabParent = app.AdvancedDimensionalityTab.Parent; 
colorsTabParent = app.ColorsTab.Parent; 
artifactRemovalTabParent = app.ArtifactRemovalTab.Parent; 
multipleTemplatesTabParent = app.MultipleTemplatesTab.Parent;
advancedConnectivityTabParent = app.AdvancedConnectivityTab.Parent;
nodeCartographyTabParent = app.NodeCartographyTab.Parent;

while app.RunPipelineButton.Value == 0

    % previous analysis fields
    if app.UsePreviousAnalysisCheckBox.Value == 0
        app.PreviousAnalysisDateEditField.Enable = 'Off';
        app.PreviousAnalysisDateEditFieldLabel.Enable = 'Off';
        app.PreviousAnalysisFolderEditField.Enable = 'Off';
        app.PreviousAnalysisFolderEditFieldLabel.Enable = 'Off';
        app.SpikeDataFolderEditField.Enable = 'Off';
        app.SpikeDataFolderEditFieldLabel.Enable = 'Off';
        app.PrevAnalysisSelectButton.Enable = 'Off';
        app.SpikeDataSelectButton.Enable = 'Off';
    else
        app.PreviousAnalysisDateEditField.Enable = 'On';
        app.PreviousAnalysisDateEditFieldLabel.Enable = 'On';
        app.PreviousAnalysisFolderEditField.Enable = 'On';
        app.PreviousAnalysisFolderEditFieldLabel.Enable = 'On';
        app.SpikeDataFolderEditField.Enable = 'On';
        app.SpikeDataFolderEditFieldLabel.Enable = 'On';
        app.PrevAnalysisSelectButton.Enable = 'On';
        app.SpikeDataSelectButton.Enable = 'On';
    end 
    
    % check whether to show advanced settings
    if app.ShowAdvancedSettingsCheckBox.Value == 1
        % Tabs
        app.AdvancedSpikeDetectionTab.Parent = advancedSpikeDetectionTabParent;
        app.AdvancedBurstDetectionTab.Parent = advancedBurstDetectionTabParent;
        app.AdvancedDimensionalityTab.Parent = advancedDimensionalityTabParent;
        app.ColorsTab.Parent = colorsTabParent; 
        app.ArtifactRemovalTab.Parent = artifactRemovalTabParent;
        app.MultipleTemplatesTab.Parent = multipleTemplatesTabParent;
        app.AdvancedConnectivityTab.Parent = advancedConnectivityTabParent;
        app.NodeCartographyTab.Parent = nodeCartographyTabParent;
        % Not Tabs
        app.MinimumnodesizeEditField.Visible = 'on';
        app.MinimumnodesizeEditFieldLabel.Visible = 'on';
        app.KDEwidthforonepointEditField.Visible = 'on';
        app.KDEwidthforonepointEditFieldLabel.Visible = 'on';
        app.KDEHeightEditField.Visible = 'on';
        app.KDEHeightEditFieldLabel.Visible = 'on';
        app.ShadeMetricDropDown.Visible = 'on';
        app.ShadeMetricDropDownLabel.Visible = 'on';
    else
        app.AdvancedSpikeDetectionTab.Parent = [];
        app.AdvancedBurstDetectionTab.Parent = [];
        app.AdvancedDimensionalityTab.Parent = [];
        app.ColorsTab.Parent = [];
        app.ArtifactRemovalTab.Parent = [];
        app.MultipleTemplatesTab.Parent = [];
        app.AdvancedConnectivityTab.Parent = [];
        app.NodeCartographyTab.Parent = [];
        % Not Tabs 
        app.MinimumnodesizeEditField.Visible = 'off';
        app.MinimumnodesizeEditFieldLabel.Visible = 'off';
        app.KDEwidthforonepointEditField.Visible = 'off';
        app.KDEwidthforonepointEditFieldLabel.Visible = 'off';
        app.KDEHeightEditField.Visible = 'off';
        app.KDEHeightEditFieldLabel.Visible = 'off';
        app.ShadeMetricDropDown.Visible = 'off';
        app.ShadeMetricDropDownLabel.Visible = 'off';
    end 

    % check if all required parameters are set
    homeDirSet = 1 - isempty(app.HomeDirectoryEditField.Value);
    spreadsheetSet = 1 - isempty(app.SpreadsheetfilenameEditField.Value);
    
    if homeDirSet && spreadsheetSet
        app.AllrequiredparameterssetLamp.Color = [0 1 0];
    else
        app.AllrequiredparameterssetLamp.Color = [1 0 0];
    end

    % Load HomeDir 
    if app.HomeDirSelectButton.Value == 1
        app.HomeDirectoryEditField.Value = uigetdir;
        app.HomeDirSelectButton.Value = 0;
        figure(app.UIFigure)  % put app back to focus
    end 

    % Load Output Data Folder
    if app.OutputDataSelectButton.Value == 1
        app.OutputDataFolderEditField.Value = uigetdir;
        app.OutputDataSelectButton.Value = 0;
        figure(app.UIFigure)  % put app back to focus
    end 

    % Load raw data folder 
    if app.RawDataSelectButton.Value == 1
        app.RawDataFolderEditField.Value = uigetdir;
        app.RawDataSelectButton.Value = 0;
        figure(app.UIFigure)  % put app back to focus
    end 
    
    % Load CSV
    if app.SpreadsheetSelectButton.Value == 1
         [spreadsheetFilename, spreadsheetFolder] = uigetfile('.csv');
         spreadsheetFilePath = fullfile(spreadsheetFolder, spreadsheetFilename);
         app.SpreadsheetfilenameEditField.Value = spreadsheetFilePath;
         app.SpreadsheetSelectButton.Value = 0;        
         figure(app.UIFigure)  % put app back to focus
         
         % load csv to check if everything is alright 
         csvRange = str2num(app.CSVRangeEditField.Value);
         csv_data = pipelineReadCSV(spreadsheetFilePath, csvRange);
         app.PipelineStatusTextArea.Value = [app.PipelineStatusTextArea.Value; 'Loaded spreadsheet succesfully!'];
         app.PipelineStatusTextArea.Value = [app.PipelineStatusTextArea.Value; sprintf('Your data has %.f rows', size(csv_data, 1))];
         app.PipelineStatusTextArea.Value = [app.PipelineStatusTextArea.Value; 'And columns with names:'];
         app.PipelineStatusTextArea.Value = [app.PipelineStatusTextArea.Value; strjoin(csv_data.Properties.VariableNames, ', ')];
    end
    
    % Load previous analysis folder 
    if app.PrevAnalysisSelectButton.Value == 1
        app.PreviousAnalysisFolderEditField.Value = uigetdir;
        app.PrevAnalysisSelectButton.Value = 0;
        figure(app.UIFigure)  % put app back to focus
    end 
    
    % Previous Spike Data Folder 
    if app.SpikeDataSelectButton.Value == 1 
        app.SpikeDataFolderEditField.Value = uigetdir;
        app.SpikeDataSelectButton.Value = 0;
        figure(app.UIFigure)  % put app back to focus
    end 
    
    % check if load parameters button is pressed
    if app.LoadParametersButton.Value == 1
        [ParamsFileName, ParamsFilePath] = uigetfile('.mat');
        app.LoadParametersButton.Value = 0;
        figure(app.UIFigure)  % put app back to focus
        load(fullfile(ParamsFilePath, ParamsFileName));
        app = setAppParams(app, Params);
        app.PipelineStatusTextArea.Value = [app.PipelineStatusTextArea.Value; 'Loaded parameters from:'];
        app.PipelineStatusTextArea.Value = [app.PipelineStatusTextArea.Value; fullfile(ParamsFilePath, ParamsFileName)];
    end 


    if app.SaveParametersButton.Value == 1
        Params = getParamsFromApp(app);
        currDateTime = string(datetime);
        currDateTime = strrep(currDateTime, ' ', '-');
        currDateTime = strrep(currDateTime, ':', '-');
        [ParamName,ParamPath,indx] = uiputfile(sprintf('MEANAP-Params-%s.mat', currDateTime));
        ParamsSavePath = fullfile(ParamPath, ParamName);
        % ParamsSavePath = strcat('MEANAP-Params-', currDateTime, '.mat');
        save(ParamsSavePath, 'Params');
        app.PipelineStatusTextArea.Value = [app.PipelineStatusTextArea.Value; 'Saved parameters to:'];
        app.PipelineStatusTextArea.Value = [app.PipelineStatusTextArea.Value; ParamsSavePath];
        app.SaveParametersButton.Value = 0;
    end 

    pause(0.1)
end 

%% Moving settings to Params
Params = getParamsFromApp(app);


Params.outputDataFolder = app.OutputDataFolderEditField.Value;
Params.rawData = app.RawDataFolderEditField.Value;
Params.priorAnalysisPath = app.PreviousAnalysisFolderEditField.Value;
Params.spikeDetectedData = app.SpikeDataFolderEditField.Value;

Params.guiMode = 1;

% some workspace varaibles 
HomeDir = Params.HomeDir;  % TODO: just put this to Params
spreadsheet_filename = Params.spreadSheetFileName;
rawData = Params.rawData;

%% Some stuff that were dealt with previously in biAdvancedSettings 
if any(isnan(Params.outputDataFolder)) || isempty(Params.outputDataFolder)
    Params.outputDataFolder = HomeDir;
end 

% TODO: move this to a function 
if strcmp(Params.channelLayout, 'MCS60old')

    channels = [11, 12, 13, 14, 15, 16, 17, 18, ... 
            21, 22, 23, 24, 25, 26, 27, 28, ...
            31, 32, 33, 34, 35, 36, 37, 38, ...
            41, 42, 43, 44, 45, 46, 47, 48, ...
            51, 52, 53, 54, 55, 56, 57, 58, ...
            61, 62, 63, 64, 65, 66, 67, 68, ...,
            71, 72, 73, 74, 75, 76, 77, 78, ...,
            81, 82, 83, 84, 85, 86, 87, 88];

    channelsOrdering = ...
    [21 31 41 51 61 71 12 22 32 42 52 62 72 82 13 23 33 43 53 63 ... 
    73 83 14 24 34 44 54 64 74 84 15 25 35 45 55 65 75 85 16 26 ...
    36 46 56 66 76 86 17 27 37 47 57 67 77 87 28 38 48 58 68 78];

    Params.coords = zeros(length(channels), 2);
    Params.coords(:, 2) = repmat(linspace(1, 0, 8), 1, 8);
    Params.coords(:, 1) = repelem(linspace(0, 1, 8), 1, 8);

    subset_idx = find(~ismember(channels, [11, 81, 18, 88]));
    channels = channels(subset_idx);

    reorderingIdx = zeros(length(channels), 1);
    for n = 1:length(channels)
        reorderingIdx(n) = find(channelsOrdering(n) == channels);
    end 
    
    Params.coords = Params.coords(subset_idx, :);

    % Re-order the channel IDs and coordinates to match the original
    % ordering
    channels = channels(reorderingIdx);
    Params.channels = channels; 
    Params.coords = Params.coords(reorderingIdx, :);

elseif strcmp(Params.channelLayout, 'MCS60')

     channels = [11, 12, 13, 14, 15, 16, 17, 18, ... 
            21, 22, 23, 24, 25, 26, 27, 28, ...
            31, 32, 33, 34, 35, 36, 37, 38, ...
            41, 42, 43, 44, 45, 46, 47, 48, ...
            51, 52, 53, 54, 55, 56, 57, 58, ...
            61, 62, 63, 64, 65, 66, 67, 68, ...,
            71, 72, 73, 74, 75, 76, 77, 78, ...,
            81, 82, 83, 84, 85, 86, 87, 88];

    channelsOrdering = ...
    [47, 48, 46, 45, 38, 37, 28, 36, 27, 17, 26, 16, 35, 25, ...
    15, 14, 24, 34, 13, 23, 12, 22, 33, 21, 32, 31, 44, 43, 41, 42, ...
    52, 51, 53, 54, 61, 62, 71, 63, 72, 82, 73, 83, 64, 74, 84, 85, 75, ...
    65, 86, 76, 87, 77, 66, 78, 67, 68, 55, 56, 58, 57];

    Params.coords = zeros(length(channels), 2);
    Params.coords(:, 2) = repmat(linspace(1, 0, 8), 1, 8);
    Params.coords(:, 1) = repelem(linspace(0, 1, 8), 1, 8);

    subset_idx = find(~ismember(channels, [11, 81, 18, 88]));
    channels = channels(subset_idx);

    reorderingIdx = zeros(length(channels), 1);
    for n = 1:length(channels)
        reorderingIdx(n) = find(channelsOrdering(n) == channels);
    end 
    
    Params.coords = Params.coords(subset_idx, :);

    % Re-order the channel IDs and coordinates to match the original
    % ordering
    channels = channels(reorderingIdx);
    Params.channels = channels; 
    Params.coords = Params.coords(reorderingIdx, :);
    Params.reorderingIdx = reorderingIdx;

elseif strcmp(Params.channelLayout, 'MCS59')

    channels = [11, 12, 13, 14, 15, 16, 17, 18, ... 
            21, 22, 23, 24, 25, 26, 27, 28, ...
            31, 32, 33, 34, 35, 36, 37, 38, ...
            41, 42, 43, 44, 45, 46, 47, 48, ...
            51, 52, 53, 54, 55, 56, 57, 58, ...
            61, 62, 63, 64, 65, 66, 67, 68, ...,
            71, 72, 73, 74, 75, 76, 77, 78, ...,
            81, 82, 83, 84, 85, 86, 87, 88];

    channelsOrdering = ...
    [47, 48, 46, 45, 38, 37, 28, 36, 27, 17, 26, 16, 35, 25, ...
    15, 14, 24, 34, 13, 23, 12, 22, 33, 21, 32, 31, 44, 43, 41, 42, ...
    52, 51, 53, 54, 61, 62, 71, 63, 72, 82, 73, 83, 64, 74, 84, 85, 75, ...
    65, 86, 76, 87, 77, 66, 78, 67, 68, 55, 56, 58, 57];

    Params.coords = zeros(length(channels), 2);
    Params.coords(:, 2) = repmat(linspace(1, 0, 8), 1, 8);
    Params.coords(:, 1) = repelem(linspace(0, 1, 8), 1, 8);

    subset_idx = find(~ismember(channels, [11, 81, 18, 88]));
    channels = channels(subset_idx);

    reorderingIdx = zeros(length(channels), 1);
    for n = 1:length(channels)
        reorderingIdx(n) = find(channelsOrdering(n) == channels);
    end 
    
    Params.coords = Params.coords(subset_idx, :);

    % Re-order the channel IDs and coordinates to match the original
    % ordering
    channels = channels(reorderingIdx);
    Params.channels = channels; 
    Params.coords = Params.coords(reorderingIdx, :);

    inclusionIndex = find(channelsOrdering ~= 82);
    Params.channels = channels(inclusionIndex);
    Params.coords = Params.coords(inclusionIndex, :);
    Params.reorderingIdx = reorderingIdx; % (inclusionIndex)


elseif strcmp(Params.channelLayout, 'Axion64')

    channels = [11, 12, 13, 14, 15, 16, 17, 18, ... 
            21, 22, 23, 24, 25, 26, 27, 28, ...
            31, 32, 33, 34, 35, 36, 37, 38, ...
            41, 42, 43, 44, 45, 46, 47, 48, ...
            51, 52, 53, 54, 55, 56, 57, 58, ...
            61, 62, 63, 64, 65, 66, 67, 68, ...,
            71, 72, 73, 74, 75, 76, 77, 78, ...,
            81, 82, 83, 84, 85, 86, 87, 88];
    Params.coords = zeros(length(channels), 2);
    Params.coords(:, 2) = repmat(linspace(0, 1, 8), 1, 8);
    Params.coords(:, 1) = repelem(linspace(0, 1, 8), 1, 8);
    
    Params.channels = channels; 


elseif strcmp(Params.channelLayout, 'Custom')

    x_min = 0;
    x_max = 1;
    y_min = 0;
    y_max = 1;
    num_nodes = 64;
    
    rand_x_coord = (x_max - x_min) .* rand(num_nodes,1) + x_min;
    rand_y_coord = (y_max - y_min) .* rand(num_nodes, 1) + y_min; 
    Params.coords = [rand_x_coord, rand_y_coord];

    Params.coords  = Params.coords * 8;

end 

Params.coords  = Params.coords * 8;  % Do not remove this line after specifying coordinate positions in (0 - 1 format)

%% Start analysis message
app.PipelineStatusTextArea.Value = [app.PipelineStatusTextArea.Value; 'Starting analysis!'];
