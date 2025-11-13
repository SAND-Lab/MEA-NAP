function MEApipeline(InputParamsFilePath)
% Process data from MEA recordings of 2D and 3D neuronal cultures
% Created: RC Feord, May 2021
% Authors: T Sit, RC Feord, AWE Dunn, J Chabros and other members of the Synaptic and Network Development (SAND) Group
%% USER INPUT REQUIRED FOR THIS SECTION
% In this section all modifiable parameters of the analysis are defined.
% No subsequent section requires user input.
% Please refer to the documentation for guidance on parameter choice here:
% https://analysis-pipeline.readthedocs.io/en/latest/pipeline-steps.html#pipeline-settings
clearvars -except InputParamsFilePath 
close all 

% Change to MEANAP folder
MEANAPscriptPath = which('MEApipeline.m');
MEANAPfolder = fileparts(MEANAPscriptPath);
cd(MEANAPfolder)

restoredefaultpath

% Directories
HomeDir = '[INPUT_REQUIRED]'; % Where the MEA-NAP (MEA Network Analysis Pipeline) code is located
Params.outputDataFolder = '';   % Where to save the output data, leave as '' if same as HomeDir 
Params.outputDataFolderName = '';  % Name of the folder to save the output data
rawData = '[INPUT_REQUIRED]';  % path to raw data .mat files
Params.priorAnalysisPath = [''];  % path to prev analysis, leave as [''] if no prior anlaysis
spikeDetectedData = ''; % path to spike-detected data, leave as '' if no previously detected spike data

% Input and output filetype
spreadsheet_file_type = 'csv'; % 'csv' or 'excel'
spreadsheet_filename = '[INPUT_REQUIRED].csv'; 
sheet = 1; % specify excel sheet
xlRange = 'A2:C7'; % specify range on the sheet (e.g., 'A2:C7' would analyse the first 6 files)
csvRange = [2, Inf]; % read the data in the range [StartRow EndRow], e.g. [2 Inf] means start reading data from row 2
Params.output_spreadsheet_file_type = 'csv';  % .xlsx or .csv

% Analysis step settings
Params.priorAnalysisDate = ''; % prior analysis date in format given in output data folder e.g., '27Sep2021'
Params.priorAnalysis = 0; % use previously analysed data? 1 = yes, 0 = no
Params.startAnalysisStep = 1; % if Params.priorAnalysis=0, default is to start with spike detection
Params.optionalStepsToRun = {''}; % include 'generateCSV' to generate csv for rawData folder
                                  % include 'Stats' to look at feature
                                  % correlation and classification across groups
                                  % include 'combineDIVplots' to combine plots across DIVs

% Spike detection settings
detectSpikes = 0; % run spike detection? % 1 = yes, 0 = no
Params.runSpikeCheckOnPrevSpikeData = 0; % whether to run spike detection check without spike detection 
Params.fs = 25000; % Sampling frequency you selected when acquiring data, e.g., MCS: 25000, Axion: 12500;
Params.dSampF = 25000; % down sampling factor for spike detection check, e.g., can set the same as the sampling frequency
Params.potentialDifferenceUnit = 'uV';  % Unit for voltage signal, e.g., MCS: uV, Axion: V 
Params.channelLayout = 'MCS60';  % 'MCS60' (for MEA2100), 'Axion64' (for 6-well plates), or 'MCS60old' (for MEA6100)
Params.thresholds = {'3', '4', '5'}; % standard deviation multiplier threshold(s), eg. {'2.5', '3.5', '4.5'}
Params.wnameList = {'bior1.5', 'bior1.3', 'db2'}; % wavelet methods to use e.g., {'bior1.5', 'bior1.3', 'mea'}; 
Params.costList = -0.12;
Params.SpikesMethod = 'bior1p5';  % wavelet methods, e.g., 'bior1p5', or 'mergedAll', or 'mergedWavelet'

% Functional connectivity inference settings
Params.FuncConLagval = [10, 25, 50]; % set the different lag values (in ms), default to [10, 15, 25]
Params.TruncRec = 0; % truncate recording? 1 = yes, 0 = no
Params.TruncLength = 120; % length of truncated recordings (in seconds)
Params.adjMtype = 'weighted'; % 'weighted' or 'binary'

% Connectivity matrix thresholding settings
Params.ProbThreshRepNum = 200; % probabilistic thresholding number of repeats (recommend at least 180) 
Params.ProbThreshTail = 0.05; % probabilistic thresholding percentile threshold 
Params.ProbThreshPlotChecks = 1; % randomly sample recordings to plot probabilistic thresholding check, 1 = yes, 0 = no
Params.ProbThreshPlotChecksN = 5; % number of random checks to plot

% Node cartography settings 
Params.autoSetCartographyBoudariesPerLag = 1;  % whether to fit separate boundaries per lag value
Params.cartographyLagVal = [10, 25, 50]; % lag value (ms) to use to calculate PC-Z distribution (only applies if Params.autoSetCartographyBoudariesPerLag = 0)
Params.autoSetCartographyBoundaries = 1;  % whether to automatically determine bounds for hubs or use custom ones

% Statistics and machine learning settings 
Params.classificationTarget = 'AgeDiv';  % which property of the recordings to classify 
Params.classification_models = {'linearSVM', 'kNN', 'fforwardNN', 'decisionTree', 'LDA'};
Params.regression_models = {'svmRegressor', 'regressionTree', 'ridgeRegression', 'fforwardNN'};

% Plot settings
Params.figExt = {'.png', '.svg'};  % supported options are '.fig', '.png', and '.svg'
Params.fullSVG = 1;  % whether to insist svg even with plots with large number of elements
Params.showOneFig = 1;  % otherwise, 0 = pipeline shows plots as it runs, 1: supress plots

% Re-computation of metrics 
Params.recomputeMetrics = 0;
Params.metricsToRecompute = {};  % {} or {'all'} or {'metricNames'}

%% GUI / Tutorial mode settings 
Params.guiMode = 1;   % GUI mode? 1 = on, 0 = off

if (Params.guiMode == 1) && ~exist('InputParamsFilePath', 'var')
    runPipelineApp
    if isvalid(app)
        spikeDetectedData = Params.spikeDetectedData;
    else
        return 
    end
else
    Params.spreadSheetFileName = spreadsheet_filename;
end 

%% Check if ParamsFilePath is specified
if exist('InputParamsFilePath', 'var')
   ParamDataFile = load(InputParamsFilePath);
   Params = ParamDataFile.Params;
   Params.guiMode = 1;
   HomeDir = Params.HomeDir;
   spreadsheet_filename = Params.spreadSheetFileName;
   rawData = Params.rawData;
   detectSpikes = Params.detectSpikes;
   option = 'list';
   Params.spikeMethodColors = ...
    [  0    0.4470    0.7410; ...
    0.8500    0.3250    0.0980; ...
    0.9290    0.6940    0.1250; ...
    0.4940    0.1840    0.5560; ... 
    0.4660    0.6740    0.1880; ... 
    0.3010    0.7450    0.9330; ... 
    0.6350    0.0780    0.1840];
end

%% Paths 
% add all relevant folders to path
cd(HomeDir)
addpath(genpath('Functions'))
addpath('Images')


%% END OF USER REQUIRED INPUT SECTION
% The rest of the MEApipeline.m runs automatically. Do not change after this line
% unless you are an expert user.
% Define output folder names
formatOut = 'ddmmmyyyy'; 
Params.Date = datestr(now,formatOut); 
clear formatOut

if Params.guiMode ~= 1
    AdvancedSettings
end 

if Params.runSpikeCheckOnPrevSpikeData
    fprintf(['You specified to run spike detection check on previously extracted spikes, \n', ... 
            'so I will skip over the spike detection step \n'])
    detectSpikes = 0;
end 

Params.detectSpikes = detectSpikes;  % As a record of option selection

% Allow starting from a subset of steps 
if length(Params.startAnalysisStep) > 1
    Params.startAnalysisSubStep = Params.startAnalysisStep(2);
    Params.startAnalysisStep = str2num(Params.startAnalysisStep(1));
else
    if isstr(Params.startAnalysisStep)
        Params.startAnalysisStep = str2num(Params.startAnalysisStep);
    end
    Params.startAnalysisSubStep = 'ALL';
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
setUpSpreadSheet  % import metadata from spreadsheet
[~,Params.GrpNm] = findgroups(ExpGrp);
[~,Params.DivNm] = findgroups(ExpDIV);

% create output data folder if doesn't exist
CreateOutputFolders(Params.outputDataFolder, Params.GrpNm, Params)

