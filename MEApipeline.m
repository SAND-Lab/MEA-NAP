% Process data from MEA recordings of 2D and 3D cultures
% created: RCFeord, May 2021
% authors: T Sit, RC Feord, AWE Dunn, J Chabros and other members of the Synaptic and Network Development (SAND) Group
%% USER INPUT REQUIRED FOR THIS SECTION
% in this section all modifiable parameters of the analysis are defined,
% no subsequent section requires user input
% Please refer to the documentation for guidance on parameter choice here:
% https://analysis-pipeline.readthedocs.io/en/latest/pipeline-steps.html#pipeline-settings

% Directories
HomeDir = '/Users/timothysit/AnalysisPipeline'; % analysis folder to home directory
rawData = '/Volumes/T7/schroter2015_mat';  % path to raw data .mat files
Params.priorAnalysisPath = ['/Users/timothysit/AnalysisPipeline/OutputData25Aug2022'];  % path to prev analysis
spikeDetectedData = '/Users/timothysit/AnalysisPipeline/OutputData25Aug2022'; % path to spike-detected data

% Input and output filetype
spreadsheet_file_type = 'csv'; % 'csv' or 'excel'
spreadsheet_filename = 'hpc_dataset.csv'; 
sheet = 1; % specify excel sheet
xlRange = 'A2:C7'; % specify range on the sheet (e.g., 'A2:C7' would analyse the first 6 files)
Params.output_spreadsheet_file_type = 'csv';  % .xlsx or .csv

% Analysis step settings
Params.priorAnalysisDate = '19May2022'; % prior analysis date in format given in output data folder e.g., '27Sep2021'
Params.priorAnalysis = 1; % use previously analysed data? 1 = yes, 0 = no
Params.startAnalysisStep = 4; % if Params.priorAnalysis=0, default is to start with spike detection
Params.optionalStepsToRun = {'runStats'}; % include 'generateCSV' to generate csv for rawData folder

% Spike detection settings
detectSpikes = 0; % run spike detection? % 1 = yes, 0 = no
Params.runSpikeCheckOnPrevSpikeData = 0; % whether to run spike detection check without spike detection 
Params.fs = 25000; % Sampling frequency, HPC: 25000, Axion: 12500;
Params.dSampF = 25000; % down sampling factor for spike detection check
Params.potentialDifferenceUnit = 'uV';  % the unit which you are recording electrical signals 
Params.channelLayout = 'MCS60';  % 'MCS60' or 'Axion64'
Params.thresholds = {'2.5', '3.5', '4.5'}; % standard deviation multiplier threshold(s), eg. {'2.5', '3.5', '4.5'}
Params.wnameList = {'bior1.5'}; % wavelet methods to use {'bior1.5', 'mea'}; 
Params.costList = -0.12;
Params.SpikesMethod = 'bior1p5';  % wavelet methods, eg. 'bior1p5', or 'mergedAll', or 'mergedWavelet'

% Functional connectivity inference settings
Params.FuncConLagval = [15]; % set the different lag values (in ms), default to [10, 15, 25]
Params.TruncRec = 0; % truncate recording? 1 = yes, 0 = no
Params.TruncLength = 120; % length of truncated recordings (in seconds)
Params.adjMtype = 'weighted'; % 'weighted' or 'binary'

% Connectivity matrix thresholding settings
Params.ProbThreshRepNum = 200; % probabilistic thresholding number of repeats 
Params.ProbThreshTail = 0.05; % probabilistic thresholding percentile threshold 
Params.ProbThreshPlotChecks = 1; % randomly sample recordings to plot probabilistic thresholding check, 1 = yes, 0 = no
Params.ProbThreshPlotChecksN = 5; % number of random checks to plot

% Node cartography settings 
Params.autoSetCartographyBoudariesPerLag = 1;  % whether to fit separate boundaries per lag value
Params.cartographyLagVal = 15; % lag value (ms) to use to calculate PC-Z distribution (only applies if Params.autoSetCartographyBoudariesPerLag = 0)
Params.autoSetCartographyBoundaries = 1;  % whether to automatically determine bounds for hubs or use custom ones

