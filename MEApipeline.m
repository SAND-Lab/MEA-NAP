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
% spreadsheet_file_type: datatype of the spreadsheet 
% option 1: csv (comma separated values)
% option 2: excel (excel spreadsheet, eg. .xlsx)
spreadsheet_file_type = 'csv';
% spread_sheet_filename = 'mecp2RecordingsList.xlsx'; % name of excel spreadsheet
spreadsheet_filename = 'mecp2RecordingsList.csv'; % name of csv file

% These options only apply if using excel spreadsheet
sheet = 1; % specify excel sheet
xlRange = 'A2:C7'; % specify range on the sheet

% get date
formatOut = 'ddmmmyyyy'; Params.Date = datestr(now,formatOut); clear formatOut

% Sampling frequency of your recordings
Params.fs = 25000;

% use previously analysed data?
Params.priorAnalysis = 1; % 1 = yes, 0 = no
% path to previously analysed data
Params.priorAnalysisPath = '/home/timsit/AnalysisPipeline/OutputData24Dec2021';
% prior analysis date in format given in output data folder e.g '27Sep2021'
Params.priorAnalysisDate = '24Dec2021';
% which section to start new analysis from? 2 = neuronal activity, 3 =
% functional connectivity, 4 = network activity
Params.startAnalysisStep = 4;

% run spike detection?
detectSpikes = 1; % 1 = yes, 0 = no
% specify folder with raw data files for spike detection
rawData = '/media/timsit/timsitHD-2020-03/mecp2/rawFiles/';
% advanced settings are automatically set but can be modified by opening
% the following function
biAdvancedSettings
% list of thresholds for spike detection, this is used for threshold-based 
% spike detection, where thershold is mean(voltage) - Params.thresholds *
% sem(voltage) (or std(voltage))
Params.thresholds = {'4.5'}; % {'2.5', '3.5', '4.5'}

% list of built in wavelets and associated cost parameters
% For more information about wavelets, type `waveinfo` into matlab 
% or see: https://uk.mathworks.com/help/wavelet/ref/waveinfo.html
% The usual wavelest that we observe good results are the (bior1.5,
% bior1.3, and 'db' wavelets
Params.wnameList = {'bior1.5'}';

% Specify the cost parameter used in spike detection, which controls 
% the false positive / false negative tradeoff in spike detection 
% more negative values leads to less false negative but more false
% positives, recommended range is between -2 to 2, but usually we use 
% -1 to 0. Note that this is in a log10 scale, meaning -1 will lead to 10
% times more false positive compared to -0.1
% For more details see 
% Nenadic and Burdick 2005: Spike detection using the continuous wavelet
% transform
Params.costList = -0.12;
% if spike detection has been run separately, specify the folder containing
% the spike detected data
spikeDetectedData = '/home/timsit/AnalysisPipeline/spikeFilesOutput';
% set spike method to be used in downstream analysis, use 'merged if all
% spike detection methods should be combined, otherwise specify method

% Spike detection method 
% 'thr3p0': means using a threshold-based method with a multiplier of 3.0
% you can specify other thresholds by replacing the decimal place '.' with
% 'p', eg. 'thr4p5' means a threhold multiplier of 4.5
% 'mea': first detect putative spikes using the threshold method, then 
% use them to construct a custom wavelet, then use wavelet spike detection 
% 'merged': merge the spike detection results from the wavelets specified 
% in Params.wnameList
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


% Network plot colormap bounds 
Params.use_theoretical_bounds = 1;
Params.use_min_max_all_recording_bounds = 0;

if Params.use_theoretical_bounds
    network_plot_cmap_bounds = struct();
    network_plot_cmap_bounds.CC = [0, 1];
    network_plot_cmap_bounds.PC = [0, 1];
    network_plot_cmap_bounds.Z = [-2, 2];
    network_plot_cmap_bounds.BC = [0, 1];
    network_plot_cmap_bounds.Eloc = [0, 1];
    Params.network_plot_cmap_bounds = network_plot_cmap_bounds;
end 




%% setup - additional setup

% import metadata from spreadsheet
if strcmp(spreadsheet_file_type, 'excel')
    [num,txt,~] = xlsread(spreadsheet_filename,sheet,xlRange);
    ExpName = txt(:,1); % name of recording
    ExpGrp = txt(:,3); % name of experimental group
    ExpDIV = num(:,1); % DIV number
elseif strcmp(spreadsheet_file_type, 'csv')
    csv_data = readtable(spreadsheet_filename);
    ExpName =  csv_data{:, 1};
    ExpGrp = csv_data{:, 3};
    ExpDIV = csv_data{:, 2};
end 

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
    % PlotNetMet(ExpName,Params,HomeDir)
    % cd(HomeDir)

end