% Set up one figure handle to save all the figures
oneFigureHandle = NaN;
oneFigureHandle = checkOneFigureHandle(Params, oneFigureHandle);
    
% plot electrode layout 
plotElectrodeLayout(Params.outputDataFolder, Params, oneFigureHandle)

% export parameters to .mat and .csv file
outputDataWDatePath = fullfile(Params.outputDataFolder, Params.outputDataFolderName);
ParamsTableSavePath = fullfile(outputDataWDatePath, strcat('Parameters_',Params.outputDataFolderName,'.csv'));
writetable(struct2table(Params,'AsArray',true), ParamsTableSavePath)
ParamsMatSavePath = fullfile(outputDataWDatePath, strcat('Parameters_',Params.outputDataFolderName,'.mat'));
save(ParamsMatSavePath, 'Params');

% save metadata to ExperimentMatFiles
metaDataSaveFolder = fullfile(outputDataWDatePath, 'ExperimentMatFiles');
for ExN = 1:length(ExpName)
    Info.FN = ExpName(ExN);
    Info.DIV = num2cell(ExpDIV(ExN));
    Info.Grp = ExpGrp(ExN);
    InfoSavePath = fullfile(metaDataSaveFolder, strcat(char(Info.FN),'_',Params.outputDataFolderName,'.mat'));
    
    
    % Append cell type information, currently assumes to be contained 
    % in folder where the 'suite2p' folder is located
    if Params.suite2pMode == 1
        fileFolder = fullfile(Params.rawData, Info.FN{1});
        folderCsvFiles = dir(fullfile(fileFolder, '*csv'));
        if length(folderCsvFiles) == 1
            cellTypeTable = readtable(fullfile(fileFolder, folderCsvFiles(1).name));
            Info.CellTypes = cellTypeTable;
        end 
    end 
    
    if ~isfile(InfoSavePath)
        save(InfoSavePath,'Info')
    else 
        save(InfoSavePath,'Info', '-append')
    end 
    

end

% create a random sample for checking the probabilistic thresholding
if Params.ProbThreshPlotChecks == 1
    Params.randRepCheckExN = randi([1 length(ExpName)],1,Params.ProbThreshPlotChecksN);
    Params.randRepCheckLag = Params.FuncConLagval(randi([1 length(Params.FuncConLagval)],1,Params.ProbThreshPlotChecksN));
    Params.randRepCheckP = [Params.randRepCheckExN;Params.randRepCheckLag];

    Params.randRepCheckExN2p = zeros(1, length(ExpName)); 
    Params.randRepCheckExN2p(1:Params.ProbThreshPlotChecksN) = 1;
    Params.randRepCheckExN2p = Params.randRepCheckExN2p(randperm(length(Params.randRepCheckExN2p)));
    Params.randRepCheckLag2p =  Params.FuncConLagval(randi([1 length(Params.FuncConLagval)],1,length(ExpName)));
end

% Copy spreadsheet to output folder 
copyfile(Params.spreadSheetFileName, outputDataWDatePath);

%% Step 1 - spike detection

if ((Params.priorAnalysis == 0) || (Params.runSpikeCheckOnPrevSpikeData)) && (Params.startAnalysisStep == 1) 
    
    if Params.guiMode == 1
        app.MEANAPStatusTextArea.Value = [app.MEANAPStatusTextArea.Value; ...
        'Running step 1 of MEA-NAP: spike detection'];
    end
    
    if Params.timeProcesses
        step1Start = tic;
    end 
    
    if (detectSpikes == 1) || (Params.runSpikeCheckOnPrevSpikeData)
        if iscell(rawData)
            for pathIdx = 1:length(rawData)
                addpath(rawData{pathIdx});
            end 
        else 
            addpath(rawData)
        end 
    else
        addpath(spikeDetectedData)
    end
    
    savePath = fullfile(Params.outputDataFolder, ...
                        Params.outputDataFolderName, ...
                        '1_SpikeDetection', '1A_SpikeDetectedData');

    
    % Run spike detection
    if detectSpikes == 1
        if Params.guiMode == 1
            batchDetectSpikes(rawData, savePath, option, ExpName, Params, app);
        else
            batchDetectSpikes(rawData, savePath, option, ExpName, Params);
        end
    end 
    
    % Stimulus detection 
    if Params.stimulationMode == 1
        batchDetectStim(ExpName, Params, app);
        % Edit spike data based on the stimulation time
        batchProcessSpikesFromStim(ExpName, Params);
    end 

    
    % Specify where ExperimentMatFiles are stored
    experimentMatFileFolder = fullfile(Params.outputDataFolder, ...
           Params.outputDataFolderName, 'ExperimentMatFiles');

    % Plot spike detection results 
    for  ExN = 1:length(ExpName)
        
        if Params.runSpikeCheckOnPrevSpikeData
            spikeDetectedDataOutputFolder = spikeDetectedData;
        else
            spikeDetectedDataOutputFolder = fullfile(Params.outputDataFolder, ...
                Params.outputDataFolderName, '1_SpikeDetection', '1A_SpikeDetectedData'); 
        end 
        
        spikeFilePath = fullfile(spikeDetectedDataOutputFolder, strcat(char(ExpName(ExN)),'_spikes.mat'));
        load(spikeFilePath,'spikeTimes','spikeDetectionResult', 'channels', 'spikeWaveforms')

        experimentMatFilePath = fullfile(experimentMatFileFolder, ...
            strcat(char(ExpName(ExN)),'_',Params.outputDataFolderName,'.mat'));
        load(experimentMatFilePath,'Info')

        spikeDetectionCheckGrpFolder = fullfile(Params.outputDataFolder, ...
            Params.outputDataFolderName, '1_SpikeDetection', '1B_SpikeDetectionChecks', char(Info.Grp));
        FN = char(Info.FN);
        spikeDetectionCheckFNFolder = fullfile(spikeDetectionCheckGrpFolder, FN);

        if ~isfolder(spikeDetectionCheckFNFolder)
            mkdir(spikeDetectionCheckFNFolder)
        end 

        plotSpikeDetectionChecks(spikeTimes, spikeDetectionResult, ...
            spikeWaveforms, Info, Params, spikeDetectionCheckFNFolder, oneFigureHandle)
        
        % Check whether there are no spikes at all in the recording 
        checkIfAnySpikes(spikeTimes, ExpName{ExN});

    end

    

    if Params.timeProcesses
        step1Duration = toc(step1Start);
    end 

end

