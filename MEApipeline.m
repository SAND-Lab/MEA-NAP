% Process data from MEA recordings of 2D and 3D cultures
% created: RCFeord, May 2021
% authors: T Sit, RC Feord, AWE Dunn, J Chabros and other members of the Synaptic and Network Development (SAND) Group


%% USER INPUT REQUIRED FOR THIS SECTION
% in this section all modifiable parameters of the analysis are defined,
% no subsequent section requires user input
% please refer to the documentation for guidance on parameter choice

% Set parameters

% set analysis folder to home directory (folder with AnalysisPipeline scripts)
HomeDir = '/Users/timothysit/AnalysisPipeline'; %for Mac '/yourpath' for PC '\yourpath'
% add all relevant folders to path
cd(HomeDir)
addpath(genpath('Functions'))
addpath('Images')

% data input from excel spreadheet or csv file with the following structure
%      column 1: filename of recording (omit .mat at the end of the filename), 
%      column 2: DIV or age of sample (should whole numbers), 
%      column 3: group, cell line, or condition (groups will be plotted in alphabetic order, 
%                do not use numbers in group names) 
%      column 4: any electrode numbers you wish to ground (check electrode naming for your MEA data files; 
%                for MCS 60 channel data, electrode 15--the reference electrode should be included here)
% 
% spreadsheet_file_type: datatype of the spreadsheet 
% option 1: csv (comma separated values)
% option 2: excel (excel spreadsheet, eg. .xlsx)
spreadsheet_file_type = 'csv'; % 'csv';
% spread_sheet_filename = 'myRecordingsList.xlsx'; % name of excel spreadsheet
% spreadsheet_filename = 'myRecordingsList.csv'; % name of csv file
spreadsheet_filename = 'hpc_dataset_subset.csv'; % other examples
% spreadsheet_filename = 'axiontest2.csv';
% spreadsheet_filename = 'axiontest_wExcludedElectrode.csv';

% These options only apply if using excel spreadsheet
sheet = 1; % specify excel sheet
xlRange = 'A2:C7'; % specify range on the sheet (e.g., 'A2:C7' would analyse the first 6 files)

% get date
formatOut = 'ddmmmyyyy'; Params.Date = datestr(now,formatOut); clear formatOut

% specify analysis output format ('excel' for .xlsx files and 'csv' for
% .csv files)
Params.output_spreadsheet_file_type = 'csv';


% Sampling frequency of your recordings
Params.fs = 25000; % HPC: 25000, Axion: 12500;
Params.dSampF = 25000; % down sampling factor for spike detection check, 
% by default should be equal to your recording sampling frequency
Params.potentialDifferenceUnit = 'uV';  % the unit which you are recording electrical signals 
% if this is a number, then will multiply this number to get potential
% difference in units of V

% use previously analysed data?
Params.priorAnalysis = 1; % 1 = yes, 0 = no
% path to previously analysed data
Params.priorAnalysisPath = ['/Users/timothysit/AnalysisPipeline/OutputData20Jan2022v3']; % example format
% Params.priorAnalysisPath = ['/Users/timothysit/AnalysisPipeline/OutputData16Feb2022'];
% prior analysis date in format given in output data folder e.g., '27Sep2021'
Params.priorAnalysisDate = '20Jan2022';
%Params.priorAnalysisDate = '16Feb2022';
% which section to start new analysis from:
% 2 = neuronal activity (uses spike detection from step 1)
% 3 = functional connectivity (uses spike detection from step 1)
% 4 = network activity (uses functional connectivity outputs from step 3)
Params.startAnalysisStep = 1; % if Params.priorAnalysis=0 (line 56), default is to start with spike detection
Params.optionalStepsToRun = {''};
% Supported optional steps: 
% getDensityLandscape : calculate and plot distribution of participation
% coefficient and centrality 
% runstats : calculates correlation of features across recording, and do 
% classification of DIV and/or recording condition (eg. genotype) based 
% on network metrics
% generateCSV : generate CSV with file paths given folder containing mat files
% comparePrePostTTX : compare pre/post TTX activity in data

% run spike detection?
detectSpikes = 0; % 1 = yes, 0 = no
Params.runSpikeCheckOnPrevSpikeData = 1;  % whether to run spike detection check without spike deteciton 

