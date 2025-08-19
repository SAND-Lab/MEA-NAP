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
addpath(fullfile(app.MEANAPFolderEditField.Value, 'Functions', 'util', 'natsort'));  % for MEANAP viewer
localVersion = getVersion(app.MEANAPFolderEditField.Value, app);

% Functions for checking suite2p mode 
addpath(fullfile(app.MEANAPFolderEditField.Value, 'Functions', 'twoPhoton')); 

app.UIFigure.Name = ['MEA-NAP ' localVersion];

% Default colours 
defaultGroupColorMap = [...
   1, 0.996, 0.670, 0.318; ... % 1 orange
   2, 0.780, 0.114, 0.114; ... % 2 red
   3, 0.459, 0.000, 0.376; ... % 3 purple
   4, 0.027, 0.306, 0.659; ... % 4 blue
   5, 0.000, 0.600, 0.451; ... % 5 teal
   6, 0.431, 0.690, 0.000; ... % 6 green
   7, 0.863, 0.863, 0.000; ... % 7 yellow
   8, 0.941, 0.471, 0.000; ... % 8 orange-red
   9, 0.800, 0.000, 0.400; ... % 9 magenta
   10, 0.365, 0.200, 0.800; ... % 10 violet
   11, 0.000, 0.500, 0.800; ... % 11 sky blue
   12, 0.000, 0.700, 0.700; ... % 12 cyan-green
   13, 0.200, 0.700, 0.200; ... % 13 medium green
   14, 0.700, 0.700, 0.200; ... % 14 olive
   15, 0.900, 0.600, 0.000; ... % 15 amber
   16, 0.900, 0.000, 0.200; ... % 16 crimson
   17, 0.600, 0.200, 0.600; ... % 17 plum
   18, 0.400, 0.400, 0.900; ... % 18 royal blue
   29, 0.200, 0.600, 0.900; ... % 19 turquoise
   20, 0.200, 0.800, 0.400];    % 20 fresh green

app.colorUITable.Data = defaultGroupColorMap(1:10, :);

app.colorUITable.ColumnEditable = [true, true, true, true];

% get Original parents to hide/show them later 
advancedSpikeDetectionTabParent = app.AdvSpikeDetectionTab.Parent;
advancedBurstDetectionTabParent = app.AdvBurstDetectionTab.Parent; 
advancedDimensionalityTabParent = app.AdvDimensionalityTab.Parent; 
advancedPlottingTabParent = app.AdvPlottingTab.Parent;
colorsTabParent = app.ColorsTab.Parent; 
artifactRemovalTabParent = app.ArtifactRemovalTab.Parent; 
advancedConnectivityTabParent = app.AdvConnectivityTab.Parent;
nodeCartographyTabParent = app.NodeCartographyTab.Parent;
catnapTabParent = app.CATNAPTab.Parent;
stimulationTabParent = app.StimulationTab.Parent;

% Context menu for MEANAP Output viewer
app.RecordingviewerMenu.MenuSelectedFcn = @(src, event) runMEANAPviewer;
app.StatsviewerMenu.MenuSelectedFcn = @(src, event) runMEANAPstatsViewer;

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

% Default Output Folder name
formatOut = 'ddmmmyyyy'; 
todyDate = datestr(now,formatOut); 
app.OutputFolderNameEditField.Value = ['OutputData' todyDate];

% Modify some titles 
% app.SpikeDetectionTab.Title = sprintf('\nSpike\nDetection');

% suite2p mode
suite2pMode = 0;

%% Run pipeline app

% Assigns minNode to 12 if Axion16 selected
% but this is only done once, so you can reset it if you want
channelLayoutCheck = 0; 

% Update sampling frequency and units if multichannel systems selected 
% But only done once 
mcsSystemParamsCheck = 0;

usingLoadedParams = 0;
prevSpreadsheetRange = str2num(app.SpreadsheetRangeEditField.Value);