%% Step 2 - neuronal activity
if Params.startAnalysisStep < 3
    
    if Params.guiMode == 1
        app.MEANAPStatusTextArea.Value = [app.MEANAPStatusTextArea.Value; ...
        'Running step 2 of MEA-NAP: neuronal activity'];
    else 
        fprintf('Running step 2 of MEA-NAP: neuronal activity \n')
    end
    
    if Params.timeProcesses
        step2Start = tic;
    end 
    
    % Suite2p data processing 
    if Params.suite2pMode == 1
        spikeFreqMax2p = 0;
        experimentMatFolderPath = fullfile(Params.outputDataFolder, ...
            Params.outputDataFolderName, 'ExperimentMatFiles');
        
        for  ExN = 1:length(ExpName)
            experimentMatFname = strcat(char(ExpName(ExN)),'_',Params.outputDataFolderName,'.mat'); 
            experimentMatFpath = fullfile(experimentMatFolderPath, experimentMatFname);
            load(experimentMatFpath, 'Info')
            
            suite2pFolder = fullfile(Params.rawData, char(ExpName(ExN)), 'suite2p', 'plane0');
            Params.ExN = ExN;
            [adjMs, coords, channels, F, denoisedF, spks, spikeTimes, fs, Params, activityProperties] = ...
                suite2pToAdjm(suite2pFolder, Params, Info, oneFigureHandle);
            % Plot original and denoised traces
            stepFolder = fullfile(Params.outputDataFolder, Params.outputDataFolderName, ...
                '2_NeuronalActivity', '2A_IndividualNeuronalAnalysis');
            groupFolder = fullfile(stepFolder, Info.Grp{1});
            if ~isfolder(groupFolder)
                mkdir(groupFolder)
            end 
            figFolder = fullfile(groupFolder, Info.FN{1});
            if ~isfolder(figFolder)
                mkdir(figFolder)
            end 
            Info.duration_s = size(spks, 1) / fs;
            plot2ptraces(suite2pFolder, Params, Info.FN{1}, fs, figFolder, oneFigureHandle);
            resamplingRate = 1;  % resample spike matrix for raster plotting
            twopActivityMatrix = get2pActivityMatrix(F, denoisedF, spks, spikeTimes, resamplingRate, Info, Params); 
            spikeFreqMax2p = max([spikeFreqMax2p, max(twopActivityMatrix)]);
            
            ExpMatFolder = fullfile(Params.outputDataFolder, ...
            Params.outputDataFolderName, 'ExperimentMatFiles');
            infoFnFname = strcat(char(Info.FN),'_',Params.outputDataFolderName,'.mat');
            infoFnFilePath = fullfile(ExpMatFolder, infoFnFname);

            Info.channels = channels;
            varsToSave = {'Info', 'Params', 'coords', 'channels', ...
                'adjMs', 'spikeTimes', 'F', 'denoisedF', 'spks', 'fs', ...
                'activityProperties'}; 

            save(infoFnFilePath, varsToSave{:}, '-append')
        end 
    end 

    % NEURONAL ACTIVITY: INITIALISE MAX VALUES FOR PLOTTING

    maxValStruct = struct(); % get the maximum value of various metrics for scaling
    valsTogetMax = {'FR', ...
                    'channelBurstRate', ...
                    'channelBurstDur', ...
                    'channelFracSpikesInBursts', ...
                    'channelISIwithinBurst', ...
                    'channeISIoutsideBurst', ...
                    };
    for fieldNameIdx = 1:length(valsTogetMax)
        fieldName = valsTogetMax{fieldNameIdx};
        maxValStruct.(fieldName) = [];
    end 
   
    % NEURONAL ACTIVITY: ANALYSIS STEP 

    for ExN = 1:length(ExpName)
        experimentMatFolderPath = fullfile(Params.outputDataFolder, ...
            Params.outputDataFolderName, 'ExperimentMatFiles');
        experimentMatFname = strcat(char(ExpName(ExN)),'_',Params.outputDataFolderName,'.mat'); 
        experimentMatFpath = fullfile(experimentMatFolderPath, experimentMatFname);
        load(experimentMatFpath, 'Info')
        
        if Params.suite2pMode == 0
            if Params.priorAnalysis==1 && Params.startAnalysisStep==2
                spikeDetectedDataFolder = spikeDetectedData;
            else
                if detectSpikes == 1
                    spikeDetectedDataFolder = fullfile(Params.outputDataFolder, ...
                        Params.outputDataFolderName, '1_SpikeDetection', ...
                        '1A_SpikeDetectedData');
                else
                    spikeDetectedDataFolder = spikeDetectedData;
                end
            end
            channelLayout =  Params.channelLayoutPerRecording{ExN};
            [spikeMatrix,spikeTimes,Params,Info] = formatSpikeTimes(... 
                char(Info.FN), Params, Info, spikeDetectedDataFolder, channelLayout);

            % load(experimentMatFpath,'Info','Params','spikeTimes','spikeMatrix');

            % get firing rates and burst characterisation
            Ephys = firingRatesBursts(spikeMatrix,Params,Info);

            for fieldNameIdx = 1:length(valsTogetMax)
                fieldName = valsTogetMax{fieldNameIdx};
                maxValStruct.(fieldName) = [maxValStruct.(fieldName) Ephys.(fieldName)];
            end 

            infoFnFilePath = fullfile(experimentMatFolderPath, ...
                              strcat(char(Info.FN),'_',Params.outputDataFolderName,'.mat'));
            save(infoFnFilePath,'Info','Params','spikeTimes', 'spikeMatrix', 'Ephys', '-v7.3')
        else 
            expData = load(experimentMatFpath);
            activityStats = calTwopActivityStats(expData, Params);
            infoFnFilePath = fullfile(experimentMatFolderPath, ...
                              strcat(char(expData.Info.FN),'_',Params.outputDataFolderName,'.mat'));
            save(infoFnFilePath, 'Params', 'activityStats', '-append')
        end
    end 

    % Get max value from struct
    for fieldNameIdx = 1:length(valsTogetMax)
        fieldName = valsTogetMax{fieldNameIdx};
        maxVal = max(maxValStruct.(fieldName));
        if isnan(maxVal)
            maxVal = 0;
        end 
        maxValStruct.(fieldName) = maxVal; 
    end 

    % NEURONAL ACTIVITY : PLOTTING STEP 
    % Set up one figure handle to save all the figures
    if ~exist('oneFigureHandle', 'var')
        oneFigureHandle = NaN;
    end
    oneFigureHandle = checkOneFigureHandle(Params, oneFigureHandle);

    for ExN = 1:length(ExpName)
        experimentMatFolderPath = fullfile(Params.outputDataFolder, ...
            Params.outputDataFolderName, 'ExperimentMatFiles');
        experimentMatFname = strcat(char(ExpName(ExN)),'_',Params.outputDataFolderName,'.mat'); 
        experimentMatFpath = fullfile(experimentMatFolderPath, experimentMatFname);
        load(experimentMatFpath,'Info','Params', 'spikeTimes', 'spikeMatrix', 'Ephys');
        
        idvNeuronalAnalysisGrpFolder = fullfile(Params.outputDataFolder, ...
            Params.outputDataFolderName, '2_NeuronalActivity', ...
            '2A_IndividualNeuronalAnalysis', char(Info.Grp));
        
        if ~isfolder(idvNeuronalAnalysisGrpFolder)
            mkdir(idvNeuronalAnalysisGrpFolder)
        end 
        
        idvNeuronalAnalysisFNFolder = fullfile(idvNeuronalAnalysisGrpFolder, char(Info.FN));
        if ~isfolder(idvNeuronalAnalysisFNFolder)
            mkdir(idvNeuronalAnalysisFNFolder)
        end 
        
        if Params.suite2pMode == 0
            % generate and save raster plot
            rasterPlot(char(Info.FN),spikeMatrix,Params, maxValStruct.FR, ...
                       idvNeuronalAnalysisFNFolder, oneFigureHandle);
            % electrode heat maps
            coords = Params.coords{ExN};
            electrodeHeatMaps(char(Info.FN), spikeMatrix, Info.channels, ... 
                maxValStruct.FR, Params, coords, idvNeuronalAnalysisFNFolder, oneFigureHandle)
            
            % Plot bursts metrics
            metricVarsToPlot = {'channelBurstRate', ...
                                'channelBurstDur', ...
                                'channelFracSpikesInBursts', ...
                                'channelISIwithinBurst', ...
                                'channeISIoutsideBurst', ...
                                };
            metricLabels = {'Average burst rate (per minute)', ...
                            'Average burst duration (ms)', ...
                            'Fraction spikes in bursts', ...
                            'ISI within bursts (ms)', ... 
                            'ISI outside bursts (ms)'};
            figNames = {'3_BurstRate_heatmap', ... 
                        '4_BurstDur_heatmap', ...
                        '5_FractSpikesInBursts_heatmap',... 
                        '6_ISIwithinBurst_heatmap', ...
                        '7_ISIoutsideBurst_heatmap'};

            cmapToUse = {viridis, ...
                        flip(viridis), ... 
                        viridis, ...
                        flip(viridis), ... 
                        flip(viridis), ...
                        };

            useLogScale = [0, 1, 0, 0, 1];

            for metricIdx = 1:length(metricVarsToPlot)
                metricVarname = metricVarsToPlot{metricIdx};
                % plot burst heatmap 
                plotNodeHeatmap(char(Info.FN), Ephys, Info.channels, ...
                    maxValStruct.(metricVarname), Params, coords, metricVarname, metricLabels{metricIdx}, ...
                    cmapToUse{metricIdx}, useLogScale(metricIdx), idvNeuronalAnalysisFNFolder, figNames{metricIdx}, ...
                    oneFigureHandle, []);
            
            end
            
            % half violin plots
            firingRateElectrodeDistribution(char(Info.FN), Ephys, Params, ... 
                Info, idvNeuronalAnalysisFNFolder, oneFigureHandle)

            clear spikeTimes spikeMatrix
        else
            expData = load(experimentMatFpath);
            % half violin plots
            firingRateElectrodeDistribution(char(expData.Info.FN), activityStats, Params, ... 
                expData.Info, idvNeuronalAnalysisFNFolder, oneFigureHandle)
            
        end

    end
    
    % Raster plot for suite2p data
    if Params.suite2pMode == 1
        for ExN = 1:length(ExpName)
            expData = loadExpData(char(ExpName(ExN)), Params, 0);
            resamplingRate = 1;  % resample spike matrix for raster plotting
            twopActivityMatrix = get2pActivityMatrix(expData.F, expData.denoisedF, ...
                expData.spks, expData.spikeTimes, resamplingRate, expData.Info, Params); 
            stepFolder = fullfile(Params.outputDataFolder, Params.outputDataFolderName, ...
                '2_NeuronalActivity', '2A_IndividualNeuronalAnalysis');
            groupFolder = fullfile(stepFolder, expData.Info.Grp{1});
            figFolder = fullfile(groupFolder, expData.Info.FN{1});
            Params.fs = fs;
            rasterPlot(expData.Info.FN{1}, twopActivityMatrix, Params, spikeFreqMax2p, figFolder, oneFigureHandle)
        end
    end
    
    % create combined plots across groups/ages
    PlotEphysStats(ExpName,Params,HomeDir, oneFigureHandle)
    saveEphysStats(ExpName, Params)
    cd(HomeDir)

    % Stimulation neuronal activity analysis 
    if Params.stimulationMode == 1
        for ExN = 1:length(ExpName)
            % spike data 
            spikeDataFname = strcat(char(ExpName(ExN)),'_spikes','.mat');
            spikeDataFpath = fullfile(spikeDetectedDataFolder, spikeDataFname);
            % experiment mat file 
            experimentMatFname = strcat(char(ExpName(ExN)),'_',Params.outputDataFolderName,'.mat'); 
            experimentMatFpath = fullfile(experimentMatFolderPath, experimentMatFname);
            expData = load(experimentMatFpath);
            % get fig folder 
            stepFolder = fullfile(Params.outputDataFolder, Params.outputDataFolderName, ...
                '2_NeuronalActivity', '2A_IndividualNeuronalAnalysis');
            groupFolder = fullfile(stepFolder, expData.Info.Grp{1});
            figFolder = fullfile(groupFolder, expData.Info.FN{1});

            spikeData = load(spikeDataFpath);
            stimActivityAnalysis(spikeData, Params, expData.Info, ...
                figFolder, oneFigureHandle);
        end
    end
    
    if Params.timeProcesses
        step2Duration = toc(step2Start);
    end 