if Params.runSpikeCheckOnPrevSpikeData
    fprintf(['You specified to run spike detection check on previously extracted spikes, \n', ... 
            'so I will skip over the spike detection step \n'])
    detectSpikes = 0;
end 

% specify folder with raw data files for spike detection
% currently does not accept path names with colon in them
rawData = '/Volumes/T7/schroter2015_mat';
% rawData = '/Users/timothysit/AnalysisPipeline/localRawData';
% rawData = '/Users/timothysit/AnalysisPipeline/2022-03-16-test-raw-data';
% advanced settings are automatically set but can be modified by opening
% the following function
biAdvancedSettings
% To perform threshold-based spike detection, list the standard deviation multiplier threshold(s).  
% the threshold is mean(voltage) - Params.thresholds * sem(voltage) (or std(voltage))
% leave empty as {} if you don't want to perform threshold-based spike detection 
% threshold-based spike detection
Params.thresholds = {}; % {'2.5', '3.5', '4.5'}
% To perform template-based spike detection, list the built in wavelets 
% For more information about wavelets, type `waveinfo` into matlab 
% or see: https://uk.mathworks.com/help/wavelet/ref/waveinfo.html
% The usual wavelets that we observe good results with for detecting spikes 
% are 'bior1.5', 'bior1.3', and 'db' wavelets.
% To use custom electrode-specific wavelets based on the average waveform detected
% with the threshold method, use 'mea' for .wnameList and select a SD multiplier .threshold (e.g., 4).
% To perform the stationery wavelet transform method, enter 'swtteo' (we have not optimized this).
% Set to empty {}' if you only want to run threshold spike detection
Params.wnameList = {'bior1.5'}; % {'bior1.5', 'mea'}';

% Specify the cost parameter used in the template-based spike detection,  
% which controls the false positive / false negative tradeoff in spike detection 
% more negative values leads to less false negative but more false
% positives, recommended range is between -2 to 2, but usually we use 
% -1 to 0. Note that this is in a log10 scale, meaning -1 will lead to 10
% times more false positive compared to -0.1
% For more details see Nenadic and Burdick 2005: Spike detection using the continuous wavelet transform
Params.costList = -0.12;
% if spike detection has been run separately, specify the folder containing
% the spike detected data; e.g., '/Users/yourpath/AnalysisPipeline/OutputData20Jan2022v3';
spikeDetectedData = '/Users/timothysit/AnalysisPipeline/OutputData20Jan2022v3';

% Set the spike method to be used in downstream analysis, use 'merged if all
% wavelet-based spike detection methods should be combined, otherwise specify method.
% 'thr3p0': means using a threshold-based method with a multiplier of 3.0
% you can specify other thresholds by replacing the decimal place '.' with
% 'p', eg. 'thr4p5' means a threhold multiplier of 4.5
% 'bio1p5': use spikes from the bior1.5 wavelet, you can also specify other
% wavelet names
% 'mea': use spikes from electrode-specific custom wavelets (adapted from putative spikes
% detected using the theshold method)
% 'merged': merge the spike detection results from the wavelets specified 
% in Params.wnameList
Params.SpikesMethod = 'bior1p5'; % 'thr3p0','mea','merged', 'bior1p5' etc.
% TODO: make sure SpikesMethod is a subset of wnameList 

% set parameters for functional connectivity inference
Params.FuncConLagval = [10 15 25]; % set the different lag values (in ms)
Params.TruncRec = 0; % truncate recording? 1 = yes, 0 = no
Params.TruncLength = 120; % length of truncated recordings (in seconds)

% set parameters for connectivity matrix thresholding
Params.ProbThreshRepNum = 200; % probabilistic thresholding number of repeats 
Params.ProbThreshTail = 0.05; % probabilistic thresholding percentile threshold 
Params.ProbThreshPlotChecks = 1; % randomly sample recordings to plot probabilistic thresholding check, 1 = yes, 0 = no
Params.ProbThreshPlotChecksN = 5; % number of random checks to plot

% set parameters for graph theory
Params.adjMtype = 'weighted'; % 'weighted' or 'binary'

% figure formats
Params.figMat = 0; % figures saved as .mat format, 1 = yes, 0 = no
Params.figPng = 1; % figures saved as .png format, 1 = yes, 0 = no
Params.figEps = 0; % figures saved as .eps format, 1 = yes, 0 = no