% Statistics and machine learning settings 
Params.classificationTarget = 'AgeDiv';  % which property of the recordings to classify 
Params.classification_models = {'linearSVM', 'kNN', 'fforwardNN', 'decisionTree', 'LDA'};
Params.regression_models = {'svmRegressor', 'regressionTree', 'ridgeRegression', 'fforwardNN'};

% Plot settings
Params.figExt = {'.png', '.svg'};  % supported options are '.fig', '.png', and '.svg'
Params.fullSVG = 1;  % whether to insist svg even with plots with large number of elements
Params.showOneFig = 1;  % otherwise, 0 = pipeline shows plots as it runs, 1: supress plots

% GUI / Tutorial mode settings 
Params.guiMode = 1;
if Params.guiMode
    CreateStruct.Interpreter = 'tex';
    CreateStruct.WindowStyle = 'modal';
    helloBox = msgbox("\fontsize{20} Hello! Welcome to the MEA network analysis pipeline toolbox!", CreateStruct);
    uiwait(helloBox);
    clear helloBox

    selectHomeDir = msgbox("\fontsize{20} First, please select the folder where your MEApieline.m script is in", CreateStruct);
    uiwait(selectHomeDir);
    clear selectHomeDir

    homeDirUiGet = uigetdir(pwd, 'Please select the folder where the MEApipeline.m script is in');
    % uiwait(homeDirUiGet)
    Params.HomeDir = homeDirUiGet;
    
    opts = struct(); 
    opts.Default = 'Yes';
    opts.Interpreter = 'tex';
    runningPipelineFirstTime = questdlg('\fontsize{20} Are you running this pipeline for the first time on raw data?', ...
	'Pipeline step question', 'Yes', 'No', opts);

end 

%% END OF USER REQUIRED INPUT SECTION
% The rest of the MEApipeline.m runs automatically. Do not change after this line
% unless you are an expert user.
% Define output folder names
formatOut = 'ddmmmyyyy'; 
Params.Date = datestr(now,formatOut); 
clear formatOut

biAdvancedSettings

if Params.runSpikeCheckOnPrevSpikeData
    fprintf(['You specified to run spike detection check on previously extracted spikes, \n', ... 
            'so I will skip over the spike detection step \n'])
    detectSpikes = 0;
end 

% add all relevant folders to path
cd(HomeDir)
addpath(genpath('Functions'))
addpath('Images')

% Network plot colormap bounds 
Params.use_theoretical_bounds = 1;
Params.use_min_max_all_recording_bounds = 0;
Params.use_min_max_per_genotype_bounds = 0;

if Params.use_theoretical_bounds
    network_plot_cmap_bounds = struct();
    network_plot_cmap_bounds.CC = [0, 1];
    network_plot_cmap_bounds.PC = [0, 1];
    network_plot_cmap_bounds.Z = [-2, 2];
    network_plot_cmap_bounds.BC = [0, 1];
    network_plot_cmap_bounds.Eloc = [0, 1];
    network_plot_cmap_bounds.aveControl = [0, 2];
    network_plot_cmap_bounds.modalControl = [0, 1]; 
    Params.network_plot_cmap_bounds = network_plot_cmap_bounds;
else 
    het_node_level_vals = 0;
    if Params.use_min_max_all_recording_bounds
        
    elseif Params.use_min_max_per_genotype_bounds

    end 
end 

%% Optional step : generate csv 
if any(strcmp(Params.optionalStepsToRun,'generateCSV')) 
    fprintf('Generating CSV with given rawData folder \n')
    mat_file_list = dir(fullfile(rawData, '*mat'));
    name_list = {mat_file_list.name}';
    name_without_ext = {};
    div = {};
    for filenum = 1:length(name_list)
        name_without_ext{filenum} = name_list{filenum}(1:end-4);
        div{filenum} = name_list{filenum}((end-5):end-4);
    end 
    name = name_without_ext'; 
    div = div';
    name_table = table([name, div]);
    writetable(name_table, spreadsheet_filename)
end 

%% setup - additional setup