end


%% Step 3 - functional connectivity, generate adjacency matrices

if Params.priorAnalysis==0 || Params.priorAnalysis==1 && Params.startAnalysisStep<4
    
    if Params.guiMode == 1
        app.MEANAPStatusTextArea.Value = [app.MEANAPStatusTextArea.Value; ...
        'Running step 3 of MEA-NAP: generating adjacency matrices'];
    else 
        fprintf('Running step 3 of MEA-NAP: generating adjacency matrices \n')
    end
    
    if Params.timeProcesses
        step3Start = tic;
    end 
    
    % Set up one figure handle to save all the figures
    if ~exist('oneFigureHandle', 'var')
        oneFigureHandle = NaN;
    end
    oneFigureHandle = checkOneFigureHandle(Params, oneFigureHandle);
    
    
    if Params.suite2pMode == 0  % suite2p adjM is created in step 2
        for  ExN = 1:length(ExpName)

            % Load spike / previous data
            if Params.priorAnalysis==1 && Params.startAnalysisStep==3
                priorAnalysisExpMatFolder = fullfile(Params.priorAnalysisPath, 'ExperimentMatFiles');
                spikeDataFname = strcat(char(ExpName(ExN)),'_',Params.priorAnalysisSubFolderName, '.mat');
                spikeDataFpath = fullfile(priorAnalysisExpMatFolder, spikeDataFname);
                if isfile(spikeDataFpath)
                    load(spikeDataFpath, 'spikeTimes', 'Ephys', 'Info')
                else 
                    % look for spike data in spike data folder 
                    spikeDataFpath = fullfile(Params.spikeDetectedData, ...
                        strcat([char(ExpName(ExN)) '_spikes.mat']));
                    load(spikeDataFpath, 'spikeTimes', 'Info')
                end 
            else
                ExpMatFolder = fullfile(Params.outputDataFolder, ...
                    Params.outputDataFolderName, 'ExperimentMatFiles');
                spikeDataFname = strcat(char(ExpName(ExN)),'_',Params.outputDataFolderName,'.mat');
                spikeDataFpath = fullfile(ExpMatFolder, spikeDataFname);
                load(spikeDataFpath, 'Info', 'Params', 'spikeTimes', 'Ephys')
            end


            if strcmp(Params.verboseLevel, 'High')
                if Params.guiMode == 1
                    app.MEANAPStatusTextArea.Value = [app.MEANAPStatusTextArea.Value; ...
                            sprintf('Generating adjacency matrix for: %s', char(Info.FN))];
                else 
                    fprintf(sprintf('Generating adjacency matrix for: %s \n', char(Info.FN)))
                end 
            end

            adjMs = generateAdjMs(spikeTimes, ExN, Params, Info, oneFigureHandle);


            ExpMatFolder = fullfile(Params.outputDataFolder, ...
                    Params.outputDataFolderName, 'ExperimentMatFiles');
            infoFnFname = strcat(char(Info.FN),'_',Params.outputDataFolderName,'.mat');
            infoFnFilePath = fullfile(ExpMatFolder, infoFnFname);

            varsToSave = {'Info', 'Params', 'spikeTimes', 'Ephys', 'adjMs'};

            save(infoFnFilePath, varsToSave{:}, '-append')
        end
    end 
    
    if Params.timeProcesses
        step3Duration = toc(step3Start);
    end 

end

%% Step 4 - network activity