% Stop figures windows from popping up (steals windows focus on linux
% machines at least) when set to 1 (by only plotting on one figure handle)
Params.showOneFig = 1;  % otherwise, 0 = pipeline shows plots as it runs

%% END OF USER REQUIRED INPUT SECTION
% The rest of the MEApipeline.m runs automatically. Do not change after this line
% unless you are an expert user.

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
    Params.network_plot_cmap_bounds = network_plot_cmap_bounds;
else 
    het_node_level_vals = 0;
    if Params.use_min_max_all_recording_bounds
        
    elseif Params.use_min_max_per_genotype_bounds

    end 
end 


%% setup - additional setup

% import metadata from spreadsheet
if strcmp(spreadsheet_file_type, 'excel')
    [num,txt,~] = xlsread(spreadsheet_filename,sheet,xlRange);
    ExpName = txt(:,1); % name of recording
    ExpGrp = txt(:,3); % name of experimental group
    ExpDIV = num(:,1); % DIV number
elseif strcmp(spreadsheet_file_type, 'csv')
    csv_data = readtable(spreadsheet_filename, 'Delimiter','comma');
    ExpName =  csv_data{:, 1};
    ExpGrp = csv_data{:, 3};
    ExpDIV = csv_data{:, 2};
    if sum(strcmp('Ground',csv_data.Properties.VariableNames))
        Params.electrodesToGroundPerRecording = csv_data.('Ground');
    else 
        Params.electrodesToGroundPerRecording = [];
    end 
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

if (Params.priorAnalysis == 0) || (Params.runSpikeCheckOnPrevSpikeData)

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

if Params.showOneFig
    % TODO: do this for spike detection plots as well, and PlotNetMet
    Params.oneFigure = figure;
end 

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
        NetMet =ExtractNetMetOrganoid(adjMs, spikeTimes, Params.FuncConLagval,Info,HomeDir,Params);

        cd(HomeDir); cd(strcat('OutputData',Params.Date)); cd('ExperimentMatFiles')

        save(strcat(char(Info.FN),'_',Params.Date,'.mat'),'Info','Params','spikeTimes','Ephys','adjMs','NetMet')
        cd(HomeDir)

        clear adjMs

    end

    % create combined plots
    PlotNetMet(ExpName,Params,HomeDir)
    cd(HomeDir)

end

%% Optional step: Run density landscape to determine the boundaries for the node cartography 
if ~any(strcmp(Params.optionalStepsToRun,'getDensityLandscape')) 
    Params.priorAnalysisPath = '/Users/timothysit/AnalysisPipeline/OutputData24Feb2022';
    cd(fullfile(Params.priorAnalysisPath, 'ExperimentMatFiles'));
    
    fig_folder = fullfile(Params.priorAnalysisPath, '4_NetworkActivity/4B_GroupComparisons/7_DensityLandscape');
    if ~isdir(fig_folder)
        mkdir(fig_folder)
    end 
    
    % loop through multiple DIVs
    for DIV = [14, 17, 21, 24, 28]
        ExpList = dir(sprintf('*DIV%.f*.mat', DIV));
        add_fig_info = strcat('DIV', num2str(DIV));
        TrialLandscapeDensity;
    end 
end 

%% Optional step: statistics and classification of genotype / ages 
if ~any(strcmp(Params.optionalStepsToRun,'runStats')) 
    Params.priorAnalysisPath = '/Users/timothysit/AnalysisPipeline/OutputData24Feb2022';
    nodeLevelFile = fullfile(Params.priorAnalysisPath, 'NetworkActivity_NodeLevel.csv');
    nodeLevelData = readtable(nodeLevelFile);
    
    recordingLevelFile = fullfile(Params.priorAnalysisPath, 'NetworkActivity_RecordingLevel.csv');
    recordingLevelData = readtable(recordingLevelFile);
    
    featureCorrelation(nodeLevelData, recordingLevelData, Params);
end 


%% Optional Step: compare pre-post TTX spike activity 
if ~any(strcmp(Params.optionalStepsToRun,'comparePrePostTTX')) 
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

%% Optional step : generate csv 
if ~any(strcmp(Params.optionalStepsToRun,'generateCSV')) 
    folder_path = '/Volumes/T7/schroter2015_mat'; 
    mat_file_list = dir(fullfile(folder_path, '*mat'));
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
    writetable(name_table, 'test.csv')
end 



