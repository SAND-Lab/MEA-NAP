%% Script to run pipeline app and propagate settings back to Params
clear app
app = AnalysisPipelineApp;
app.PipelineStatusTextArea.Value = {'Welcome!, Analysis Pipeline GUI is launched'};
app.UITable.Data = [ ...
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
app.UITable.ColumnEditable = [true, true, true, true];

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
    else
        app.PreviousAnalysisDateEditField.Enable = 'On';
        app.PreviousAnalysisDateEditFieldLabel.Enable = 'On';
        app.PreviousAnalysisFolderEditField.Enable = 'On';
        app.PreviousAnalysisFolderEditFieldLabel.Enable = 'On';
        app.SpikeDataFolderEditField.Enable = 'On';
        app.SpikeDataFolderEditFieldLabel.Enable = 'On';
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
    end 

    % check if all required parameters are set
    homeDirSet = 1 - isempty(app.HomeDirectoryEditField.Value);
    if homeDirSet
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
        ParamsSavePath = strcat('MEANAP-Params-', currDateTime, '.mat');
        save(ParamsSavePath, 'Params');
        app.PipelineStatusTextArea.Value = [app.PipelineStatusTextArea.Value; 'Saved parameters to:'];
        app.PipelineStatusTextArea.Value = [app.PipelineStatusTextArea.Value; ParamsSavePath];
        app.SaveParametersButton.Value = 0;
    end 

    pause(0.1)
end 

%% Moving settings to Params
Params = getParamsFromApp(app);

HomeDir = Params.HomeDir;  % TODO: just put this to Params
spreadsheet_filename = Params.spreadSheetFileName;

Params.outputDataFolder = app.OutputDataFolderEditField.Value;
Params.rawData = app.RawDataFolderEditField.Value;
Params.priorAnalysisPath = app.PreviousAnalysisFolderEditField.Value;
Params.spikeDetectedData = app.SpikeDataFolderEditField.Value;



%% Start analysis message
app.PipelineStatusTextArea.Value = [app.PipelineStatusTextArea.Value; 'Starting analysis!'];