if Params.priorAnalysis==0 || Params.priorAnalysis==1 && Params.startAnalysisStep<=4
    
    step4startMessage = 'Running step 4 of MEA-NAP: Analyzing network activity';
    
    if Params.guiMode == 1
        app.MEANAPStatusTextArea.Value = [app.MEANAPStatusTextArea.Value; step4startMessage];
    else 
        fprintf([step4startMessage '\n'])
    end 
    
    if Params.timeProcesses
        step4Start = tic;
    end 
    
    % Set up one figure handle to save all the figures
    if ~exist('oneFigureHandle', 'var')
        oneFigureHandle = NaN;
    end
    oneFigureHandle = checkOneFigureHandle(Params, oneFigureHandle);
    
    % Set up node cartography metrics 
    nodeCartographyMetrics = {'NCpn1', 'NCpn2', 'NCpn3', 'NCpn4', 'NCpn5','NCpn6'};
    
    % Step 4 Analysis step
    if strcmp(Params.startAnalysisSubStep, 'ALL')
        for  ExN = 1:length(ExpName) 

            if Params.priorAnalysis==1 && Params.startAnalysisStep==4
                priorAnalysisExpMatFolder = fullfile(Params.priorAnalysisPath, 'ExperimentMatFiles');
                spikeDataFname = strcat(char(ExpName(ExN)),'_',Params.priorAnalysisSubFolderName,'.mat');
                spikeDataFpath = fullfile(priorAnalysisExpMatFolder, spikeDataFname);
                expMatData = load(spikeDataFpath);
                
                if Params.suite2pMode == 0
                    load(spikeDataFpath, 'spikeTimes', 'Ephys','adjMs','Info')
                else 
                    load(spikeDataFpath, 'spks', 'fs', 'adjMs','Info')
                end
            else
                ExpMatFolder = fullfile(Params.outputDataFolder, ...
                    Params.outputDataFolderName, 'ExperimentMatFiles');
                spikeDataFname = strcat(char(ExpName(ExN)),'_',Params.outputDataFolderName,'.mat');
                spikeDataFpath = fullfile(ExpMatFolder, spikeDataFname);
                expMatData = load(spikeDataFpath);
                if Params.suite2pMode == 0
                    load(spikeDataFpath, 'Info', 'Params', 'spikeTimes', 'Ephys','adjMs')
                else
                    load(spikeDataFpath, 'Info', 'Params', 'spks', 'fs', 'adjMs')
                end 
            end
            
            if strcmp(Params.verboseLevel, 'High')
                if Params.guiMode == 1
                    app.MEANAPStatusTextArea.Value = [app.MEANAPStatusTextArea.Value; ...
                            sprintf('Running network analysis on: %s', char(Info.FN))];
                else 
                    fprintf(sprintf('Running network analysis on: %s', char(Info.FN)))
                end 
            end

            idvNetworkAnalysisGrpFolder = fullfile(Params.outputDataFolder, ...
                Params.outputDataFolderName, '4_NetworkActivity', ...
                '4A_IndividualNetworkAnalysis', char(Info.Grp));

            idvNetworkAnalysisFNFolder = fullfile(idvNetworkAnalysisGrpFolder, char(Info.FN));
            if ~isfolder(idvNetworkAnalysisFNFolder)
                mkdir(idvNetworkAnalysisFNFolder)
            end 

            if Params.priorAnalysis == 1
                if isempty(spikeDetectedData)
                    spikeDetectedDataFolder = fullfile(Params.outputDataFolder, ...
                        Params.outputDataFolderName, '1_SpikeDetection', ...
                        '1A_SpikeDetectedData');
                else 
                    spikeDetectedDataFolder = spikeDetectedData;
                end 
            else
                spikeDetectedDataFolder = fullfile(Params.outputDataFolder, ...
                        Params.outputDataFolderName, '1_SpikeDetection', ...
                        '1A_SpikeDetectedData');
            end 

            channelLayout = Params.channelLayoutPerRecording{ExN};
            
            if Params.suite2pMode
                if strcmp(Params.twopActivity, 'denoised F')
                    activityMatrix = expMatData.denoisedF;
                    Params.fs = expMatData.fs;
                    spikeTimes = [];
                elseif strcmp(Params.twopActivity, 'spks')
                    activityMatrix = expMatData.spks;
                    Params.fs = expMatData.fs;
                    spikeTimes = [];
                elseif strcmp(Params.twopActivity, 'peaks')
                    Params.fs = expMatData.fs;
                    [activityMatrix, spikeTimes, Params, Info] = formatSpikeTimes(char(Info.FN), ...
                    Params, Info, spikeDetectedDataFolder, expMatData);
                end
            else 
                [activityMatrix, spikeTimes, Params, Info] = formatSpikeTimes(char(Info.FN), ...
                    Params, Info, spikeDetectedDataFolder, expMatData);
            end

            Params.networkActivityFolder = idvNetworkAnalysisFNFolder;
            
            if isfield(expMatData, 'coords')
                coords = expMatData.coords;
                channels = expMatData.channels;
            else 
                coords = Params.coords{ExN};
                channels = Params.channels{ExN}; 
            end 
            
            NetMet = ExtractNetMet(adjMs, activityMatrix, ...
                Params.FuncConLagval, Info, Params, coords, channels, oneFigureHandle);

            ExpMatFolder = fullfile(Params.outputDataFolder, ...
                    Params.outputDataFolderName, 'ExperimentMatFiles');
            infoFnFname = strcat(char(Info.FN),'_',Params.outputDataFolderName,'.mat');
            infoFnFilePath = fullfile(ExpMatFolder, infoFnFname);
            
            varsToSave = {'Info', 'Params', 'adjMs', 'NetMet', 'coords', 'channels'}; 
            
            if Params.suite2pMode == 1
               varsToSave{end+1} = 'fs'; 
            end
            
            if exist('spikeTimes', 'var')
                varsToSave{end+1} = 'spikeTimes';
            end
            if exist('Ephys', 'var')
                varsToSave{end+1} = 'Ephys';
            end

            save(infoFnFilePath, varsToSave{:}, '-append')

            clear adjMs

        end

        % save and export network data to spreadsheet
        saveNetMet(ExpName, Params)
 
        % Set up one figure handle to save all the figures
        if ~exist('oneFigureHandle', 'var')
            oneFigureHandle = NaN;
        end
        oneFigureHandle = checkOneFigureHandle(Params, oneFigureHandle);


    % Aggregate all files and run density analysis to determine boundaries
    % for node cartography
    usePriorNetMet = 0;  % set to 0 by default
    if length(intersect(Params.netMetToCal, nodeCartographyMetrics)) >= 1
        if Params.autoSetCartographyBoundaries
            if Params.priorAnalysis==1 && usePriorNetMet
                experimentMatFileFolder = fullfile(Params.priorAnalysisPath, 'ExperimentMatFiles');
                % cd(fullfile(Params.priorAnalysisPath, 'ExperimentMatFiles'));   
                fig_folder = fullfile(Params.priorAnalysisPath, ...
                    '4_NetworkActivity', '4B_GroupComparisons', '7_DensityLandscape');
            else
                experimentMatFileFolder = fullfile(Params.outputDataFolder, ...
                    Params.outputDataFolderName, 'ExperimentMatFiles');
                % cd(fullfile(strcat('OutputData', Params.Date), 'ExperimentMatFiles'));  
                fig_folder = fullfile(Params.outputDataFolder, Params.outputDataFolderName, ...
                    '4_NetworkActivity', '4B_GroupComparisons', '7_DensityLandscape');
            end 

            if ~isfolder(fig_folder)
                mkdir(fig_folder)
            end 

            add_fig_info = '';

            if Params.autoSetCartographyBoudariesPerLag
                for lag_val = Params.FuncConLagval
                    [hubBoundaryWMdDeg, periPartCoef, proHubpartCoef, nonHubconnectorPartCoef, connectorHubPartCoef] = ...
                    TrialLandscapeDensity(Params, ExpName, experimentMatFileFolder, fig_folder, add_fig_info, lag_val, oneFigureHandle);

                    if isnan(hubBoundaryWMdDeg)
                        hubBoundaryWMdDeg = Params.hubBoundaryWMdDeg;
                        periPartCoef = Params.periPartCoef;
                        proHubpartCoef = Params.proHubpartCoef;
                        nonHubconnectorPartCoef = Params.nonHubconnectorPartCoef; 
                        connectorHubPartCoef = Params.connectorHubPartCoef;
                    end 

                    Params.(strcat('hubBoundaryWMdDeg', sprintf('_%.fmsLag', lag_val))) = hubBoundaryWMdDeg;
                    Params.(strcat('periPartCoef', sprintf('_%.fmsLag', lag_val))) = periPartCoef;
                    Params.(strcat('proHubpartCoef', sprintf('_%.fmsLag', lag_val))) = proHubpartCoef;
                    Params.(strcat('nonHubconnectorPartCoef', sprintf('_%.fmsLag', lag_val))) = nonHubconnectorPartCoef;
                    Params.(strcat('connectorHubPartCoef', sprintf('_%.fmsLag', lag_val))) = connectorHubPartCoef;
                end 

            else 
                lagValIdx = 1;
                lag_val = Params.FuncConLagval;
                [hubBoundaryWMdDeg, periPartCoef, proHubpartCoef, nonHubconnectorPartCoef, connectorHubPartCoef] = ...
                    TrialLandscapeDensity(Params, ExpName, experimentMatFileFolder, fig_folder, add_fig_info, lag_val(lagValIdx), oneFigureHandle);
                Params.hubBoundaryWMdDeg = hubBoundaryWMdDeg;
                Params.periPartCoef = periPartCoef;
                Params.proHubpartCoef = proHubpartCoef;
                Params.nonHubconnectorPartCoef = nonHubconnectorPartCoef;
                Params.connectorHubPartCoef = connectorHubPartCoef;
            end 

            % save the newly set boundaries to the Params struct
            experimentMatFileFolderToSaveTo = fullfile(Params.outputDataFolder, ...
                    Params.outputDataFolderName, 'ExperimentMatFiles');
            for nFile = 1:length(ExpName) 
                FN = ExpName{nFile};
                FNPath = fullfile(experimentMatFileFolderToSaveTo, [FN '_' Params.outputDataFolderName '.mat']);
                save(FNPath, 'Params', '-append')
            end 


        end 
        % Run through each file to do node cartography analysis 
        for ExN = 1:length(ExpName) 
            if Params.priorAnalysis==1 && Params.startAnalysisStep==4 && usePriorNetMet
                experimentMatFileFolder = fullfile(Params.priorAnalysisPath, 'ExperimentMatFiles');
                experimentMatFilePath = fullfile(experimentMatFileFolder, strcat(char(ExpName(ExN)),'_',Params.priorAnalysisSubFolderName,'.mat'));
                expData = load(experimentMatFilePath);
            else
                experimentMatFileFolder = fullfile(Params.outputDataFolder, Params.outputDataFolderName, 'ExperimentMatFiles');
                experimentMatFilePath = fullfile(experimentMatFileFolder, strcat(char(ExpName(ExN)),'_',Params.outputDataFolderName,'.mat'));
                expData = load(experimentMatFilePath);
            end
            fileNameFolder = fullfile(Params.outputDataFolder, Params.outputDataFolderName, ...
                                      '4_NetworkActivity', '4A_IndividualNetworkAnalysis', ...
                                      char(expData.Info.Grp), char(expData.Info.FN));

            if isfield(expData, 'coords')
                coords = expData.coords;  % to be saved
                channels = expData.channels; % to be saved
                originalCoords = expData.coords;
                originalChannels = expData.channels;
            else 
                originalCoords = Params.coords{ExN};
                originalChannels = Params.channels{ExN}; 
            end 

            Params.ExpNameGroupUseCoord = 1;
            NetMet = calNodeCartography(expData.adjMs, Params, expData.NetMet, expData.Info, originalCoords, originalChannels, ...
            HomeDir, fileNameFolder, oneFigureHandle);
            % save NetMet now that we have node cartography data as well
            experimentMatFileFolderToSaveTo = fullfile(Params.outputDataFolder, Params.outputDataFolderName, 'ExperimentMatFiles');
            experimentMatFilePathToSaveTo = fullfile(experimentMatFileFolderToSaveTo, strcat(char(expData.Info.FN),'_',Params.outputDataFolderName,'.mat'));

            if isfield(expData, 'spikeTimes') 
                spikeTimes = expData.spikeTimes;
            else
                spikeTimes = [];
            end 
            if isfield(expData, 'Ephys') 
                Ephys = expData.Ephys;
            else
                Ephys = [];
            end 

            varsToSave = {'Info', 'Params', 'spikeTimes', 'adjMs', 'NetMet', 'coords', 'channels', 'Ephys'};

            adjMs = expData.adjMs;  % evaluated here for saving purpose
            Info = expData.Info;
            save(experimentMatFilePathToSaveTo, varsToSave{:}, '-append')
        end
    end 
        
    end
    
    
    
    %%% 4B: create combined plots %%%
    if strcmp(Params.startAnalysisSubStep, 'ALL') || strcmp(Params.startAnalysisSubStep, 'B')
        
        if strcmp(Params.startAnalysisSubStep, 'ALL')
            experimentMatFileFolder = fullfile(Params.outputDataFolder, ... 
                Params.outputDataFolderName, 'ExperimentMatFiles');
        elseif strcmp(Params.startAnalysisSubStep, 'B')
            experimentMatFileFolder =  fullfile(Params.outputDataFolder, ... 
                strcat('OutputData', Params.priorAnalysisSubFolderName), 'ExperimentMatFiles');
        end
        % (everything except node cartography)
        PlotNetMet(ExpName, Params, experimentMatFileFolder, oneFigureHandle)

        % Plot node cartography metrics across all recordings
        if length(intersect(Params.netMetToCal, nodeCartographyMetrics)) >= 1
            NetMetricsE = Params.networkLevelNetMetToPlot;
            NetMetricsC = Params.unitLevelNetMetToPlot;
            experimentMatFileFolderToSaveTo = fullfile(Params.outputDataFolder, ...
                Params.outputDataFolderName, 'ExperimentMatFiles');
            combinedData = combineExpNetworkData(ExpName, Params, NetMetricsE, ...
                NetMetricsC, experimentMatFileFolder);
            figFolder = fullfile(Params.outputDataFolder, Params.outputDataFolderName, ...
                '4_NetworkActivity', '4B_GroupComparisons', '6_NodeCartographyByLag');
            plotNetMetNodeCartography(combinedData, ExpName,Params, HomeDir, figFolder, oneFigureHandle)
        end
    end 

    
    %%%%% 4A: individual plots %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    % 4A Part 1: General network metrics
    % Make network plots with shared colorbar and edge weight widths etc.
    if strcmp(Params.startAnalysisSubStep, 'ALL') || strcmp(Params.startAnalysisSubStep, 'A')
        outputDataDateFolder = fullfile(Params.outputDataFolder, ...
            Params.outputDataFolderName);
        
        if strcmp(Params.verboseLevel, 'High')
            if Params.guiMode == 1
                app.MEANAPStatusTextArea.Value = [app.MEANAPStatusTextArea.Value; ...
                        'Running step 4A : individual network plots'];
            else
                disp('Running step 4A : individual network plots')
            end 
        end
        
        % Search current analysis folder for csv, if none found, then use
        % the one from the previously analysed data
        spreadsheetFname = strcat('NetworkActivity_RecordingLevel', '.csv');
        if isfile(fullfile(outputDataDateFolder, spreadsheetFname))
            minMax = findMinMaxNetMetTable(outputDataDateFolder, Params);
        else
            minMax = findMinMaxNetMetTable(Params.priorAnalysisPath, Params);
        end
        
        minMax.EW = [0.1, 1];
        Params.metricsMinMax = minMax;
        Params.useMinMaxBoundsForPlots = 1;
        Params.sideBySideBoundPlots = 1;
        for ExN = 1:length(ExpName) 
            
            % Make figure handle per recording 
            % Set up one figure handle to save all the figures
            if ~exist('oneFigureHandle', 'var')
                oneFigureHandle = NaN;
            end
            oneFigureHandle = checkOneFigureHandle(Params, oneFigureHandle);
            
            if strcmp(Params.verboseLevel, 'High')
                if Params.guiMode == 1
                    app.MEANAPStatusTextArea.Value = [app.MEANAPStatusTextArea.Value; ...
                            sprintf('Plotting networks for %s', char(ExpName(ExN)))];
                else
                    disp(char(ExpName(ExN)))
                end 
            end
            
            % load NetMet 
            if isfile(fullfile(outputDataDateFolder, spreadsheetFname))
                experimentMatFileFolder = fullfile(Params.outputDataFolder, ...
                    Params.outputDataFolderName, 'ExperimentMatFiles');
                experimentMatFilePath = fullfile(experimentMatFileFolder, ...
                    strcat(char(ExpName(ExN)),'_',Params.outputDataFolderName,'.mat'));
            else
                experimentMatFileFolder = fullfile(Params.priorAnalysisPath, 'ExperimentMatFiles');
                ExpFPathSearchName = dir(fullfile(experimentMatFileFolder, [char(ExpName(ExN)), '*.mat'])).name;
                experimentMatFilePath = fullfile(experimentMatFileFolder, ExpFPathSearchName);
            end

            expData = load(experimentMatFilePath);
            idvNetworkAnalysisGrpFolder = fullfile(Params.outputDataFolder, ...
                Params.outputDataFolderName, '4_NetworkActivity', ...
                '4A_IndividualNetworkAnalysis', char(expData.Info.Grp));

            idvNetworkAnalysisFNFolder = fullfile(idvNetworkAnalysisGrpFolder, char(expData.Info.FN));
            if ~isfolder(idvNetworkAnalysisFNFolder)
                mkdir(idvNetworkAnalysisFNFolder)
            end 

            Params.networkActivityFolder = idvNetworkAnalysisFNFolder;
            
            if isfield(expData, 'coords')
                originalCoords = expData.coords;
                originalChannels = expData.channels;
                expData.Info.channels = originalChannels;
            else 
                originalCoords = Params.coords{ExN};
                originalChannels = Params.channels{ExN};
            end
            
            PlotIndvNetMet(expData, Params, expData.Info, originalCoords, originalChannels,  oneFigureHandle)

            if Params.showOneFig
                oneFigureHandle = checkOneFigureHandle(Params, oneFigureHandle);
                clf(oneFigureHandle)
            else
                close all 
            end 

            % Testing: Always close all the figures
            close all
            if strcmp(Params.verboseLevel, 'High')
                getMemoryUsage
                numTotalGraphicObjects = length(findall(groot));
                fprintf(sprintf('Total number of graphic objects: %.f \n', numTotalGraphicObjects))
            end 

        end

        % 4A Part 2: NMF individual plot
        if Params.includeNMFcomponents
            % Plot NMF 
            if isfile(fullfile(outputDataDateFolder, spreadsheetFname))
                experimentMatFolder = fullfile(Params.outputDataFolder, ...
                    Params.outputDataFolderName, 'ExperimentMatFiles');
            else
                experimentMatFolder = fullfile(Params.priorAnalysisPath, 'ExperimentMatFiles');
            end
            
            plotSaveFolder = fullfile(Params.outputDataFolder, ...
                Params.outputDataFolderName, '4_NetworkActivity', ...
                '4A_IndividualNetworkAnalysis');
            plotNMF(experimentMatFolder, plotSaveFolder, Params)
        end 

        % 4A Part 3: Node cartography individual plot
        % Plot node cartography plots using either custom bounds or
        % automatically determined bounds
        if ~exist('oneFigureHandle', 'var')
            oneFigureHandle = NaN;
        end
        oneFigureHandle = checkOneFigureHandle(Params, oneFigureHandle);
        nodeCartographyMetrics = {'NCpn1', 'NCpn2', 'NCpn3', 'NCpn4'};
        if strcmp(Params.startAnalysisSubStep, 'A')
           usePriorNetMet = 1; 
           % transfer some of the previous obtained boundary values to the new Params file 
           
        else 
           usePriorNetMet = 0;  % set to 0 by default 
        end
        
        if length(intersect(Params.netMetToCal, nodeCartographyMetrics)) >= 1
            % Group the ExpNames by their file identity, to anchor coordinates to
            % the last DIV
            for ExN = 1:length(ExpName)
                expData = loadExpData(ExpName{ExN}, Params, usePriorNetMet);
                stringParts = strsplit(ExpName{ExN}, '_');
                stringPartWithDIV_index = find(contains(stringParts, 'DIV'));
                stringPartWithoutDIV_index = find(~contains(stringParts, 'DIV'));
                ExpNamesWithoutDIV{ExN} = strjoin(stringParts(stringPartWithoutDIV_index), '_');
                divPerExN(ExN) = expData.Info.DIV{1};  
            end
            ExpNameGroup = findgroups(ExpNamesWithoutDIV);
            ExpNameGroupUseCoord = zeros(length(ExpNamesWithoutDIV), 1);
            for groupNum = unique(ExpNameGroup)
                subsetIndex = find(ExpNameGroup == groupNum);
                divMaxIndex = find(divPerExN(subsetIndex) == max(divPerExN(subsetIndex)));
                ExpNameGroupUseCoord(subsetIndex(divMaxIndex)) = 1; 
            end 

            % Loop through each group 
            for groupNum = unique(ExpNameGroup)
                fprintf(sprintf('%.f \n', groupNum))
                subsetIndex = find(ExpNameGroup == groupNum);
                % Put the recording to be used as the anchor as the first recording
                % to analyse
                [~, sort_index] = sort(ExpNameGroupUseCoord(subsetIndex), 'descend');
                ExNorderToAnalyse = subsetIndex(sort_index);
                for ExN = ExNorderToAnalyse
                    Params.ExpNameGroupUseCoord = ExpNameGroupUseCoord(ExN);
                    if Params.priorAnalysis==1 && Params.startAnalysisStep==4 && usePriorNetMet
                        experimentMatFileFolder = fullfile(Params.priorAnalysisPath, 'ExperimentMatFiles');
                        experimentMatFilePath = fullfile(experimentMatFileFolder, strcat(char(ExpName(ExN)),'_',Params.priorAnalysisSubFolderName,'.mat'));
                        expData = load(experimentMatFilePath, 'spikeTimes','Ephys','adjMs','Info', 'NetMet', 'Params', 'coords', 'channels');
                    else
                        experimentMatFileFolder = fullfile(Params.outputDataFolder, Params.outputDataFolderName, 'ExperimentMatFiles');
                        experimentMatFilePath = fullfile(experimentMatFileFolder, strcat(char(ExpName(ExN)),'_',Params.outputDataFolderName,'.mat'));
                        expData = load(experimentMatFilePath,'Info','Params', 'spikeTimes','Ephys','adjMs', 'NetMet', 'coords', 'channels');
                    end

                    fileNameFolder = fullfile(Params.outputDataFolder, Params.outputDataFolderName, ...
                                          '4_NetworkActivity', '4A_IndividualNetworkAnalysis', ...
                                          char(expData.Info.Grp), char(expData.Info.FN));

                    if isfield(expData, 'coords')
                        originalCoords = expData.coords;
                        originalChannels = expData.channels;
                        coords = expData.coords;  % for saving purpose
                        channels = expData.channels;
                    else 
                        originalCoords = Params.coords{ExN};
                        originalChannels = Params.channels{ExN};
                    end

                    % apply the anchoring index used in previous recording
                    if Params.ExpNameGroupUseCoord == 0
                        for lagval = Params.FuncConLagval
                             expData.NetMet.(sprintf('AnchoredReorderingIndex%.fmslag', lagval)) = tempNetMet.(sprintf('AnchoredReorderingIndex%.fmslag', lagval)); 
                        end
                    end

                    % note here the Params from expData is not used because there
                    % is a variable I want to preserve between runs... may come
                    % up with a better solution down the line...
                    if usePriorNetMet
                        % Adding expData.Params node cartography boundaries to
                        % Params 
                        boundaryNames = {'hubBoundaryWMdDeg', 'periPartCoef', 'proHubpartCoef', ...
                                         'nonHubconnectorPartCoef', 'connectorHubPartCoef'};
                        
                        for lagIdx = 1:length(Params.FuncConLagval)             
                            for boundaryIdx = 1:length(boundaryNames)
                                boundaryFieldName = strcat(boundaryNames{boundaryIdx}, sprintf('_%.fmsLag', Params.FuncConLagval(lagIdx)));
                                Params.(boundaryFieldName) = expData.Params.(boundaryFieldName);
                            end
                        end 
                    end 

                    % TODO: remove the analysis step in the function, already
                    % dealt with earlier
                    NetMet = plotNodeCartography(expData.adjMs, Params, expData.NetMet, ...
                          expData.Info, originalCoords, originalChannels, ...
                          HomeDir, fileNameFolder, oneFigureHandle);
                    % plotNodeCartographyProportions(expData.NetMet, Params.FuncConLagval, char(expData.Info.FN), ...
                    % Params, fileNameFolder, oneFigureHandle)
                    % save NetMet now that we have node cartography data as well
                    experimentMatFileFolderToSaveTo = fullfile(Params.outputDataFolder, Params.outputDataFolderName, 'ExperimentMatFiles');
                    experimentMatFilePathToSaveTo = fullfile(experimentMatFileFolderToSaveTo, strcat(char(expData.Info.FN),'_',Params.outputDataFolderName,'.mat'));

                     if isfield(expData, 'spikeTimes') 
                        spikeTimes = expData.spikeTimes;
                     else
                        spikeTimes = [];
                     end 
                     if isfield(expData, 'Ephys') 
                        Ephys = expData.Ephys;
                     else
                        Ephys = [];
                     end 

                    varsToSave = {'Info', 'Params', 'spikeTimes', 'adjMs', ...
                        'NetMet', 'coords', 'channels', 'Ephys'};

                    adjMs = expData.adjMs;
                    Info = expData.Info;
                    save(experimentMatFilePathToSaveTo, varsToSave{:})

                    % save the current in use reordering index 
                    for lagval = Params.FuncConLagval
                        tempNetMet.(sprintf('AnchoredReorderingIndex%.fmslag', lagval)) = NetMet.(sprintf('AnchoredReorderingIndex%.fmslag', lagval)); 
                    end
                end
            end
        end 
    end 
    
    if Params.timeProcesses
        step4Duration = toc(step4Start);
    end 

