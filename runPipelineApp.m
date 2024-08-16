%% Script to run pipeline app and propagate settings back to Params
clear app
app = MEANAPApp;
app.MEANAPStatusTextArea.Value = {'Welcome! The MEA-NAP GUI is launched.'};

% GUI resizing 
% app.UIFigure.SizeChangedFcn = createCallbackFcn(app, @updateAppLayout, true);

% Default home directory 
app.MEANAPFolderEditField.Value = pwd;

% Check version 
addpath(fullfile(app.MEANAPFolderEditField.Value, 'Functions', 'util'));
getVersion(app.MEANAPFolderEditField.Value, app);

% Default colours 
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

% Set default network parameters to calculate

app.NetworkmetricstocalculateListBox.Items = {'aN','Dens','CC','nMod','Q','PL','Eglob', ...
    'SW','SWw', 'effRank', ...
    'num_nnmf_components', 'nComponentsRelNS', ...
    'NDmean', 'NDtop25', ...
    'sigEdgesMean', 'sigEdgesTop10', ...
    'NSmean', 'ElocMean', ... 
    'PCmean', 'PCmeanTop10', 'PCmeanBottom10', ...
    'percentZscoreGreaterThanZero', 'percentZscoreLessThanZero', ...
    'NCpn1','NCpn2','NCpn3','NCpn4','NCpn5','NCpn6', ...
    'aveControlMean', 'modalControlMean', ...
    'ND','MEW','NS','Z','Eloc','PC','BC', ...
    'aveControl', 'modalControl'};

app.NetworkmetricstocalculateListBox.Value = {...
    'aN','Dens',...
    'NDmean', 'NDtop25', ...
    'sigEdgesMean', 'sigEdgesTop10', ...
    'CC','nMod','Q','PL','Eglob', ...
    'SW','SWw', 'effRank', ...
    'num_nnmf_components', 'nComponentsRelNS', ...
    'NSmean', 'ElocMean', ... 
    'PCmean', 'PCmeanTop10', 'PCmeanBottom10', ...
    'percentZscoreGreaterThanZero', 'percentZscoreLessThanZero', ...
    'NCpn1','NCpn2','NCpn3','NCpn4','NCpn5','NCpn6', ...
    'ND','NS','Z','Eloc','PC','BC', ...
    'MEW', ...
    'aveControl', 'modalControl', 'aveControlMean'};


%% Run pipeline app

