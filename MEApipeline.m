% Process data from MEA recordings of 2D and 3D cultures
% author: RCFeord, May 2021


%% USER INPUT REQUIRED FOR THIS SECTION
% in this section all modifiable parameters of the analysis are defined, no
% subsequent section requires user input
% please refer to the documentation for guidance on parameter choice

% Set parameters

% set analysis folder to home directory
HomeDir = '/home/timsit/AnalysisPipeline/';
% add all relevant folders to path
cd(HomeDir)
addpath(genpath('Functions'))
addpath('Images')

% data input from excel spreadheet, column 1: name of recording, column 2:
% DIV/age of sample, column 3: group/cell line
xlsfilename = 'mecp2RecordingsList.xlsx'; % name of excel spreadsheet
sheet = 1; % specify excel sheet
xlRange = 'A2:C7'; % specify range on the sheet

% get date
formatOut = 'ddmmmyyyy'; Params.Date = datestr(now,formatOut); clear formatOut

% Sampling frequency of your recordings
Params.fs = 25000;

% use previously analysed data?
Params.priorAnalysis = 0; % 1 = yes, 0 = no
% path to previously analysed data
Params.priorAnalysisPath = '/home/timsit/AnalysisPipeline/OutputData02Dec2021v3';
% prior analysis date in format given in output data folder e.g '27Sep2021'
Params.priorAnalysisDate = '02Dec2021';
% which section to start new analysis from? 2 = neuronal activity, 3 =
% functional connectivity, 4 = network activity
Params.startAnalysisStep = 2;

% run spike detection?
detectSpikes = 1; % 1 = yes, 0 = no
% specify folder with raw data files for spike detection
rawData = '/home/timsit/AnalysisPipeline/rawFiles';
% advanced settings are automatically set but can be modified by opening
% the following function
biAdvancedSettings
% list of thresholds for spike detection
Params.thresholds = {'4.5'}; % {'2.5', '3.5', '4.5'}
% list of built in wavelets and associated cost parameters
Params.wnameList = {'bior1.5'}';
Params.costList = -0.12;
% if spike detection has been run separately, specify the folder containing
% the spike detected data
spikeDetectedData = '/home/timsit/AnalysisPipeline/spikeFilesOutput';
% set spike method to be used in downstream analysis, use 'merged if all
% spike detection methods should be combined, otherwise specify method
Params.SpikesMethod = 'merged'; % 'thr3p0','mea','merged'

% set parameters for functional connectivity inference
Params.FuncConLagval = [10 15 25]; % set the different lag values (in ms)
Params.TruncRec = 0; % truncate recording? 1 = yes, 0 = no
Params.TruncLength = 120; % length of truncated recordings (in seconds)

% set parameters for connectivity matrix thresholding
Params.ProbThreshRepNum = 200; % probabilistic thresholding number of repeats
Params.ProbThreshTail = 0.10; % probabilistic thresholding percentile threshold
Params.ProbThreshPlotChecks = 1; % randomly sample recordings to plot probabilistic thresholding check, 1 = yes, 0 = no
Params.ProbThreshPlotChecksN = 5; % number of random checks to plot

% set parameters for graph theory
Params.adjMtype = 'weighted'; % 'weighted' or 'binary'

% figure formats
Params.figMat = 1; % figures saved as .mat format, 1 = yes, 0 = no
Params.figPng = 1; % figures saved as .png format, 1 = yes, 0 = no
Params.figEps = 0; % figures saved as .eps format, 1 = yes, 0 = no

% Stop figures windows from popping up (steals windows focus on linux
% machines at least)
Params.showFig = 0;  % TODO: set(h1, 'Visible', 'off'); when h1 is the figure handle

%% setup - additional setup

% import metadata from spreadsheet
[num,txt,~] = xlsread(xlsfilename,sheet,xlRange);
ExpName = txt(:,1); % name of recording
ExpGrp = txt(:,3); % name of experimental group
ExpDIV = num(:,1); % DIV number
[~,Params.GrpNm] = findgroups(ExpGrp);
[~,Params.DivNm] = findgroups(ExpDIV);

% create output data folder if doesn't exist
CreateOutputFolders(HomeDir,Params.Date,Params.GrpNm)

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

if Params.priorAnalysis == 0

    if detectSpikes == 1
        addpath(rawData)
    else
        addpath(spikeDetectedData)
    end

    savePath = strcat(HomeDir,'/OutputData',Params.Date,'/1_SpikeDetection/1A_SpikeDetectedData/');
    savePath(strfind(savePath,'\'))='/';

    batchDetectSpikes(rawData, savePath, option, ExpName, Params);
    cd(HomeDir)

    for  ExN = 1:length(ExpName)

        cd(strcat(HomeDir,'/OutputData',Params.Date,'/1_SpikeDetection/1A_SpikeDetectedData/'))
        load(strcat(char(ExpName(ExN)),'_spikes.mat'),'spikeTimes','spikeDetectionResult','channels','spikeWaveforms')
        cd(HomeDir); cd(strcat('OutputData',Params.Date)); cd('ExperimentMatFiles')
        load(strcat(char(ExpName(ExN)),'_',Params.Date,'.mat'),'Info')

        cd(HomeDir); cd(strcat('OutputData',Params.Date))
        cd('1_SpikeDetection'); cd('1B_SpikeDetectionChecks'); cd(char(Info.Grp))
        plotSpikeDetectionChecks(spikeTimes,spikeDetectionResult,spikeWaveforms,Info,Params)
        cd(HomeDir)

    end

end

%% Step 2 - neuronal activity

if Params.priorAnalysis==0 || Params.priorAnalysis==1 && Params.startAnalysisStep<3

    % Format spike data

    for  ExN = 1:length(ExpName)

        cd(strcat('OutputData',Params.Date)); cd('ExperimentMatFiles')
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
        cd('2A_IndividualNetworkAnalysis'); cd(char(Info.Grp))
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
        save(strcat(char(Info.FN),'_',Params.Date,'.mat'),'Info','Params','spikeTimes','Ephys')
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
            path(strfind(savepath,'\'))='/'; cd(path)
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

if Params.priorAnalysis==0 || Params.priorAnalysis==1 && Params.startAnalysisStep<=4

    for  ExN = 1:length(ExpName)

        if Params.priorAnalysis==1 && Params.startAnalysisStep==4
            path = strcat(Params.priorAnalysisPath,'/ExperimentMatFiles/');
            path(strfind(savepath,'\'))='/'; cd(path)
            load(strcat(char(ExpName(ExN)),'_',Params.priorAnalysisDate,'.mat'),'spikeTimes','Ephys','adjMs','Info')
        else
            cd(strcat('OutputData',Params.Date)); cd('ExperimentMatFiles')
            load(strcat(char(ExpName(ExN)),'_',Params.Date,'.mat'),'Info','Params','spikeTimes','Ephys','adjMs')
        end
        cd(HomeDir)

        disp(char(Info.FN))

        cd(strcat('OutputData',Params.Date)); cd('4_NetworkActivity')
        cd('4A_IndividualNetworkAnalysis'); cd(char(Info.Grp))
        NetMet = ExtractNetMetOrganoid(adjMs,Params.FuncConLagval,Info,HomeDir,Params);

        cd(HomeDir); cd(strcat('OutputData',Params.Date)); cd('ExperimentMatFiles')
        save(strcat(char(Info.FN),'_',Params.Date,'.mat'),'Info','Params','spikeTimes','Ephys','adjMs','NetMet')
        cd(HomeDir)

        clear adjMs

    end

    % create combined plots
    PlotNetMet(ExpName,Params,HomeDir)
    cd(HomeDir)

end