% import metadata from spreadsheet
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
    opts.DataLines = [2 Inf];  % start reading data from row 2
    % csv_data = readtable(spreadsheet_filename, 'Delimiter','comma');
    csv_data = readtable(spreadsheet_filename, opts);
    ExpName =  csv_data{:, 1};
    ExpGrp = csv_data{:, 3};
    ExpDIV = csv_data{:, 2};
    if sum(strcmp('Ground',csv_data.Properties.VariableNames))
        Params.electrodesToGroundPerRecording = csv_data.('Ground'); % this should be a 1 x N cell array 
        if ~iscell(Params.electrodesToGroundPerRecording)
            Params.electrodesToGroundPerRecording = {Params.electrodesToGroundPerRecording};
        end 
    else 
        Params.electrodesToGroundPerRecording = [];
    end 
end 

[~,Params.GrpNm] = findgroups(ExpGrp);
[~,Params.DivNm] = findgroups(ExpDIV);

% create output data folder if doesn't exist
CreateOutputFolders(HomeDir,Params.Date,Params.GrpNm)

% plot electrode layout 
plotElectrodeLayout(HomeDir, Params)

% export parameters to csv file
cd(strcat('OutputData',Params.Date))
writetable(struct2table(Params,'AsArray',true), strcat('Parameters_',Params.Date,'.csv'))
cd(HomeDir)

% save metadata
for ExN = 1:length(ExpName)

    Info.FN = ExpName(ExN);
    Info.DIV = num2cell(ExpDIV(ExN));
    Info.Grp = ExpGrp(ExN);

    cd(strcat('OutputData',Params.Date)); cd('ExperimentMatFiles')
    save(strcat(char(Info.FN),'_',Params.Date,'.mat'),'Info')
    cd(HomeDir)

end

% create a random sample for checking the probabilistic thresholding
if Params.ProbThreshPlotChecks == 1
    Params.randRepCheckExN = randi([1 length(ExpName)],1,Params.ProbThreshPlotChecksN);
    Params.randRepCheckLag = Params.FuncConLagval(randi([1 length(Params.FuncConLagval)],1,Params.ProbThreshPlotChecksN));
    Params.randRepCheckP = [Params.randRepCheckExN;Params.randRepCheckLag];
end

%% Step 1 - spike detection

