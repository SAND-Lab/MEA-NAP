%% Script to run pipeline app and propagate settings back to Params
clear app
app = AnalysisPipelineApp;
app.MEANAPStatusTextArea.Value = {'Welcome! The MEA-NAP GUI is launched.'};
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
    homeDirSet = 1 - isempty(app.MEANAPFolderEditField.Value);
    spreadsheetSet = 1 - isempty(app.SpreadsheetfilenameEditField.Value);
    
    if homeDirSet && spreadsheetSet
        app.AllrequiredparameterssetLamp.Color = [0 1 0];
    else
        app.AllrequiredparameterssetLamp.Color = [1 0 0];
    end

    % Load HomeDir 
    if app.HomeDirSelectButton.Value == 1
        app.MEANAPFolderEditField.Value = uigetdir;
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
         csvRange = str2num(app.SpreadsheetRangeEditField.Value);
         csv_data = pipelineReadCSV(spreadsheetFilePath, csvRange);
         app.MEANAPStatusTextArea.Value = [app.MEANAPStatusTextArea.Value; 'Loaded spreadsheet succesfully!'];
         app.MEANAPStatusTextArea.Value = [app.MEANAPStatusTextArea.Value; sprintf('Your data has %.f rows', size(csv_data, 1))];
         app.MEANAPStatusTextArea.Value = [app.MEANAPStatusTextArea.Value; 'And columns with names:'];
         app.MEANAPStatusTextArea.Value = [app.MEANAPStatusTextArea.Value; strjoin(csv_data.Properties.VariableNames, ', ')];
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
        app.MEANAPStatusTextArea.Value = [app.MEANAPStatusTextArea.Value; 'Loaded parameters from:'];
        app.MEANAPStatusTextArea.Value = [app.MEANAPStatusTextArea.Value; fullfile(ParamsFilePath, ParamsFileName)];
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
        app.MEANAPStatusTextArea.Value = [app.MEANAPStatusTextArea.Value; 'Saved parameters to:'];
        app.MEANAPStatusTextArea.Value = [app.MEANAPStatusTextArea.Value; ParamsSavePath];
        app.SaveParametersButton.Value = 0;
        figure(app.UIFigure)  % put app back to focus
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
detectSpikes = Params.detectSpikes;
Params.output_spreadsheet_file_type = 'csv';

%% Some stuff that were dealt with previously in biAdvancedSettings 
if any(isnan(Params.outputDataFolder)) || isempty(Params.outputDataFolder)
    Params.outputDataFolder = HomeDir;
end 



%% Start analysis message
app.MEANAPStatusTextArea.Value = [app.MEANAPStatusTextArea.Value; 'Starting analysis!'];