% Update default STTC lag values if suite2p mode selected, only done once
suite2pParamsCheck = 0;

% Update Wid based on sampling frequency 
samplingFrequencyCheck = 0;

% Initial ordering of tabs (and hiding of advanced settings)
tabStatus = 0;  % keeping track of whether advanced settings is shown (1) or not (0) to see when I need to update
% Specify ordering of the tabs 
tabOrder = [app.GeneralTab, app.SpikeDetectionTab, app.ConnectivityTab, ...
       app.PlottingTab, app.ColorsTab, app.PipelineTab, app.FileConversionTab, ...
       app.SpreadsheetTab,  ...
       app.AdvSpikeDetectionTab, app.ArtifactRemovalTab, app.AdvBurstDetectionTab, ...
       app.AdvConnectivityTab, app.NodeCartographyTab, app.AdvDimensionalityTab, app.AdvPlottingTab, ...
       ];  
% Reassign the Parent property to reorder
for i = 1:length(tabOrder)
    tabOrder(i).Parent = [];
    tabOrder(i).Parent = app.TabGroup;
end

app.AdvSpikeDetectionTab.Parent = [];
app.AdvBurstDetectionTab.Parent = [];
app.AdvDimensionalityTab.Parent = [];
app.AdvPlottingTab.Parent = [];
app.ColorsTab.Parent = [];
app.ArtifactRemovalTab.Parent = [];
app.AdvConnectivityTab.Parent = [];
app.NodeCartographyTab.Parent = [];
app.StimulationTab.Parent = [];
% Not Tabs 
app.ShadeMetricDropDown.Visible = 'off';
app.ShadeMetricDropDownLabel.Visible = 'off';

% Set up original sampling frequency and layout value to link the two 
% sfValue1 = app.SamplingFrequencyEditField.Value
% sfValue2 = app.SamplingFrequencyEditField.Value