if ((Params.priorAnalysis == 0) || (Params.runSpikeCheckOnPrevSpikeData)) && (Params.startAnalysisStep == 1) 

    if (detectSpikes == 1) || (Params.runSpikeCheckOnPrevSpikeData)
        addpath(rawData)
    else
        addpath(spikeDetectedData)
    end

    savePath = strcat(HomeDir,'/OutputData',Params.Date,'/1_SpikeDetection/1A_SpikeDetectedData/');
    savePath(strfind(savePath,'\'))='/';
    
    % Run spike detection
    if detectSpikes == 1
        batchDetectSpikes(rawData, savePath, option, ExpName, Params);
        cd(HomeDir)
    end 

    % Plot spike detection results 

    for  ExN = 1:length(ExpName)
        
        if Params.runSpikeCheckOnPrevSpikeData
            cd(fullfile(spikeDetectedData, '1_SpikeDetection', '1A_SpikeDetectedData'))
        else
            cd(strcat(HomeDir,'/OutputData',Params.Date,'/1_SpikeDetection/1A_SpikeDetectedData/'))
        end 
        load(strcat(char(ExpName(ExN)),'_spikes.mat'),'spikeTimes','spikeDetectionResult','channels','spikeWaveforms')
        cd(HomeDir); cd(strcat('OutputData',Params.Date)); cd('ExperimentMatFiles')
        load(strcat(char(ExpName(ExN)),'_',Params.Date,'.mat'),'Info')

        cd(HomeDir); cd(strcat('OutputData',Params.Date))
        cd('1_SpikeDetection'); cd('1B_SpikeDetectionChecks'); cd(char(Info.Grp))
        plotSpikeDetectionChecks(spikeTimes,spikeDetectionResult,spikeWaveforms,Info,Params)
        
        % Check whether there are no spikes at all in recording 
        checkIfAnySpikes(spikeTimes, ExpName{ExN});

        cd(HomeDir)

    end

end

%% Step 2 - neuronal activity

if Params.priorAnalysis==0 || Params.priorAnalysis==1 && Params.startAnalysisStep<3

    % Format spike data
    % TODO: deal with the case where spike data is already formatted...
    for  ExN = 1:length(ExpName)
            
        cd(strcat('OutputData',Params.Date)); cd('ExperimentMatFiles')

        % experimentMatFileData = load(strcat(char(ExpName(ExN)),'_',Params.Date,'.mat'));

        load(strcat(char(ExpName(ExN)),'_',Params.Date,'.mat'),'Info')
        cd(HomeDir)

        % extract spike matrix, spikes times and associated info
        disp(char(Info.FN))

        if Params.priorAnalysis==1 && Params.startAnalysisStep==2
            path = strcat(Params.priorAnalysisPath,'/1_SpikeDetection/1A_SpikeDetectedData/');
            path(strfind(savepath,'\'))='/'; cd(path)
        else
            if detectSpikes == 1
                path = strcat(HomeDir,'/OutputData',Params.Date,'/1_SpikeDetection/1A_SpikeDetectedData/');
                path(strfind(savepath,'\'))='/'; cd(path)
            else
                cd(spikeDetectedData)
            end
        end

        [spikeMatrix,spikeTimes,Params,Info] = formatSpikeTimes(char(Info.FN),Params,Info);
        cd(HomeDir)

        % initial run-through to establish max values for scaling
        spikeFreqMax(ExN) = prctile((downSampleSum(full(spikeMatrix), Info.duration_s)),95,'all');

        cd(strcat('OutputData',Params.Date)); cd('ExperimentMatFiles')
        save(strcat(char(Info.FN),'_',Params.Date,'.mat'),'Info','Params','spikeTimes','spikeMatrix')
        cd(HomeDir)

        clear spikeTimes
    end

    % extract and plot neuronal activity

    disp('Electrophysiological properties')

    spikeFreqMax = max(spikeFreqMax);

    for  ExN = 1:length(ExpName)

        cd(strcat('OutputData',Params.Date)); cd('ExperimentMatFiles')
        load(strcat(char(ExpName(ExN)),'_',Params.Date,'.mat'),'Info','Params','spikeTimes','spikeMatrix')
        cd(HomeDir)

        % get firing rates and burst characterisation
        Ephys = firingRatesBursts(spikeMatrix,Params,Info);

        cd(strcat('OutputData',Params.Date)); cd('2_NeuronalActivity')
        cd('2A_IndividualNeuronalAnalysis'); cd(char(Info.Grp))
        mkdir(char(Info.FN))
        cd(char(Info.FN))

        % generate and save raster plot
        rasterPlot(char(Info.FN),spikeMatrix,Params,spikeFreqMax)
        % electrode heat maps
        electrodeHeatMaps(char(Info.FN),spikeMatrix,Info.channels,spikeFreqMax,Params)
        % half violin plots
        firingRateElectrodeDistribution(char(Info.FN),Ephys,Params,Info)

        cd(HomeDir)

        cd(strcat('OutputData',Params.Date)); cd('ExperimentMatFiles')
        save(strcat(char(Info.FN),'_',Params.Date,'.mat'),'Info','Params','spikeTimes','Ephys', '-v7.3')
        cd(HomeDir)

        clear spikeTimes spikeMatrix

    end

    % create combined plots across groups/ages
    PlotEphysStats(ExpName,Params,HomeDir)
    cd(HomeDir)

end


%% Step 3 - functional connectivity, generate adjacency matrices

if Params.priorAnalysis==0 || Params.priorAnalysis==1 && Params.startAnalysisStep<4

    disp('generating adjacency matrices')

    for  ExN = 1:length(ExpName)

        if Params.priorAnalysis==1 && Params.startAnalysisStep==3
            path = strcat(Params.priorAnalysisPath,'/ExperimentMatFiles/');
            path(strfind(savepath,'\'))='/'; 
            cd(path)
            load(strcat(char(ExpName(ExN)),'_',Params.priorAnalysisDate,'.mat'),'spikeTimes','Ephys','Info')
         else
            cd(strcat('OutputData',Params.Date)); cd('ExperimentMatFiles')
            load(strcat(char(ExpName(ExN)),'_',Params.Date,'.mat'),'Info','Params','spikeTimes','Ephys')
        end
        cd(HomeDir)

        disp(char(Info.FN))

        cd(strcat('OutputData',Params.Date))
        adjMs = generateAdjMs(spikeTimes,ExN,Params,Info,HomeDir);
        cd(HomeDir)

        cd(strcat('OutputData',Params.Date)); cd('ExperimentMatFiles')
        save(strcat(char(Info.FN),'_',Params.Date,'.mat'),'Info','Params','spikeTimes','Ephys','adjMs')
        cd(HomeDir)

    end

end

%% Step 4 - network activity
Params = checkOneFigureHandle(Params);

if Params.priorAnalysis==0 || Params.priorAnalysis==1 && Params.startAnalysisStep<=4

    for  ExN = 1:length(ExpName)

        if Params.priorAnalysis==1 && Params.startAnalysisStep==4
            path = strcat(Params.priorAnalysisPath,'/ExperimentMatFiles/');
            path(strfind(savepath,'\'))='/'; cd(path)
            load(strcat(char(ExpName(ExN)),'_',Params.priorAnalysisDate,'.mat'), 'spikeTimes', 'Ephys','adjMs','Info')
        else
            cd(strcat('OutputData',Params.Date)); cd('ExperimentMatFiles')
            load(strcat(char(ExpName(ExN)),'_',Params.Date,'.mat'),'Info','Params', 'spikeTimes', 'Ephys','adjMs')
            Params = checkOneFigureHandle(Params);
        end
        cd(HomeDir)

        disp(char(Info.FN))

        cd(strcat('OutputData',Params.Date)); cd('4_NetworkActivity')
        cd('4A_IndividualNetworkAnalysis'); cd(char(Info.Grp))
        
        addpath(fullfile(spikeDetectedData, '1_SpikeDetection', '1A_SpikeDetectedData'));
        [spikeMatrix,spikeTimes,Params,Info] = formatSpikeTimes(char(Info.FN),Params,Info);
        
        NetMet = ExtractNetMetOrganoid(adjMs, spikeTimes, ...
            Params.FuncConLagval, Info,HomeDir,Params, spikeMatrix);

        cd(HomeDir); cd(strcat('OutputData',Params.Date)); cd('ExperimentMatFiles')

        save(strcat(char(Info.FN),'_',Params.Date,'.mat'),'Info','Params','spikeTimes','Ephys','adjMs','NetMet')
        cd(HomeDir)

        clear adjMs

    end

    % create combined plots
    PlotNetMet(ExpName,Params,HomeDir)
    
    if Params.includeNMFcomponents
        % Plot NMF 
        experimentMatFolder = fullfile(HomeDir, ...
            strcat('OutputData',Params.Date), 'ExperimentMatFiles');
        plotSaveFolder = fullfile(HomeDir, ...
            strcat('OutputData',Params.Date), '4_NetworkActivity', ...
            '4A_IndividualNetworkAnalysis');
        plotNMF(experimentMatFolder, plotSaveFolder, Params)
    end 

    cd(HomeDir)

    % Aggregate all files and run density analysis to determine boundaries
    % for node cartography
    if Params.autoSetCartographyBoundaries
        if Params.priorAnalysis==1 
            cd(fullfile(Params.priorAnalysisPath, 'ExperimentMatFiles'));   
        else
            cd(fullfile(strcat('OutputData', Params.Date), 'ExperimentMatFiles'));   
        end 
        
        fig_folder = fullfile(Params.priorAnalysisPath, '4_NetworkActivity/4B_GroupComparisons/7_DensityLandscape');
        if ~isfolder(fig_folder)
            mkdir(fig_folder)
        end 

        ExpList = dir('*.mat');
        add_fig_info = '';

        if Params.autoSetCartographyBoudariesPerLag
            for lag_val = Params.FuncConLagval
                [hubBoundaryWMdDeg, periPartCoef, proHubpartCoef, nonHubconnectorPartCoef, connectorHubPartCoef] = ...
                TrialLandscapeDensity(ExpList, fig_folder, add_fig_info, Params.cartographyLagVal);
                Params.(strcat('hubBoundaryWMdDeg', sprintf('_%.fmsLag', lag_val))) = hubBoundaryWMdDeg;
                Params.(strcat('periPartCoef', sprintf('_%.fmsLag', lag_val))) = periPartCoef;
                Params.(strcat('proHubpartCoef', sprintf('_%.fmsLag', lag_val))) = proHubpartCoef;
                Params.(strcat('nonHubconnectorPartCoef', sprintf('_%.fmsLag', lag_val))) = nonHubconnectorPartCoef;
                Params.(strcat('connectorHubPartCoef', sprintf('_%.fmsLag', lag_val))) = connectorHubPartCoef;
            end 

        else 
            [hubBoundaryWMdDeg, periPartCoef, proHubpartCoef, nonHubconnectorPartCoef, connectorHubPartCoef] = ...
                TrialLandscapeDensity(ExpList, fig_folder, add_fig_info, Params.cartographyLagVal);
            Params.hubBoundaryWMdDeg = hubBoundaryWMdDeg;
            Params.periPartCoef = periPartCoef;
            Params.proHubpartCoef = proHubpartCoef;
            Params.nonHubconnectorPartCoef = nonHubconnectorPartCoef;
            Params.connectorHubPartCoef = connectorHubPartCoef;
        end 

        % save the newly set boundaries to the Params struct
        for nFile = 1:length(ExpList)
            FN = ExpList(nFile).name;
            save(FN, 'Params', '-append')
        end 
        
        cd(HomeDir)
        
    end 

    % Plot node catography plots using either custom bounds or
    % automatically determined bounds
    for  ExN = 1:length(ExpName)

        if Params.priorAnalysis==1 && Params.startAnalysisStep==4
            path = strcat(Params.priorAnalysisPath,'/ExperimentMatFiles/');
            path(strfind(savepath,'\'))='/'; cd(path)
            % TODO: load as struct rather than into workspace
            load(strcat(char(ExpName(ExN)),'_',Params.priorAnalysisDate,'.mat'), 'spikeTimes','Ephys','adjMs','Info', 'NetMet')
        else
            cd(strcat('OutputData',Params.Date)); cd('ExperimentMatFiles')
            load(strcat(char(ExpName(ExN)),'_',Params.Date,'.mat'),'Info','Params', 'spikeTimes','Ephys','adjMs', 'NetMet')
        end
        cd(HomeDir)

        disp(char(Info.FN))

        cd(strcat('OutputData',Params.Date)); cd('4_NetworkActivity')
        cd('4A_IndividualNetworkAnalysis'); cd(char(Info.Grp))
        Params = checkOneFigureHandle(Params);
        NetMet = plotNodeCartography(adjMs, Params, NetMet, Info, HomeDir);
        % save NetMet now we node cartography data as well
        cd(HomeDir); cd(strcat('OutputData',Params.Date)); cd('ExperimentMatFiles')
        save(strcat(char(Info.FN),'_',Params.Date,'.mat'),'Info','Params','spikeTimes','Ephys','adjMs','NetMet')
        cd(HomeDir)
    end 
    
    % Plot node cartography metrics across all reccordings 
    cd(fullfile(HomeDir, strcat('OutputData', Params.Date), 'ExperimentMatFiles'))
    NetMetricsE = {'Dens','Q','nMod','Eglob','aN','CC','PL','SW','SWw', ... 
               'Hub3','Hub4', 'NCpn1','NCpn2','NCpn3','NCpn4','NCpn5','NCpn6'}; 
    NetMetricsC = {'ND','EW','NS','Eloc','BC','PC','Z'};
    combinedData = combineExpNetworkData(ExpName, Params, NetMetricsE, NetMetricsC, HomeDir);
    plotNetMetNodeCartography(combinedData, ExpName,Params,HomeDir)

end

%% Optional step: Run density landscape to determine the boundaries for the node cartography 
if any(strcmp(Params.optionalStepsToRun,'getDensityLandscape')) 
    cd(fullfile(Params.priorAnalysisPath, 'ExperimentMatFiles'));
    
    fig_folder = fullfile(Params.priorAnalysisPath, '4_NetworkActivity/4B_GroupComparisons/7_DensityLandscape');
    if ~isdir(fig_folder)
        mkdir(fig_folder)
    end 
    
    % loop through multiple DIVs
    for DIV = [14, 17, 21, 24, 28]
        ExpList = dir(sprintf('*DIV%.f*.mat', DIV));
        add_fig_info = strcat('DIV', num2str(DIV));
        [hubBoundaryWMdDeg, periPartCoef, proHubpartCoef, nonHubconnectorPartCoef, connectorHubPartCoef] ...
            = TrialLandscapeDensity(ExpList, fig_folder, add_fig_info, Params.cartographyLagVal);
    end 
end 

%% Optional step: statistics and classification of genotype / ages 
if any(strcmp(Params.optionalStepsToRun,'runStats'))
    if Params.showOneFig
        if ~isfield(Params, 'oneFigure')
            Params.oneFigure = figure;
        end 
    end 

    nodeLevelFile = fullfile(Params.priorAnalysisPath, 'NetworkActivity_NodeLevel.csv');
    nodeLevelData = readtable(nodeLevelFile);
    
    recordingLevelFile = fullfile(Params.priorAnalysisPath, 'NetworkActivity_RecordingLevel.csv');
    recordingLevelData = readtable(recordingLevelFile);
    
    for lag_val = Params.FuncConLagval
        plotSaveFolder = fullfile(Params.priorAnalysisPath, '5_Stats', sprintf('%.fmsLag', lag_val));
        if ~isfolder(plotSaveFolder)
            mkdir(plotSaveFolder)
        end 
        featureCorrelation(nodeLevelData, recordingLevelData, Params, lag_val, plotSaveFolder);
        doClassification(recordingLevelData, Params, lag_val, plotSaveFolder);
    end 
end 


%% Optional Step: compare pre-post TTX spike activity 
if any(strcmp(Params.optionalStepsToRun,'comparePrePostTTX')) 
    % see find_best_spike_result.m for explanation of the parameters
    Params.prePostTTX.max_tolerable_spikes_in_TTX_abs = 100; 
    Params.prePostTTX.max_tolerable_spikes_in_grounded_abs = 100;
    Params.prePostTTX.max_tolerable_spikes_in_TTX_per_s = 1; 
    Params.prePostTTX.max_tolerable_spikes_in_grounded_per_s = 1;
    Params.prePostTTX.start_time = 0;
    Params.prePostTTX.default_end_time = 600;  
    Params.prePostTTX.sampling_rate = 1;  
    Params.prePostTTX.threshold_ground_electrode_name = 15;
    Params.prePostTTX.default_grounded_electrode_name = 15;
    Params.prePostTTX.min_spike_per_electrode_to_be_active = 0.5;
    Params.prePostTTX.wavelet_to_search = {'mea', 'bior1p5'};
    Params.prePostTTX.use_TTX_to_tune_L_param = 0;
    Params.prePostTTX.spike_time_unit = 'frame'; 
    Params.prePostTTX.custom_backup_param_to_use = []; 
    Params.prePostTTX.regularisation_param = 10;
    
    
    % Get spike detection result folder
    spike_folder = strcat(HomeDir,'/OutputData',Params.Date,'/1_SpikeDetection/1A_SpikeDetectedData/');
    spike_folder(strfind(spike_folder,'\'))='/';
    
    pre_post_ttx_plot_folder = fullfile(HomeDir, 'OutputData', ... 
        Params.Date, '1_SpikeDetection', '1C_prePostTTXcomparison'); 
    
    find_best_spike_result(spike_folder, pre_post_ttx_plot_folder, Params)
end 