end

%% Optional step: Run density landscape to determine the boundaries for the node cartography 
if any(strcmp(Params.optionalStepsToRun,'getDensityLandscape')) 
    cd(fullfile(Params.priorAnalysisPath, 'ExperimentMatFiles'));
    
    fig_folder = fullfile(Params.priorAnalysisPath, '4_NetworkActivity', ...
        '4B_GroupComparisons', '7_DensityLandscape');
    if ~isfolder(fig_folder)
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
% Statistics and machine learning settings 
% Params.classificationTarget = 'AgeDiv';  % which property of the recordings to classify 
Params.classification_models = {'linearSVM', 'kNN', 'decisionTree', 'LDA'}; % 'fforwardNN'
Params.regression_models = {'svmRegressor', 'regressionTree', 'ridgeRegression', 'fforwardNN'};
Params.statsRandomSeed = 1;

if any(strcmp(Params.optionalStepsToRun,'Stats'))
    if Params.showOneFig
        if ~isfield(Params, 'oneFigure')
            Params.oneFigure = figure;
        end 
    end 
    
    if Params.priorAnalysis && Params.startAnalysisStep >= 5
        statsDataFolder = Params.priorAnalysisPath;
    else
        statsDataFolder = fullfile(Params.outputDataFolder, ...
                Params.outputDataFolderName);
    end 
    
    nodeLevelFile = fullfile(statsDataFolder, 'NetworkActivity_NodeLevel.csv');
    nodeLevelData = readtable(nodeLevelFile);
    
    recordingLevelFile = fullfile(statsDataFolder, 'NetworkActivity_RecordingLevel.csv');
    recordingLevelData = readtable(recordingLevelFile);

    % Traditional Statistics
    statsTable = doStats(recordingLevelData, 'recordingLevel', Params);
    statsTableSavePath = fullfile(statsDataFolder, 'stats.csv');
    writetable(statsTable, statsTableSavePath);
    oneFigureHandle = NaN;
    oneFigureHandle = checkOneFigureHandle(Params, oneFigureHandle);
    plotSaveFolder = fullfile(statsDataFolder, '5_Stats');
    if ~isfolder(plotSaveFolder)
        mkdir(plotSaveFolder)
    end 
    plotStats(statsTable, plotSaveFolder, Params, oneFigureHandle)
    
    % nodeStatsTable = doStats(nodeLevelData, 'nodeLevel', Params);
    
    
    % Classification and Regression 
    for lag_val = Params.FuncConLagval
        plotSaveFolder = fullfile(statsDataFolder, '5_Stats', sprintf('%.fmsLag', lag_val));
        if ~isfolder(plotSaveFolder)
            mkdir(plotSaveFolder)
        end 
        featureCorrelation(nodeLevelData, recordingLevelData, Params, lag_val, plotSaveFolder);
        doLDA(recordingLevelData, Params, lag_val);
        doClassification(recordingLevelData, Params, lag_val, plotSaveFolder, oneFigureHandle);
    end 