% Assigns minNode to 12 if Axion16 selected
% but this is only done once, so you can reset it if you want
channelLayoutCheck = 0; 
usingLoadedParams = 0;

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
    spreadsheetSet = 1 - isempty(app.SpreadsheetFilenameEditField.Value);
    
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
        
        % Update spreadsheet tab as well 
        app.RawDataFolderEditField_2.Value = app.RawDataFolderEditField.Value;
    end 
    
    % Load CSV
    if app.SpreadsheetSelectButton.Value == 1
         [spreadsheetFilename, spreadsheetFolder] = uigetfile('.csv');
         spreadsheetFilePath = fullfile(spreadsheetFolder, spreadsheetFilename);
         app.SpreadsheetFilenameEditField.Value = spreadsheetFilePath;
         app.SpreadsheetSelectButton.Value = 0;        
         figure(app.UIFigure)  % put app back to focus
         
         % load csv to check if everything is alright 
         csvRange = str2num(app.SpreadsheetRangeEditField.Value);
         csv_data = pipelineReadCSV(spreadsheetFilePath, csvRange);
         app.MEANAPStatusTextArea.Value = [app.MEANAPStatusTextArea.Value; 'Loaded spreadsheet succesfully!'];
         app.MEANAPStatusTextArea.Value = [app.MEANAPStatusTextArea.Value; sprintf('Your data has %.f rows', size(csv_data, 1))];
         app.MEANAPStatusTextArea.Value = [app.MEANAPStatusTextArea.Value; 'And columns with names:'];
         app.MEANAPStatusTextArea.Value = [app.MEANAPStatusTextArea.Value; strjoin(csv_data.Properties.VariableNames, ', ')];
         
         % Update spreadsheet tab csvTable with loaded csv data
         app.SpreadsheetFilepathEditField.Value = spreadsheetFilePath;
         app.csvTable.Data = csv_data;
         app.csvTable.ColumnName = csv_data.Properties.VariableNames;
         
         % Check for special characters in spreadsheet and group names that
         % start with numbers
         if size(csv_data, 2) >= 3 
            [groupNameBeginsWnumber, groupNameContainsSpecial] = checkCSV(csv_data);
            if groupNameBeginsWnumber
                app.MEANAPStatusTextArea.Value = [app.MEANAPStatusTextArea.Value; ...
                    'WARNING: at least one of the group names in your csv file start with a number, MEANAP may not run properly'];
            end 
            if groupNameContainsSpecial
                app.MEANAPStatusTextArea.Value = [app.MEANAPStatusTextArea.Value; ...
                    'WARNING: at least one of the group names in your csv file contain a special character, MEANAP may not run properly'];
            end 
            % Update Custom Group Order with detected group names
            uniqueGrpNames = unique(csv_data(:, 3));
            app.CustomGroupOrderEditField.Value = strjoin(table2cell(uniqueGrpNames), ',');
         end
         
         
         % app.csvTable.ColumnEditable = true; % logical(ones(1, length(csv_data.Properties.VariableNames)));
    end
    
    % Spreadsheet Tab 
    
    
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
        
        usingLoadedParams = 1;
        
        % if csv data exists, load it and check it is okay 
        if isfile(app.SpreadsheetFilenameEditField.Value)
            csvRange = str2num(app.SpreadsheetRangeEditField.Value);
            csv_data = pipelineReadCSV(app.SpreadsheetFilenameEditField.Value, csvRange);
            if size(csv_data, 2) >= 3 
                [groupNameBeginsWnumber, groupNameContainsSpecial] = checkCSV(csv_data);
                if groupNameBeginsWnumber
                    app.MEANAPStatusTextArea.Value = [app.MEANAPStatusTextArea.Value; ...
                        'WARNING: at least one of the group names in your csv file start with a number, MEANAP may not run properly'];
                end 
                if groupNameContainsSpecial
                    app.MEANAPStatusTextArea.Value = [app.MEANAPStatusTextArea.Value; ...
                        'WARNING: at least one of the group names in your csv file contain a special character, MEANAP may not run properly'];
                end 
            end
        end 
    end 

    % SAVING PARAMETERS
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
    
    % FILE CONVERSION 
    
    % Path to files to convert 
    if app.FileConversionselectButton.Value == 1 
        app.DataFolderEditField.Value = uigetdir;
        app.FileConversionselectButton.Value = 0;
        figure(app.UIFigure)  % put app back to focus
    end 
    
    if ~strcmp(app.FileTypeDropDown.Value, '.raw from Axion Maestro')
        app.BatchCSVNameEditField.Enable = 0;
        app.DIVincludedCheckBox.Enable = 0;
        app.OneGenotypeCheckBox.Enable = 0;
        app.GroupNameEditField.Enable = 0;
    else 
        app.BatchCSVNameEditField.Enable = 1;
        app.DIVincludedCheckBox.Enable = 1;
        app.OneGenotypeCheckBox.Enable = 1;
        app.GroupNameEditField.Enable = 1;
    end 
    
    if app.RunfileconversionButton.Value == 1
        
        % add functions to file path 
        addpath(genpath(fullfile(app.MEANAPFolderEditField.Value, 'Functions')))
        
        app.MEANAPStatusTextArea.Value = ...
            [app.MEANAPStatusTextArea.Value; 'Running file conversion...'];
        if strcmp(app.FileTypeDropDown.Value, '.raw from Multichannel Systems')  
            app.MEANAPStatusTextArea.Value = ...
            [app.MEANAPStatusTextArea.Value; 'on .raw files from Multichannel Systems...'];
            MEAbatchConvert('.raw', app.DataFolderEditField.Value);
            cd(app.MEANAPFolderEditField.Value); 
        elseif strcmp(app.FileTypeDropDown.Value, '.raw from Axion Maestro')
             app.MEANAPStatusTextArea.Value = ...
            [app.MEANAPStatusTextArea.Value; 'on .raw files from Axion Maestro...'];
            drawnow;
            rawConvertFunc(app.MEANAPFolderEditField.Value, app.DataFolderEditField.Value, ...
                app.BatchCSVNameEditField.Value, app.DIVincludedCheckBox.Value, ...
                app.OneGenotypeCheckBox.Value, app.GroupNameEditField.Value, ....
                app.SamplingFrequencyEditField.Value); 
            
        elseif strcmp(app.FileTypeDropDown.Value, '.h5 from Multichannel Systems')
            app.MEANAPStatusTextArea.Value = ...
            [app.MEANAPStatusTextArea.Value; 'on .h5 files from Multichannel Systems...'];
            drawnow;
            convertMCSh5toMat(app.DataFolderEditField.Value);
        end 
        app.MEANAPStatusTextArea.Value = ...
            [app.MEANAPStatusTextArea.Value; 'File conversion complete!'];
        app.RunfileconversionButton.Value = 0;
    end 
    
    % ND is a compulsory network metric to calculate (used in many plots)
    if 1 - any(strcmp(app.NetworkmetricstocalculateListBox.Value, 'ND'))
        app.NetworkmetricstocalculateListBox.Value{end+1} = 'ND';
    end 
    
    % Check if Axion16 layout selected, and set minNode to 12 by default 
    if (usingLoadedParams == 0) && (channelLayoutCheck == 0) && strcmp(app.ChannelLayoutDropDown.Value, 'Axion16') 
        channelLayoutCheck = 1;
        app.MinimumnumberofnodesEditField.Value = 12;
    end
    
    pause(0.1)
end 

%% Moving settings to Params
Params = getParamsFromApp(app);

% TODO: Can this be moved to getParamsFromApp?
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
csvRange = str2num(app.SpreadsheetRangeEditField.Value);
option = 'list';  % spike detection option
Params.spikeMethodColors = ...
    [  0    0.4470    0.7410; ...
    0.8500    0.3250    0.0980; ...
    0.9290    0.6940    0.1250; ...
    0.4940    0.1840    0.5560; ... 
    0.4660    0.6740    0.1880; ... 
    0.3010    0.7450    0.9330; ... 
    0.6350    0.0780    0.1840];


%% Optional step : statistics and classification 
Params.pValThreshold = 0.01;  % p value threshold to consider effect as significant

%% Some stuff that were dealt with previously in AdvancedSettings 
if any(isnan(Params.outputDataFolder)) || isempty(Params.outputDataFolder)
    Params.outputDataFolder = HomeDir;
end 



%% Start analysis message
app.MEANAPStatusTextArea.Value = [app.MEANAPStatusTextArea.Value; 'Starting analysis!'];