while isvalid(app)

    % previous analysis fields
    if app.UsePreviousAnalysisCheckBox.Value == 0
        app.PreviousAnalysisFolderEditField.Enable = 'Off';
        app.PreviousAnalysisFolderEditFieldLabel.Enable = 'Off';
        app.SpikeDataFolderEditField.Enable = 'Off';
        app.SpikeDataFolderEditFieldLabel.Enable = 'Off';
        app.PrevAnalysisSelectButton.Enable = 'Off';
        app.SpikeDataSelectButton.Enable = 'Off';
    else
        app.PreviousAnalysisFolderEditField.Enable = 'On';
        app.PreviousAnalysisFolderEditFieldLabel.Enable = 'On';
        app.SpikeDataFolderEditField.Enable = 'On';
        app.SpikeDataFolderEditFieldLabel.Enable = 'On';
        app.PrevAnalysisSelectButton.Enable = 'On';
        app.SpikeDataSelectButton.Enable = 'On';
    end 
    
    % check whether to show advanced settings
    if (app.ShowAdvancedSettingsCheckBox.Value == 1) && (tabStatus == 0)
        % Tabs
        app.AdvSpikeDetectionTab.Parent = advancedSpikeDetectionTabParent;
        app.ArtifactRemovalTab.Parent = artifactRemovalTabParent;
        app.AdvBurstDetectionTab.Parent = advancedBurstDetectionTabParent;
        app.AdvConnectivityTab.Parent = advancedConnectivityTabParent;
        app.NodeCartographyTab.Parent = nodeCartographyTabParent;
        app.AdvDimensionalityTab.Parent = advancedDimensionalityTabParent;
        app.AdvPlottingTab.Parent = advancedPlottingTabParent;
        app.ColorsTab.Parent = colorsTabParent; 
        
        % Not Tabs
        app.ShadeMetricDropDown.Visible = 'on';
        app.ShadeMetricDropDownLabel.Visible = 'on';
        
        tabStatus = 1;
        
    elseif (app.ShowAdvancedSettingsCheckBox.Value == 0) && (tabStatus == 1)
        
        app.AdvSpikeDetectionTab.Parent = [];
        app.AdvBurstDetectionTab.Parent = [];
        app.AdvDimensionalityTab.Parent = [];
        app.AdvPlottingTab.Parent = [];
        app.ColorsTab.Parent = [];
        app.ArtifactRemovalTab.Parent = [];
        app.AdvConnectivityTab.Parent = [];
        app.NodeCartographyTab.Parent = [];
        % Not Tabs 
        app.ShadeMetricDropDown.Visible = 'off';
        app.ShadeMetricDropDownLabel.Visible = 'off';
        
        tabStatus = 0;
        
    end 
    
    if suite2pMode == 0
        app.CATNAPTab.Parent = [];
    else 
        app.CATNAPTab.Parent = catnapTabParent;
    end

    if app.StimulationmodeCheckBox.Value == 1 
        app.StimulationTab.Parent = stimulationTabParent;
    else 
        app.StimulationTab.Parent = [];
    end

    % check if all required parameters are set
    homeDirSet = 1 - isempty(app.MEANAPFolderEditField.Value);
    spreadsheetSet = 1 - isempty(app.SpreadsheetFilenameEditField.Value);
    
    % Toggle all required parameters set lamp and enable/disable run
    % pipeline button 
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
        app.MEADataFolderEditField.Value = uigetdir;
        app.RawDataSelectButton.Value = 0;
        figure(app.UIFigure)  % put app back to focus
        
        % Print out number of files found in raw data folder 
        numRawDataFiles = length(dir(fullfile(app.MEADataFolderEditField.Value, '*.mat')));
        app.MEANAPStatusTextArea.Value = [app.MEANAPStatusTextArea.Value; ...
            sprintf('%.f mat files found in raw data folder', numRawDataFiles)];
        
        % Check for suite2p data 
        if numRawDataFiles == 0
            suite2pMode = appCheckSuite2pData(app);
        end 
        
        % Update spreadsheet tab as well 
        app.RawDataFolderEditField_2.Value = app.MEADataFolderEditField.Value;
    end 
    
    % Plotting settings 
    if strcmp(app.EdgethresholdmethodDropDown.Value, 'Absolute Value')
        app.EdgeweightpercentileEditField.Enable = 'off';
        app.MinedgeweightEditField.Enable = 'on';
    else 
        app.EdgeweightpercentileEditField.Enable = 'on';
        app.MinedgeweightEditField.Enable = 'off';
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
         
         if istable(csv_data)
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
                [groupNameBeginsWnumber, groupNameContainsSpecial, allDIVisValid, groupNameIllegal] = checkCSV(csv_data);

                updateCSVstatusInGui(app, groupNameBeginsWnumber, groupNameContainsSpecial, allDIVisValid, groupNameIllegal);

                % Update Custom Group Order with detected group names
                uniqueGrpNames = unique(csv_data(:, 3));
                app.CustomGroupOrderEditField.Value = strjoin(table2cell(uniqueGrpNames), ',');
             end
             
         elseif csv_data == 0
             
             app.MEANAPStatusTextArea.Value = [app.MEANAPStatusTextArea.Value; 'Spreadsheet failed to load. ', ...
                                               'Please check your csv has at least 3 columns, ', ...
                                               'and at least one entry (not counting the header). ', ...
                                               'Read the documentation for details.'];
             
         end 
         
         % app.csvTable.ColumnEditable = true; % logical(ones(1, length(csv_data.Properties.VariableNames)));
    end
    
    % Check if CSV range has changed, if so, update custom groups
    currSpreadsheetRange = str2num(app.SpreadsheetRangeEditField.Value);
    if exist('csv_data', 'var') && (usingLoadedParams == 0)
        if sum(prevSpreadsheetRange ~= currSpreadsheetRange) > 0
            numRows = size(csv_data, 1);
            currSpreadsheetRange(currSpreadsheetRange == inf) = numRows;
            currSpreadsheetRange(currSpreadsheetRange > numRows) = numRows;
            startRow = currSpreadsheetRange(1) - 1;  % ignore header row 
            endRow = currSpreadsheetRange(2) - 1;
            uniqueGrpNames = unique(csv_data(startRow:endRow, 3));
            app.CustomGroupOrderEditField.Value = strjoin(table2cell(uniqueGrpNames), ',');
        end 
    end 
    
    %%%% Spreadsheet Tab %%%%%%%%%%%%%%%%%%%%%%%%%%%
    % Make spreadsheet from folder of .mat / suite2p files
    if app.CreatespreadsheetButton.Value == 1
        
    end
    
    %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%


    %%%%%%% Colors Tab %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    numGroups = app.NumberofgroupsEditField.Value;
    [currentRowCount, ~] = size(app.colorUITable.Data);
    
    if numGroups > currentRowCount
        % add new row to the color table
        app.colorUITable.Data = defaultGroupColorMap(1:numGroups, :);
    elseif numGroups < currentRowCount
        app.colorUITable.Data = defaultGroupColorMap(1:numGroups, :);
    end

    %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    
    
    % Load previous analysis folder 
    if app.PrevAnalysisSelectButton.Value == 1
        app.PreviousAnalysisFolderEditField.Value = uigetdir;
        
        % Get names and automatically populate spike detection folder
        [~, folderName] = fileparts(app.PreviousAnalysisFolderEditField.Value);
        app.SpikeDataFolderEditField.Value = fullfile( ...
            app.PreviousAnalysisFolderEditField.Value, '1_SpikeDetection', '1A_SpikeDetectedData');
        
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
                [groupNameBeginsWnumber, groupNameContainsSpecial, allDIVisValid, groupNameIllegal] = checkCSV(csv_data);
                updateCSVstatusInGui(app, groupNameBeginsWnumber, groupNameContainsSpecial, allDIVisValid, groupNameIllegal);
            end
            % note here csv_data already subsetted based on range
            uniqueGrpNames = unique(csv_data(:, 3));
            app.CustomGroupOrderEditField.Value = strjoin(table2cell(uniqueGrpNames), ',');
            
        end 
        
        % check suite2p mode 
        suite2pMode = appCheckSuite2pData(app);
        
    end 
    
    % Suite2p mode default parameters 
    if (suite2pMode == 1) && (suite2pParamsCheck == 0)
       app.STTCLagmsEditField.Value = '[1000, 2500, 5000]';
       app.NodecartographylagvaluesEditField.Value = '[1000, 2500, 5000]';
       app.SpikeMethodforAnalysisEditField.Value = 'peak';
       suite2pParamsCheck = 1; 
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
    
    if app.RunfileconversionButton.Value == 1
        
        % add functions to file path 
        addpath(genpath(fullfile(app.MEANAPFolderEditField.Value, 'Functions')))
        
        app.MEANAPStatusTextArea.Value = ...
            [app.MEANAPStatusTextArea.Value; 'Running file conversion...'];
        if strcmp(app.FileTypeDropDown.Value, '.raw from Multichannel Systems')  
            app.MEANAPStatusTextArea.Value = ...
            [app.MEANAPStatusTextArea.Value; 'on .raw files from Multichannel Systems...'];
            drawnow;
            MEAbatchConvert('.raw', app.DataFolderEditField.Value);
            createBatchCSVFile(app.DataFolderEditField.Value, ...
                app.BatchCSVNameEditField.Value, app.DIVincludedCheckBox.Value, ...
                app.OneGenotypeCheckBox.Value, app.GroupNameEditField.Value); 
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
            createBatchCSVFile(app.DataFolderEditField.Value, ...
                app.BatchCSVNameEditField.Value, app.DIVincludedCheckBox.Value, ...
                app.OneGenotypeCheckBox.Value, app.GroupNameEditField.Value); 
            cd(app.MEANAPFolderEditField.Value); 
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
    
    % Update sampling frequency and units if multichannel systems layout selected 
    if (usingLoadedParams == 0) && (mcsSystemParamsCheck == 0) && contains(app.ChannelLayoutDropDown.Value, 'MCS60') 
        mcsSystemParamsCheck = 1;
        app.SamplingFrequencyEditField.Value = 25000;
        app.DownSampleFrequencyEditField.Value = 25000;
        app.PotentialDifferenceUnitEditField.Value = 'uV';
    end
    
    % Update Wid settings if sampling frequecy too low 
    if (samplingFrequencyCheck == 0) && (app.SamplingFrequencyEditField.Value <= 10000)
        app.MEANAPStatusTextArea.Value = ...
            [app.MEANAPStatusTextArea.Value; ...
            'Sampling frequecy is too low for default spike detection parameters, ', ...
            'updating Wid to [0.5, 1.0], you can manually adjust this in the advanced spike detection tab'];
        drawnow;
        app.WaveletwidEditField.Value = '[0.5, 1.0]';
        samplingFrequencyCheck = 1;
    end
    
    
    % Setting parameters for testing pipeline 
    if app.TestPipelineButton.Value == 1
        % Download data to run test 
        downloadExampleData; 
        
        % Set Raw data folder 
        app.MEADataFolderEditField.Value = fullfile(app.MEANAPFolderEditField.Value, 'ExampleData');
        
        % Set CSV path 
        spreadsheetFilePath = fullfile(app.MEANAPFolderEditField.Value, 'ExampleData', 'exampleData.csv');
        % spreadsheetFilePath
        app.SpreadsheetFilenameEditField.Value = spreadsheetFilePath;
        % app.SpreadsheetFilepathEditField.Value = spreadsheetFilePath;
        % Set CSV range
        app.SpreadsheetRangeEditField.Value = '[2, 3]';
        
        % Update custom group order
        csvRange = str2num(app.SpreadsheetRangeEditField.Value);
            csv_data = pipelineReadCSV(app.SpreadsheetFilenameEditField.Value, csvRange);
            if size(csv_data, 2) >= 3 
                [groupNameBeginsWnumber, groupNameContainsSpecial, allDIVisValid, groupNameIllegal] = checkCSV(csv_data);
                updateCSVstatusInGui(app, groupNameBeginsWnumber, groupNameContainsSpecial, allDIVisValid, groupNameIllegal);
            end
            % note here csv_data already subsetted based on range
            uniqueGrpNames = unique(csv_data(:, 3));
            app.CustomGroupOrderEditField.Value = strjoin(table2cell(uniqueGrpNames), ',');
        
        break
    end

    % Linking the channel layout and sampling frequency settings 

    
    % Launch MEANAP viewer 
    if app.ViewOutputsButton.Value == 1
        runMEANAPviewer;
        app.ViewOutputsButton.Value = 0;
    end

    % Launch stim detection app 
    if app.LaunchstimdetectionappButton.Value == 1
        runStimDetectionApp(app);
        app.LaunchstimdetectionappButton.Value = 0;
    end 
    
    if (app.RunPipelineButton.Value == 1)
        break 
    end 
    
    pause(0.1)
end 

if ~isvalid(app)
    fprintf('MEANAP GUI closed \n')
    return 
end 

%% Moving settings to Params
%
% remove NMF calculation if running suite2p mode 
if suite2pMode 
    inclusionIndex = find(~ismember(app.NetworkmetricstocalculateListBox.Value, {'num_nnmf_components', 'nComponentsRelNS'}));
    app.NetworkmetricstocalculateListBox.Value = app.NetworkmetricstocalculateListBox.Value(inclusionIndex);
end
%}

Params = getParamsFromApp(app);
Params.suite2pMode = suite2pMode;

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