end 

%% Optional step : combine plots across DIVs
if any(strcmp(Params.optionalStepsToRun,'Combine Plots'))
    if Params.priorAnalysis == 1
        featureFolder = fullfile(Params.priorAnalysisPath, '4_NetworkActivity', '4A_IndividualNetworkAnalysis');
    else
        featureFolder = fullfile(Params.outputDataFolder, Params.outputDataFolderName, '4_NetworkActivity', '4A_IndividualNetworkAnalysis');
    end 
    featureFolderSearch = dir(featureFolder);
    dirFlags = [featureFolderSearch.isdir];
    folderNames = {featureFolderSearch.name};
    groupFolders = folderNames(dirFlags);
    groupFolders = groupFolders(~ismember(groupFolders, {'.', '..'}));
    combinedPlotFolder = fullfile(Params.outputDataFolder, ['OutputData' Params.Date], ...
        '4_NetworkActivity', '4B_GroupComparisons', '8_CombinedPlotsByDiv');
    if 1 - isfolder(combinedPlotFolder)
        mkdir(combinedPlotFolder)
    end 
    
    for grpNameIdx = 1:length(Params.GrpNm)
        combinedPlotGroupFolder = fullfile(combinedPlotFolder, Params.GrpNm{grpNameIdx});
        if 1 - isfolder(combinedPlotGroupFolder)
            mkdir(combinedPlotGroupFolder)
        end 
    end 
    
    Params.includeIdvScaledPlotsInCombinedPlots = 1;
    Params.plotNames = {'3_scaled_MEA_NetworkPlotNodedegreeBetweennesscentrality.png', ...
                        '4_scaled_MEA_NetworkPlotNodedegreeParticipationcoefficient.png', ...
                        '5_scaled_MEA_NetworkPlotNodestrengthLocalefficiency.png', ...
                        '10_scaled_MEA_NetworkPlotNodedegreeAveragecontrollability.png', ... 
                        '11_scaled_MEA_NetworkPlotNodedegreeModalcontrollability.png', ...
                        '2_scaled_MEA_NetworkPlot.png', ...
                        };


    for nGroupFolder = 1:length(groupFolders)

        % get the recording folders 
        groupFolder = fullfile(featureFolder, groupFolders{nGroupFolder});
        groupFolderSearch = dir(groupFolder);
        dirFlags = [groupFolderSearch.isdir];
        folderNames = {groupFolderSearch.name};
        recordingFolders = folderNames(dirFlags);
        recordingFolders = recordingFolders(~ismember(recordingFolders, {'.', '..'}));

        % get the recording name excluding DIV 
        numRecordings = length(recordingFolders);
        recordingNames = cell(numRecordings, 1);
        for recordingIdx = 1:numRecordings
            recordingNameParts = split(recordingFolders{recordingIdx}, '_');
            recordingNames(recordingIdx) = join(recordingNameParts(1:end-1), '_');
        end 

        uniqueRecordings = unique(recordingNames);

        for uniqueRecordingIdx = 1:length(uniqueRecordings)

            recordingName = uniqueRecordings{uniqueRecordingIdx};
            recordingDIVfoldersSearch = dir(fullfile(groupFolder, sprintf('%s*', recordingName)));
            dirFlags = [recordingDIVfoldersSearch.isdir];
            recordingDIVfoldersSearchNames = {recordingDIVfoldersSearch.name};
            recordingDIVfolders = recordingDIVfoldersSearchNames(dirFlags);
            recordingDIVfolders = recordingDIVfolders(~ismember(recordingDIVfolders, {'.', '..'}));

            recordingDIVfolderFullPath = fullfile(groupFolder, recordingDIVfolders{1});
            recordingDIVfoldersSearch = dir(recordingDIVfolderFullPath);
            dirFlags = [recordingDIVfoldersSearch.isdir];
            recordingDIVfoldersSearchNames = {recordingDIVfoldersSearch.name};
            lagFolders = recordingDIVfoldersSearchNames(dirFlags);
            lagFolders = lagFolders(~ismember(lagFolders, {'.', '..'}));

            for lagIdx = 1:length(lagFolders)
                for plotNameIdx = 1:length(Params.plotNames)
                    % make the list of plot paths to combine
                    plotName = Params.plotNames{plotNameIdx};
                    plotPathsToCombine = cell(length(recordingDIVfolders), 1);

                    for divIdx = 1:length(recordingDIVfolders)
                        plotPathsToCombine{divIdx} = fullfile(...
                        groupFolder, recordingDIVfolders{divIdx}, ...
                        lagFolders{lagIdx}, plotName);
                    end 

                    % save the plot in 4B
                    outputFolder = fullfile(combinedPlotFolder, ...
                        groupFolders{nGroupFolder}, recordingName, ...
                        lagFolders{lagIdx});
                    if 1 - isdir(outputFolder)
                        mkdir(outputFolder)
                    end 
                    outputFilePath = fullfile(outputFolder,  plotName(1:end-4)); 
                    %  outputFilePath = fullfile(recordingDIVfolderFullPath, ... 
                    %     sprintf('combined_%s_%s', lagFolders{lagIdx}, plotName(1:end-4)));

                    combinePlots(plotPathsToCombine, outputFilePath, Params)

                end 
            end 

        end

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

%% Provide summary of MEA-NAP run 
if Params.guiMode == 1
    app.MEANAPStatusTextArea.Value = [app.MEANAPStatusTextArea.Value; ...
        'MEA-NAP run completed successfully'];
    fprintf('MEA-NAP run completed successfully \n')
else
    fprintf('MEA-NAP run completed successfully \n')
end

if Params.timeProcesses
    if exist('step1Duration', 'var')
        if Params.guiMode == 1
            app.MEANAPStatusTextArea.Value = [app.MEANAPStatusTextArea.Value; ...
                    sprintf('Step 1 duration (seconds): %.f \n', step1Duration)];
        else 
            fprintf(sprintf('Step 1 duration (seconds): %.f \n', step1Duration))
        end
    end
    if exist('step2Duration', 'var')
        if Params.guiMode == 1
            app.MEANAPStatusTextArea.Value = [app.MEANAPStatusTextArea.Value; ...
                    sprintf('Step 2 duration (seconds): %.f \n', step2Duration)];
        else 
            fprintf(sprintf('Step 2 duration (seconds): %.f \n', step2Duration))
        end
    end
    if exist('step3Duration', 'var')
        if Params.guiMode == 1
            app.MEANAPStatusTextArea.Value = [app.MEANAPStatusTextArea.Value; ...
                    sprintf('Step 3 duration (seconds): %.f \n', step3Duration)];
        else 
            fprintf(sprintf('Step 3 duration (seconds): %.f \n', step3Duration))
        end
    end
    if exist('step4Duration', 'var')
        if Params.guiMode == 1
            app.MEANAPStatusTextArea.Value = [app.MEANAPStatusTextArea.Value; ...
                    sprintf('Step 4 duration (seconds): %.f \n', step4Duration)];
        else 
            fprintf(sprintf('Step 4 duration (seconds): %.f \n', step4Duration))
        end
    end
end

%% Check if user wants to view outputs 
if Params.guiMode == 1
    while isvalid(app)
       % Launch MEANAP viewer 
        if app.ViewOutputsButton.Value == 1
            runMEANAPviewer;
            app.ViewOutputsButton.Value = 0;
        end 
        pause(0.1);
    end
end 

end 

