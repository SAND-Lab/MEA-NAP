classdef getSpikesApp < matlab.apps.AppBase
    
    % Properties that correspond to app components
    properties (Access = public)
        UIFigure                        matlab.ui.Figure
        GridLayout                      matlab.ui.container.GridLayout
        ParametersLabel                 matlab.ui.control.Label
        OutputfolderButton              matlab.ui.control.Button
        LoaddataButton                  matlab.ui.control.Button
        Switch                          matlab.ui.control.ToggleSwitch
        MaxvethresholdEditField         matlab.ui.control.NumericEditField
        MaxvethresholdEditFieldLabel    matlab.ui.control.Label
        MaxvethresholdEditField_2       matlab.ui.control.NumericEditField
        MaxvethresholdEditField_2Label  matlab.ui.control.Label
        MinvethresholdEditField         matlab.ui.control.NumericEditField
        MinvethresholdEditFieldLabel    matlab.ui.control.Label
        SubsamplingEditField            matlab.ui.control.EditField
        SubsamplingEditFieldLabel       matlab.ui.control.Label
        WaveletsEditField               matlab.ui.control.EditField
        WaveletsEditFieldLabel          matlab.ui.control.Label
        CostparametersEditField         matlab.ui.control.EditField
        CostparametersEditFieldLabel    matlab.ui.control.Label
        GroundedEditField               matlab.ui.control.EditField
        GroundedEditFieldLabel          matlab.ui.control.Label
        WidthmsEditField                matlab.ui.control.EditField
        WidthmsEditFieldLabel           matlab.ui.control.Label
        NoscalesEditField               matlab.ui.control.NumericEditField
        NoscalesEditFieldLabel          matlab.ui.control.Label
        NospikesEditField               matlab.ui.control.NumericEditField
        NospikesEditFieldLabel          matlab.ui.control.Label
        MultiplierEditField             matlab.ui.control.EditField
        MultiplierEditFieldLabel        matlab.ui.control.Label
        SaveButton                      matlab.ui.control.Button
        DatafolderpathEditField         matlab.ui.control.EditField
        SavefolderpathEditField         matlab.ui.control.EditField
        ListoffilesTextAreaLabel        matlab.ui.control.Label
        ListoffilesTextArea             matlab.ui.control.TextArea
        AnalysedFilesTextAreaLabel      matlab.ui.control.Label
        AnalysedFilesTextArea           matlab.ui.control.TextArea
        DetectspikesButton              matlab.ui.control.Button
        SpiketimeunitDropDownLabel      matlab.ui.control.Label
        SpiketimeunitDropDown           matlab.ui.control.DropDown
    end
    
    
    properties (Access = private)
        dataPath;
        files_;
        savePath;
        params_;
        wbar;
        step = 0;
        filePath;
        filenames;
    end
    
    methods (Access = private)
        % Code that executes after component creation
        function startupFcn(app)
            'costam'
        end
        function r = list2mat(app, str, flag)
            str = strrep(str, ' ', '');
            str = split(str, ',');
            if flag
                for i = 1:numel(str)
                    r(i) = str2num(str{i});
                end
            else
                r = str;
            end
        end
        
        function getSpikes(app, dataPath, savePath, option, params)
            
            % Description:
            %	Master script for spike detection using CWT method. Runs spike
            %	detection through recordings, cost parameters, electrodes, and
            %	wavelets.
            
            % INPUT:
            %
            %   dataPath: path (ending with '/') to the folder containing data to be
            %             analyzed
            %
            %   savePath: path (ending with '/') to the folder where spike detection
            %             output will be saved
            %
            %   option: pass either path to files ('path') or list of files ('list');
            %
            %   params: [optional] argument to pass structure containing parameters;
            %           otherwise, run setParams() first to set parameters
            
            arguments
                app;
                dataPath;
                savePath;
                option;
                params;
            end
            
            %   Load parameters
            multiplier = params.multiplier;
            thresholds = params.thresholds;
            nSpikes = params.nSpikes;
            nScales = params.nScales;
            wid = params.wid;
            grd = params.grd;
            costList = params.costList;
            wnameList = params.wnameList;
            minPeakThrMultiplier = params.minPeakThrMultiplier;
            maxPeakThrMultiplier = params.maxPeakThrMultiplier;
            posPeakThrMultiplier = params.posPeakThrMultiplier;
            unit = params.unit;
            
            thrList = strcat( 'thr', thresholds);
            thrList = strrep(thrList, '.', 'p')';
            wnameList = horzcat(wnameList', thrList);
            
            % Get files
            % Modify the '*string*.mat' wildcard to include a subset of recordings
            
            if exist('option', 'var') && strcmp(option, 'list')
                files = dataPath;
                if ~iscell(files)
                    files = {files};
                end
            else
                files = dir([dataPath '*.mat']);
            end
            
            for recording = 1:numel(files)
                
                updateProgressbar(app, recording);
                
                if exist('option', 'var') && strcmp(option, 'list')
                    fileName = files{recording};
                else
                    fileName = [app.filePath files(recording).name];
                end
                
                diary('on');
                % Load data
                disp(['Loading ' fileName ' ...']);
                file = load(fileName);
                disp('File loaded');
                
                data = file.dat;
                channels = file.channels;
                fs = file.fs;
                ttx = contains(fileName, 'TTX');
                params.duration = length(data)/fs;
                
                % Truncate the data if specified
                if isfield(params, 'subsample_time')
                    if ~isempty(params.subsample_time)
                        if params.subsample_time(1) == 1
                            start_frame = 1;
                            
                        else
                            start_frame = params.subsample_time(1) * fs;
                            
                        end
                        end_frame = params.subsample_time(2) * fs;
                        
                    end
                    data = data(start_frame:end_frame, :);
                    params.duration = length(data)/fs;
                end
                
                for L = costList
                    L = log(L)/36.7368; % Convert from commission/omission ratio to actual cost parameter
                    
                    if startsWith(fileName, app.filePath)
                        saveName = [savePath strrep(fileName(1:end-4), app.filePath, '') '_L_' num2str(L) '_spikes.mat'];
                    else
                        saveName = [savePath fileName(1:end-4) '_L_' num2str(L) '_spikes.mat'];
                    end
                    
                    if ~exist(saveName, 'file')
                        params.L = L;
                        tic
                        disp('Detecting spikes...');
                        disp(['L = ' num2str(L)]);
                        
                        spikeTimes = cell(1,60);
                        spikeWaveforms = cell(1,60);
                        mad = zeros(1,60);
                        variance = zeros(1,60);
                        
                        % Run spike detection
                        for channel = 1:length(channels)
                            
                            spikeStruct = struct();
                            waveStruct = struct();
                            trace = data(:, channel);
                            
                            for wname = 1:numel(wnameList)
                                
                                wname = char(wnameList{wname});
                                valid_wname = strrep(wname, '.', 'p');
                                
                                spikeWaves = [];
                                spikeFrames = [];
                                
                                if ~(ismember(channel, grd))
                                    
                                    [spikeFrames, spikeWaves, trace] = ...
                                        detect_spikes_cwt(app, trace,fs,wid,wname,L,nScales, ...
                                        multiplier,nSpikes,ttx, minPeakThrMultiplier, ...
                                        maxPeakThrMultiplier, posPeakThrMultiplier);
                                    
                                    waveStruct.(valid_wname) = spikeWaves;
                                    
                                    if ~numel(spikeFrames)
                                        disp(['Electrode ' num2str(channel) ': no spikes detected']);
                                    end
                                    
                                    switch unit
                                        
                                        case 'ms'
                                            spikeStruct.(valid_wname) = spikeFrames/(fs/1000);
                                        case 's'
                                            spikeStruct.(valid_wname) = spikeFrames/fs;
                                        case 'frames'
                                            spikeStruct.(valid_wname) = spikeFrames;
                                    end
                                    
                                else
                                    waveStruct.(valid_wname) = [];
                                    spikeStruct.(valid_wname) = [];
                                end
                            end
                            
                            spikeTimes{channel} = spikeStruct;
                            spikeWaveforms{channel} = waveStruct;
                            mad(channel) = median(abs(trace - mean(trace))) / 0.6745;
                            variance(channel) = var(trace);
                            
                            median(abs(trace - mean(trace))) / 0.6745
                            var(trace)
                            
                            
                        end
                        
                        toc
                        
                        % Save results
                        save_suffix = ['_' strrep(num2str(L), '.', 'p')];
                        params.save_suffix = save_suffix;
                        params.fs = fs;
                        params.variance = variance;
                        params.mad = mad;
                        
                        spikeDetectionResult = struct();
                        spikeDetectionResult.method = 'CWT';
                        spikeDetectionResult.params = params;
                        
                        disp(['Saving results to: ' saveName]);
                        
                        varsList = {'spikeTimes', 'channels', 'spikeDetectionResult', ...
                            'spikeWaveforms'};
                        save(saveName, varsList{:}, '-v7.3');
                        disp(' ');
                    end
                end
                
                if recording+1 <= numel(files) && numel(files) > 1
                    txt_val = {app.filenames{recording+1:end}};
                else
                    txt_val = app.filenames;
                end
                
                app.ListoffilesTextArea.Value = txt_val;
                txt_val_new = app.AnalysedFilesTextArea.Value;
                txt_val_new{end+1} = app.filenames{recording};
                app.AnalysedFilesTextArea.Value = txt_val_new;
            end
            
            diary('off');
            diaryName = [strrep(date, '-','') '_spike_detection_log'];
            diary(diaryName);
            app.ListoffilesTextArea.Value = {''};
        end
        
        function [spikeTimes, spikeWaveforms, trace] = detect_spikes_cwt(...
                app, data, fs, Wid, wname, L, Ns, multiplier, nSpikes, ttx, ...
                minPeakThrMultiplier, maxPeakThrMultiplier, posPeakThrMultiplier)
            
            % Description:
            %
            %   Spike detection based on continuous wavelet transform with data-driven templates
            %
            %   Core function: detect_spikes_wavelet.m
            %   Adapted from Nenadic & Burdick (2005), doi:10.1109/TBME.2004.839800
            %   Modified by JJC
            %
            %   Custom wavelet specific functions: getTemplate.m, customWavelet.m
            %   Written by JJC (2020), https://github.com/jeremi-chabros/CWT
            
            % INPUT:
            %
            %   data: [1 x n] (raw) extracellular voltage trace to be analyzed
            %
            %   fs: sampling frequency [Hz]
            %
            %   Wid:  [1 x 2] vector of expected minimum and maximum width [ms] of
            %         transient to be detected Wid=[Wmin Wmax]
            %         For most practical purposes Wid=[0.5 1.0]
            %
            %   wname: (string): the name of wavelet family in use
            %       'bior1.5' - biorthogonal
            %       'bior1.3' - biorthogonal
            %       'db2'     - Daubechies
            %       'mea'     - custom data-driven wavelet (https://github.com/jeremi-chabros/CWT)
            %
            %       Note: sym2 and db2 differ only by sign --> they produce the same
            %       result
            %
            %	L: the factor that multiplies [cost of comission]/[cost of omission].
            %       For most practical purposes -0.2 <= L <= 0.2. Larger L --> omissions
            %       likely, smaller L --> false positives likely.
            %       For unsupervised detection, the suggested value of L is close to 0
            %
            %   Ns: [scalar] the number of scales to use in spike detection (Ns >= 2)
            %
            %   multiplier: [scalar] the threshold multiplier used for spike detection
            %
            %   nSpikes: [scalar] the number of spikes used to adapt a custom wavelet
            %
            %   ttx: [logical] flag for the recordings with TTX added: 1 = TTX, 0 = control
            %
            %   minPeakThrMultiplier: [scalar] specifies the minimal spike amplitude
            %
            %   maxPeakThrMultiplier: [scalar] specifies the maximal spike amplitude
            %
            %   posPeakThrMultiplier: [scalar] specifies the maximal positive peak of the spike
            
            
            % OUTPUT:
            %
            %   spikeTimes: [1 x #spikes] vector containing frames where spikes were detected
            %                 (divided by fs yields spike times in seconds)
            %
            %   spikeWaveforms: [51 x #spikes] matrix containing spike waveforms
            %                    (51 comes from sampling frequency and corresponds to
            %                     spike Frame +/-1 ms)
            %
            %   trace: [1 x n] filtered extracellular voltage trace
            
            % Author:
            %   Jeremy Chabros, University of Cambridge, 2020
            %   email: jjc80@cam.ac.uk
            %   github.com/jeremi-chabros
            
            
            refPeriod = 2; % Only used by the threshold method
            
            % Filter signal
            try
                lowpass = 600;
                highpass = 8000;
                wn = [lowpass highpass] / (fs / 2);
                filterOrder = 3;
                [b, a] = butter(filterOrder, wn);
                trace = filtfilt(b, a, double(data));
            catch
                error('Signal Processing Toolbox not found');
            end
            
            win = 25;   % [frames]
            
            if strcmp(wname, 'mea') && ~ttx
                
                %   Use threshold-based spike detection to obtain the median waveform
                %   from nSpikes
                try
                    [aveWaveform, ~] = get_template(app, trace, multiplier, refPeriod, fs, nSpikes);
                catch
                    warning('Failed to obtain mean waveform');
                end
                
                %   Adapt custom wavelet from the waveform obtained above
                try
                    adapt_wavelet(app, aveWaveform);
                catch
                    warning('Failed to adapt custom wavelet');
                end
            end
            
            try
                spikeWaveforms = [];
                spikeTimes = [];
                
                % Detect spikes with threshold method
                if startsWith(wname, 'thr')
                    multiplier = strrep(wname, 'p', '.');
                    multiplier = strrep(multiplier, 'thr', '');
                    multiplier = str2num(multiplier);
                    [spikeTrain, ~, ~] = detect_spikes_threshold(app, trace, multiplier, 2, fs, 0);
                    spikeTimes = find(spikeTrain == 1);
                else
                    
                    % Detect spikes with wavelet method
                    spikeTimes = detect_spikes_wavelet(app, trace, fs/1000, Wid, Ns, 'l', L, wname, 0, 0);
                end
                
                % Align spikes by negative peak & remove artifacts by amplitude
                [spikeTimes, spikeWaveforms] = align_peaks(app, spikeTimes, trace, win, 1,...
                    minPeakThrMultiplier,...
                    maxPeakThrMultiplier,...
                    posPeakThrMultiplier);
            catch
                spikeTimes = [];
            end
        end
        
        
        %%
        function [aveWaveform, spikeTimes] = get_template(app, trace, multiplier, refPeriod, fs, nSpikes)
            
            % Description:
            %   Obtain median waveform from spikes detected with threshold method
            
            % INPUT:
            %   trace: [n x 1] filtered voltage trace
            %   multiplier: [scalar] threshold multiplier used for spike detection
            %   refPeriod: [scalar] refractory period [ms] after a spike in which
            %                       no spikes will be detected
            %   fs: [scalar] sampling freqency in [Hz]
            %   nSpikes: [scalar] the number of spikes used to obtain average waveform
            
            % OUTPUT:
            %   aveWaveform: [51 x 1] average spike waveform
            %   spikeTimes: [#spikes x 1] vector containing detected spike times
            
            % Author:
            %   Jeremy Chabros, University of Cambridge, 2020
            %   email: jjc80@cam.ac.uk
            %   github.com/jeremi-chabros
            
            [spikeTrain, ~, ~] = detect_spikes_threshold(app, trace, multiplier, refPeriod, fs, 0);
            spikeTimes = find(spikeTrain == 1);
            
            %   If fewer spikes than specified - use the maximum number possible
            if  numel(spikeTimes) < nSpikes
                nSpikes = sum(spikeTrain);
            end
            
            %   Uniformly sample n_spikes
            spikes2use = round(linspace(2, length(spikeTimes)-2, nSpikes));
            
            spikeWaveforms = zeros(51, nSpikes);
            for i = 1:nSpikes
                n = spikeTimes(spikes2use(i));
                bin = trace(n-10:n+10);
                pos = find(bin == min(bin))-11; % 11 = middle sample in bin
                spikeWaveforms(:,i) = trace(n+pos-25:n+pos+25);
            end
            
            aveWaveform = median(spikeWaveforms,2);
        end
        
        function [spikeTrain, filtTrace, threshold] = ...
                detect_spikes_threshold(app, trace, multiplier, refPeriod, fs, filterFlag)
            
            % Description:
            %   Threshold-based spike detection
            
            % INPUT:
            %   trace: [n x 1] raw or filtered voltage trace
            %   multiplier: [scalar] threshold multiplier used for spike detection
            %   refPeriod: [scalar] refractory period [ms] after a spike in which
            %                       no spikes will be detected
            %   fs: [scalar] sampling frequency in [Hz]
            %   filterFlag: specifies whether to filter the trace (1); (0) otherwise
            
            % OUTPUT:
            %   spikeTrain - [n x 1] binary vector, where 1 represents a spike
            %   filtTrace - [n x 1] filtered voltage trace
            %   threshold - [scalar] threshold used in spike detection in [mV]
            
            % Author:
            %   Jeremy Chabros, University of Cambridge, 2020
            %   email: jjc80@cam.ac.uk
            %   github.com/jeremi-chabros
            
            %   Filtering
            if filterFlag
                lowpass = 600;
                highpass = 8000;
                wn = [lowpass highpass] / (fs / 2);
                filterOrder = 3;
                [b, a] = butter(filterOrder, wn);
                trace = filtfilt(b, a, double(trace));
            end
            
            % Calculate the threshold (median absolute deviation)
            % See: https://en.wikipedia.org/wiki/Median_absolute_deviation
            s = (mad(trace, 1)/0.6745);     % Faster than mad(X,1);
            m = mean(trace);                % Note: filtered trace is already zero-mean
            threshold = m - multiplier*s;
            
            % Detect spikes (defined as threshold crossings)
            spikeTrain = zeros(size(trace));
            spikeTrain = trace < threshold;
            spikeTrain = double(spikeTrain);
            
            % Impose the refractory period [ms]
            refPeriod = refPeriod * 10^-3 * fs;
            for i = 1:length(spikeTrain)
                if spikeTrain(i) == 1
                    refStart = i + 1;
                    refEnd = round(i + refPeriod);
                    if refEnd > length(spikeTrain)
                        spikeTrain(refStart:length(spikeTrain)) = 0;
                    else
                        spikeTrain(refStart:refEnd) = 0;
                    end
                end
            end
            filtTrace = trace;
        end
        
        function [spikeTimes, spikeWaveforms] = align_peaks(app, spikeTimes, trace, win,...
                artifactFlg, varargin)
            
            % Description:
            %   Aligns spikes by negative peaks and removes artifacts by amplitude
            
            % INPUT:
            %   spikeTimes: vector containing spike times
            %   trace: [n x 1] filtered voltage trace
            %   win: [scalar] window around the spike; length of the waveform in [frames];
            %   artifactFlg: [logical] flag for artifact removal; 1 to remove artifacts, 0 otherwise
            %
            % Optional arguments (only used in post-hoc artifact removal)
            %   varargin{1} = minPeakThrMultiplier;
            %   varargin{2} = maxPeakThrMultiplier;
            %   varargin{3} = posPeakThrMultiplier;
            
            % OUTPUT:
            %   spikeTimes: [#spikes x 1] new spike times aligned to the negative amplitude peak
            %   spikeWaveforms: [51 x #spikes] waveforms of the detected spikes
            
            % Author:
            %   Jeremy Chabros, University of Cambridge, 2020
            %   email: jjc80@cam.ac.uk
            %   github.com/jeremi-chabros
            
            % Obtain thresholds for artifact removal
            threshold = median(abs(trace - mean(trace))) / 0.6745;
            
            if exist('varargin', 'var')
                minPeakThr = -threshold * varargin{1};
                % maxPeakThr = -threshold * varargin{2};
                posPeakThr = threshold * varargin{3};
            end
            
            sFr = zeros(1, length(spikeTimes));
            spikeWaveforms = zeros(51, length(spikeTimes));
            
            
            for i = 1:length(spikeTimes)
                
                if spikeTimes(i)+win < length(trace) && spikeTimes(i)-win > 1
                    
                    % Look into a window around the spike
                    bin = trace(spikeTimes(i)-win:spikeTimes(i)+win);
                    
                    negativePeak = min(bin);
                    positivePeak = max(bin);
                    pos = find(bin == negativePeak);
                    
                    % Remove artifacts and assign new timestamps
                    
                    if artifactFlg
                        if negativePeak < minPeakThr && positivePeak < posPeakThr
                            
                            newSpikeTime = spikeTimes(i)+pos-win;
                            waveform = trace(newSpikeTime-25:newSpikeTime+25);
                            
                            sFr(i) = newSpikeTime;
                            spikeWaveforms(:, i) = waveform;
                            
                        end
                    else
                        newSpikeTime = spikeTimes(i)+pos-win;
                        waveform = trace(newSpikeTime-25:newSpikeTime+25);
                        
                        sFr(i) = newSpikeTime;
                        spikeWaveforms(:, i) = waveform;
                        
                    end
                end
            end
            
            spikeTimes = sFr(sFr~=0);
            spikeWaveforms = spikeWaveforms(:, sFr~=0);
            
        end
        %%
        
        
        
        function [newWaveletIntegral, newWaveletSqN] = adapt_wavelet(app, aveWaveform)
            
            % Description:
            %   Uses spike waveform to adapt custom wavelet that can be used for
            %   continuous wavelet transform
            
            % INPUT:
            %   aveWaveform: average (mean or median) spike waveform
            
            % OUTPUT:
            %   newWaveletIntegral: area under the newly adapted wavelet
            %   newWaveletSqN: square normm of the newly adapted wavelet
            
            % Author:
            %   Jeremy Chabros, University of Cambridge, 2020
            %   email: jjc80@cam.ac.uk
            %   github.com/jeremi-chabros/CWT
            
            template = aveWaveform;
            
            % Interpolation
            template = spline(1:length(template), template, linspace(1, length(template), 100));
            
            % Gaussian smoothing
            w = gausswin(10);
            y = filter(w,1,template);
            y = rescale(y);
            y = y - mean(y);
            
            % Pre-allocate
            signal = zeros(1, 110);
            
            % Center the template
            signal(6:105) = y;
            
            % Adapt the wavelet
            [Y,X,~] = pat2cwav(signal, 'orthconst', 0, 'none') ;
            
            % Test if a legitmate wavelet
            dxval = max(diff(X));
            newWaveletIntegral = dxval*sum(Y); %    Should be 1.0
            newWaveletSqN = dxval*sum(Y.^2);
            newWaveletSqN = round(newWaveletSqN,10); % Should be zero
            
            % Save the wavelet
            if newWaveletSqN == 1.0000
                
                % Using built-in cwt method requires saving the custom wavelet each
                % time - currently overwriting as there is no reason to retrieve the
                % wavelet
                save('mother.mat', 'X', 'Y');
                wavemngr('del', 'mea');
                
                % Note: all wavelets cunstructed with wavemngr are type 4 wavelets
                % without a scaling function
                wavemngr('add', 'meaCustom','mea', 4, '', 'mother.mat', [-100 100]);
            else
                disp('ERROR: Not a proper wavelet');
                disp(['Integral = ', num2str(newWaveletIntegral)]);
                disp(['L^2 norm = ', num2str(newWaveletSqN)]);
            end
        end
        
        %%
        
        function spikeFrames = detect_spikes_wavelet(...
                app, Signal, SFr, Wid, Ns, option, L, wname, PltFlg, CmtFlg)
            
            % DETECT_SPIKES_WAVELET wavelet based algorithm for detection of transients
            % from neural data.
            %
            %   TE=DETECT_SPIKES_WAVELET(Signal,SFr,Wid,Ns,option,L,wname,PltFlg,CmtFlg)
            %
            %   Signal - extracellular potential data to be analyzed 1 x Nt;
            %
            %   SFr - sampling frequency [kHz];
            %
            %   Wid - 1 x 2 vector of expected minimum and maximum width [msec] of transient
            %   to be detected Wid=[Wmin Wmax]. For most practical purposes Wid=[0.5 1.0];
            %
            %   Ns - (scalar): the number of scales to use in detection (Ns >= 2);
            %
            %   option - (string): the action taken when no coefficients survive hard
            %   thresholding
            %   'c' means conservative and returns no spikes if P(S) is found to be 0
            %   'l' means assume P(S) as a vague prior (see the original reference)
            %
            %   L is the factor that multiplies [cost of comission]/[cost of omission].
            %   For most practical purposes -0.2 <= L <= 0.2. Larger L --> omissions
            %   likely, smaller L --> false positives likely. For unsupervised
            %   detection, the suggested value of L is close to 0.
            %
            %   wname - (string): the name of wavelet family in use
            %           'bior1.5' - biorthogonal
            %           'bior1.3' - biorthogonal
            %           'db2'     - Daubechies
            %           'sym2'    - symmlet
            %           'haar'    - Haar function
            %   Note: sym2 and db2 differ only by sign --> they produce the same
            %   result;
            %
            %   PltFlg - (integer) is the plot flag:
            %   PltFlg = 1 --> generate figures, otherwise do not;
            %
            %   CmtFlg - (integer) is the comment flag,
            %   CmtFlg = 1 --> display comments, otherwise do not;
            %
            %   TE is the vector of event occurrence times;
            %
            %   Reference: Z. Nenadic and J.W. Burdick, Spike detection using the
            %   continuous wavelet transform, IEEE T. Bio-med. Eng., vol. 52,
            %   pp. 74-87, 2005.
            
            %   Originally developed by:
            %   Zoran Nenadic
            %   California Institute of Technology
            %   May 2003
            %
            %   Modified by:
            %   Zoran Nenadic
            %   University of California, Irvine
            %   February 2008
            %
            %   Modified by:
            %   Jeremi Chabros
            %   University of Cambridge
            %   November 2020
            
            
            %admissible wavelet families (more wavelets could be added)
            wfam = {'bior1.5','bior1.3','sym2','db2','haar','mea'};
            
            if sum(strcmp(wname,wfam)) == 0
                error('unknown wavelet family')
            elseif CmtFlg == 1
                disp(['wavelet family: ' wname])
                to = clock;
            end
            
            %make sure signal is zero-mean
            Signal = Signal - mean(Signal);
            
            Nt = length(Signal);      %# of time samples
            
            %define relevant scales for detection
            W = determine_scales(app, wname,Wid,SFr,Ns);
            
            %initialize the matrix of thresholded coefficients
            ct = zeros(Ns,Nt);
            
            try
                %get all coefficients
                c = cwt(Signal,W,wname);
            catch
                error('Wavelet Toolbox not found');
            end
            
            %define detection parameter
            Lmax = 36.7368;       % log(Lcom/Lom), where the ratio is the maximum
            % allowed by the current machine precision
            L = L * Lmax;
            
            %initialize the vector of spike indicators, 0-no spike, 1-spike
            Io = zeros(1,Nt);
            
            %loop over scales
            for i = 1:Ns
                
                %take only coefficients that are independent (W(i) apart) for median
                %standard deviation
                
                Sigmaj = median(abs(c(i,1:round(W(i)):end) - mean(c(i,:))))/0.6745;
                Thj = Sigmaj * sqrt(2 * log(Nt));     %hard threshold
                index = find(abs(c(i,:)) > Thj);
                if isempty(index) && strcmp(num2str(option),'c')
                    %do nothing ct=[0];
                elseif isempty(index) && strcmp(num2str(option),'l')
                    Mj = Thj;
                    %assume at least one spike
                    PS = 1/Nt;
                    PN = 1 - PS;
                    DTh = Mj/2 + Sigmaj^2/Mj * [L + log(PN/PS)];    %decision threshold
                    DTh = abs(DTh) * (DTh >= 0);                 %make DTh>=0
                    ind = find(abs(c(i,:)) > DTh);
                    if isempty(ind)
                        %do nothing ct=[0];
                    else
                        ct(i,ind) = c(i,ind);
                    end
                else
                    Mj = mean(abs(c(i,index)));       %mean of the signal coefficients
                    PS = length(index)/Nt;            %prior of spikes
                    PN = 1 - PS;                        %prior of noise
                    DTh = Mj/2 + Sigmaj^2/Mj * [L + log(PN/PS)];   %decision threshold
                    DTh = abs(DTh) * (DTh >= 0);         %make DTh>=0
                    ind = find(abs(c(i,:)) > DTh);
                    ct(i,ind) = c(i,ind);
                end
                
                %find which coefficients are non-zero
                Index = ct(i,:) ~= 0;
                
                %make a union with coefficients from previous scales
                Index = or(Io,Index);
                Io = Index;
            end
            
            spikeFrames = parse(app, Index,SFr,Wid);
            
            if PltFlg == 1
                close all
                figure(1)
                scale = 64./[max(abs(c),[],2) * ones(1,Nt)];
                temp = zeros(1,Nt);
                temp(spikeFrames) = 1;
                image(flipud(abs(c)) .* scale)
                colormap pink
                ylabel('Scales')
                Wt = [fliplr(W)];
                set(gca,'YTick',1:Ns,'YTickLabel',Wt,'Position',[0.1 0.2 0.8 0.6], ...
                    'XTick',[])
                title(['|C| across scales: ' num2str(W)])
                ah2 = axes;
                set(ah2,'Position',[0.1 0.1 0.8 0.1])
                plot(temp,'o-m','MarkerSize',4,'MarkerFaceColor','m')
                set(gca,'YTick',[],'XLim',[1 Nt])
                xlabel('Time (samples)')
                ylabel('Spikes')
                
                figure(2)
                plot(Signal,'Color',[0.7 0.7 0.7],'LineWidth',2)
                hold on
                plot(ct','-o','LineWidth',1,'MarkerFaceColor','k', ...
                    'MarkerSize',4)
                xlabel('Time (samples)')
                ylabel('Coefficients')
                set(gca,'XLim',[1 Nt])
            end
            
            if CmtFlg == 1
                disp([num2str(length(spikeFrames)) ' spikes found'])
                disp(['elapsed time: ' num2str(etime(clock,to))])
            end
        end
        
        
        function Scale = determine_scales(app, wname,Wid,SFr,Ns)
            
            %Ns - # of scales
            
            dt = 1/SFr;  %[msec]
            
            %signal sampled @ 1 KHz
            Signal = zeros(1,1000);
            %create Dirac function
            Signal(500) = 1;
            
            Width = linspace(Wid(1),Wid(2),Ns);
            
            %infinitesimally small number
            Eps = 10^(-15);
            
            ScaleMax = 4;
            ScaleMax = ScaleMax*SFr;
            
            switch num2str(wname)
                
                case 'haar'
                    for i = 1:Ns
                        Scale(i) = Width(i)/dt - 1;
                    end
                case 'db2'
                    Scales = 2:ScaleMax;
                    c = cwt(Signal,Scales,wname);
                    for i = 1:length(Scales)
                        %indicators of positive coefficients
                        IndPos = (c(i,:) > 0);
                        %indicators of derivative
                        IndDer = diff(IndPos);
                        %indices of negative slope zero crossings
                        IndZeroCross = find(IndDer == -1);
                        IndMax = IndZeroCross > 500;
                        Ind(2) = min(IndZeroCross(IndMax))+1;
                        IndMin = IndZeroCross < 500;
                        Ind(1) = max(IndZeroCross(IndMin));
                        WidthTable(i) = diff(Ind) * dt;
                    end
                    WidthTable = WidthTable + [1:length(Scales)] * Eps;
                    %look-up table
                    Scale = round(interp1(WidthTable,Scales,Width,'linear'));
                case 'sym2'
                    Scales = 2:ScaleMax;
                    c = cwt(Signal,Scales,wname);
                    for i = 1:length(Scales)
                        %indicators of positive coefficients
                        IndPos = (c(i,:) > 0);
                        %indicators of derivative
                        IndDer = diff(IndPos);
                        %indices of positive slope zero crossings
                        IndZeroCross = find(IndDer == 1);
                        IndMax = IndZeroCross > 500;
                        Ind(2) = min(IndZeroCross(IndMax))+1;
                        IndMin = IndZeroCross < 500;
                        Ind(1) = max(IndZeroCross(IndMin));
                        WidthTable(i) = diff(Ind) * dt;
                    end
                    WidthTable = WidthTable + [1:length(Scales)] * Eps;
                    %look-up table
                    Scale = round(interp1(WidthTable,Scales,Width,'linear'));
                case 'bior1.3'
                    Scales = 2:ScaleMax;
                    c = cwt(Signal,Scales,wname);
                    for i = 1:length(Scales)
                        %indicators of positive coefficients
                        IndPos = (c(i,:) > 0);
                        %indicators of derivative
                        IndDer = diff(IndPos);
                        %indices of negative slope zero crossings
                        IndZeroCross = find(IndDer == -1);
                        IndMax = IndZeroCross > 500;
                        Ind(2) = min(IndZeroCross(IndMax))+1;
                        IndMin = IndZeroCross < 500;
                        Ind(1) = max(IndZeroCross(IndMin));
                        WidthTable(i) = diff(Ind) * dt;
                    end
                    WidthTable = WidthTable + [1:length(Scales)] * Eps;
                    %look-up table
                    Scale = round(interp1(WidthTable,Scales,Width,'linear'));
                case 'bior1.5'
                    Scales = 2:ScaleMax;
                    c = cwt(Signal,Scales,wname);
                    for i = 1:length(Scales)
                        %indicators of positive coefficients
                        IndPos = (c(i,:) > 0);
                        %indicators of derivative
                        IndDer = diff(IndPos);
                        %indices of negative slope zero crossings
                        IndZeroCross = find(IndDer == -1);
                        IndMax = IndZeroCross > 500;
                        Ind(2) = min(IndZeroCross(IndMax))+1;
                        IndMin = IndZeroCross < 500;
                        Ind(1) = max(IndZeroCross(IndMin));
                        WidthTable(i) = diff(Ind) * dt;
                    end
                    WidthTable = WidthTable + [1:length(Scales)] * Eps;
                    %look-up table
                    Scale = round(interp1(WidthTable,Scales,Width,'linear'));
                    
                    
                    
                    % Custom data-driven wavelets added by JJC, November 2020
                    % See: https://github.com/jeremi-chabros/CWT
                    
                case 'mea'
                    Scales = 2:ScaleMax;
                    c = cwt(Signal,Scales,wname);
                    for i = 3:length(Scales)
                        %indicators of positive coefficients
                        IndPos = (c(i,:) > 0);
                        %indicators of derivative
                        IndDer = diff(IndPos);
                        %indices of negative slope zero crossings
                        IndZeroCross = find(IndDer == -1);
                        IndMax = IndZeroCross > 500;
                        Ind(2) = min(IndZeroCross(IndMax))+1;
                        IndMin = IndZeroCross < 500;
                        Ind(1) = max(IndZeroCross(IndMin));
                        WidthTable(i) = diff(Ind) * dt;
                    end
                    WidthTable = WidthTable + [1:length(Scales)] * Eps;
                    %look-up table
                    Scale = round(interp1(WidthTable,Scales,Width,'linear'));
                    
                otherwise
                    error('unknown wavelet family')
            end
            
            NaNInd = isnan(Scale);
            
            if sum(NaNInd) > 0
                warning(['Your choice of Wid is not valid given' ...
                    ' the sampling rate and wavelet family'])
                if NaNInd(1) == 1
                    disp(['Most likely Wid(1) is too small'])
                elseif NaNInd(Ns) == 1
                    disp(['Most likely Wid(2) is too large'])
                    disp(['Change the value on line: ''ScaleMax = 2'' to something larger'])
                end
            end
        end
        
        %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
        
        function fcn = parse(app, Index,SFr,Wid)
            
            %This is a special function, it takes the vector Index which has
            %the structure [0 0 0 1 1 1 0 ... 0 1 0 ... 0]. This vector was obtained
            %by coincidence detection of certain events (lower and upper threshold
            %crossing for threshold detection, and the appearance of coefficients at
            %different scales for wavelet detection).
            %The real challenge here is to merge multiple 1's that belong to the same
            %spike into one event and to locate that event
            
            Refract = 1.5 * Wid(2);    %[ms] the refractory period -- can't resolve spikes
            %that are closer than Refract;
            Refract = round(Refract * SFr);
            
            Merge = mean(Wid);      %[ms] merge spikes that are closer than Merge, since
            %it is likely they belong to the same spike
            
            Merge = round(Merge * SFr);
            
            
            Index([1 end]) = 0;   %discard spikes located at the first and last samples
            
            ind_ones = find(Index == 1);    %find where the ones are
            
            if isempty(ind_ones)
                TE = [];
            else
                temp = diff(Index);  %there will be 1 followed by -1 for each spike
                N_sp = sum(temp == 1); %nominal number of spikes
                
                lead_t = find(temp == 1);  %index of the beginning of a spike
                lag_t = find(temp == -1);  %index of the end of the spike
                
                for i = 1:N_sp
                    tE(i) = ceil(mean([lead_t(i) lag_t(i)]));
                end
                
                i = 1;        %initialize counter
                while 0 < 1
                    if i > (length(tE) - 1)
                        break;
                    else
                        Diff = tE(i+1) - tE(i);
                        if Diff < Refract & Diff > Merge
                            tE(i+1) = [];      %discard spike too close to its predecessor
                        elseif Diff <= Merge
                            tE(i) = ceil(mean([tE(i) tE(i+1)]));  %merge
                            tE(i+1) = [];                         %discard
                        else
                            i = i+1;
                        end
                    end
                end
                TE = tE;
            end
            
            fcn = TE;
        end
        
        function updateProgressbar(app, prog)
            wbarColor = [1,0.3089, 0.3089];
            
            app.DetectspikesButton.Text = {['Detecting spikes...'], ['File: ' num2str(prog) filesep num2str(numel(app.files_))]};
            app.wbar = permute(repmat(app.DetectspikesButton.BackgroundColor,30,1,700),[1,3,2]);
            app.wbar([1,end],:,:) = 0;
            app.wbar(:,[1,end],:) = 0;
            app.DetectspikesButton.Icon = app.wbar;
            currentProg = min(round((size(app.wbar,2)-2)*(prog/numel(app.files_))),size(app.wbar,2)-2);
            
            app.DetectspikesButton.Icon(2:end-1, 2:currentProg+1, 1) = wbarColor(1);
            app.DetectspikesButton.Icon(2:end-1, 2:currentProg+1, 2) = wbarColor(2);
            app.DetectspikesButton.Icon(2:end-1, 2:currentProg+1, 3) = wbarColor(3);
            pause(.3)
        end
        
    end
    
    
    % Callbacks that handle component events
    methods (Access = private)
        
        % Button pushed function: SaveButton
        function SaveButtonPushed(app, event)
            
            params = struct();
            
            multipliers = app.MultiplierEditField.Value;
            params.thresholds = list2mat(app, multipliers, 0);
            params.multiplier = str2num(multipliers(1));
            
            params.nSpikes = app.NospikesEditField.Value;
            params.nScales = app.NoscalesEditField.Value;
            
            wid = app.WidthmsEditField.Value;
            params.wid = list2mat(app, wid, 1);
            
            params.grd = [];
            if app.GroundedEditField.Value
                grd = app.GroundedEditField.Value;
                params.grd = list2mat(app, grd, 1);
            end
            
            costList = app.CostparametersEditField.Value;
            params.costList = list2mat(app, costList, 1);
            
            wnameList = app.WaveletsEditField.Value;
            params.wnameList = list2mat(app, wnameList, 0);
            
            if app.SubsamplingEditField.Value
                subsample_time = app.SubsamplingEditField.Value;
                params.subsample_time = list2mat(app, subsample_time, 1);
            end
            
            params.minPeakThrMultiplier = app.MinvethresholdEditField.Value;
            params.maxPeakThrMultiplier = app.MaxvethresholdEditField.Value;
            params.posPeakThrMultiplier = app.MaxvethresholdEditField_2.Value;
            
            unit = strrep(app.SpiketimeunitDropDown.Value, '[', '');
            unit = strrep(unit, ']', '');
            params.unit = unit;
            
            app.params_ = params;
            
            app.step = app.step + 1;
            save('params.mat', 'params');
        end
        
        % Button pushed function: LoaddataButton
        function LoaddataButtonPushed(app, event)
            
            if strcmp(app.Switch.Value, 'Folders')
                app.UIFigure.Visible = 'off';
                app.dataPath = [uigetdir() filesep];
                figure(app.UIFigure)
                app.DatafolderpathEditField.Value = app.dataPath;
                app.files_ = dir([app.dataPath '*.mat']);
                app.filenames = {app.files_.name};
                app.filePath = app.dataPath;
                
            else
                app.UIFigure.Visible = 'off';
                [app.files_, app.filePath] = uigetfile('*.mat', 'MultiSelect','on');
                figure(app.UIFigure)
                app.filenames = app.files_;
                app.DatafolderpathEditField.Value = app.filePath;
                app.files_ = strcat(app.filePath, app.files_);
                
                if ~iscell(app.filenames)
                    app.filenames = {app.filenames};
                    app.files_ = {app.files_};
                end
            end
            app.ListoffilesTextArea.Value = app.filenames';
            app.step = app.step + 1;
        end
        
        % Value changed function: Switch
        function SwitchValueChanged(app, event)
            value = app.Switch.Value;
        end
        
        % Button pushed function: OutputfolderButton
        function OutputfolderButtonPushed(app, event)
            app.UIFigure.Visible = 'off';
            app.savePath = [uigetdir() filesep];
            figure(app.UIFigure)
            app.SavefolderpathEditField.Value = app.savePath;
        end
        
        % Button pushed function: DetectspikesButton
        function DetectspikesButtonPushed(app, event)
            
            if app.step >= 2
                app.DetectspikesButton.Text = {['Detecting spikes...'], [' ']};
                app.DetectspikesButton.IconAlignment = 'bottom';
                app.wbar = permute(repmat(app.DetectspikesButton.BackgroundColor,30,1,700),[1,3,2]);
                app.wbar([1,end],:,:) = 0;
                app.wbar(:,[1,end],:) = 0;
                app.DetectspikesButton.Icon = app.wbar;
                updateProgressbar(app, 0);
                
                app.ListoffilesTextArea.FontColor = [0.6353 0.0784 0.1843];
                app.ListoffilesTextArea.FontWeight = 'bold';
                
                
                if strcmp(app.Switch.Value, 'Folders')
                    option = "path";
                    
                    getSpikes(app, app.dataPath, app.savePath, option, app.params_);
                    
                else
                    option = "list";
                    getSpikes(app, app.files_, app.savePath, option, app.params_);
                end
                
                app.DetectspikesButton.Icon = '';
                app.DetectspikesButton.Text = 'Detection complete';
            end
        end
        
        % Value changed function: DatafolderpathEditField
        function DatafolderpathEditFieldValueChanged(app, event)
            app.dataPath = app.DatafolderpathEditField.Value;
        end
        
        % Value changed function: SavefolderpathEditField
        function SavefolderpathEditFieldValueChanged(app, event)
            app.savePath = app.SavefolderpathEditField.Value;
        end
        
        % Value changed function: SpiketimeunitDropDown
        function SpiketimeunitDropDownValueChanged(app, event)
            value = app.SpiketimeunitDropDown.Value;
            
        end
    end
    
    % Component initialization
    methods (Access = private)
        
        % Create UIFigure and components
        function createComponents(app)
            
            % Create UIFigure and hide until all components are created
            app.UIFigure = uifigure('Visible', 'off');
            app.UIFigure.Position = [300 300 812 438];
            app.UIFigure.Name = 'MATLAB App';
            
            % Create GridLayout
            app.GridLayout = uigridlayout(app.UIFigure);
            app.GridLayout.ColumnWidth = {70, 85, 334, 20, 100, 100, 20};
            app.GridLayout.RowHeight = {20, 20, 20, 20, 20, 20, 20, 20, 20, 20, 20, 20, 20, 20};
            app.GridLayout.ColumnSpacing = 11.8571428571429;
            app.GridLayout.Padding = [11.8571428571429 10 11.8571428571429 10];
            
            % Create ParametersLabel
            app.ParametersLabel = uilabel(app.GridLayout);
            app.ParametersLabel.HorizontalAlignment = 'center';
            app.ParametersLabel.FontSize = 14;
            app.ParametersLabel.FontWeight = 'bold';
            app.ParametersLabel.Layout.Row = 1;
            app.ParametersLabel.Layout.Column = 6;
            app.ParametersLabel.Text = 'Parameters';
            app.ParametersLabel.Tooltip = 'Set spike detection parameters and click "save"';
            
            % Create OutputfolderButton
            app.OutputfolderButton = uibutton(app.GridLayout, 'push');
            app.OutputfolderButton.ButtonPushedFcn = createCallbackFcn(app, @OutputfolderButtonPushed, true);
            app.OutputfolderButton.Layout.Row = 3;
            app.OutputfolderButton.Layout.Column = 2;
            app.OutputfolderButton.Text = 'Output folder';
            app.OutputfolderButton.Tooltip = 'Set path to the folder where spike detection output will be saved';
            
            % Create LoaddataButton
            app.LoaddataButton = uibutton(app.GridLayout, 'push');
            app.LoaddataButton.ButtonPushedFcn = createCallbackFcn(app, @LoaddataButtonPushed, true);
            app.LoaddataButton.Layout.Row = 2;
            app.LoaddataButton.Layout.Column = 2;
            app.LoaddataButton.Text = 'Load data';
            app.LoaddataButton.Tooltip = 'Select files or set path to the folder with data';
            
            
            % Create Switch
            app.Switch = uiswitch(app.GridLayout, 'toggle');
            app.Switch.Items = {'Folders', 'Files'};
            app.Switch.ValueChangedFcn = createCallbackFcn(app, @SwitchValueChanged, true);
            app.Switch.Layout.Row = [2 4];
            app.Switch.Layout.Column = 1;
            app.Switch.Value = 'Folders';
            app.Switch.Tooltip = '"Folders" enables you to choose a folder with data, "Files" allows choosing single or multiple files';
            
            % Create MaxvethresholdEditField
            app.MaxvethresholdEditField = uieditfield(app.GridLayout, 'numeric');
            app.MaxvethresholdEditField.Layout.Row = 12;
            app.MaxvethresholdEditField.Layout.Column = 6;
            app.MaxvethresholdEditField.Value = 5;
            app.MaxvethresholdEditField.Tooltip = 'Threshold multiplier that specifies the maximum positive peak amplitude of a spike';
            
            % Create MaxvethresholdEditFieldLabel
            app.MaxvethresholdEditFieldLabel = uilabel(app.GridLayout);
            app.MaxvethresholdEditFieldLabel.HorizontalAlignment = 'right';
            app.MaxvethresholdEditFieldLabel.Layout.Row = 12;
            app.MaxvethresholdEditFieldLabel.Layout.Column = 5;
            app.MaxvethresholdEditFieldLabel.Text = 'Max +ve threshold';
            app.MaxvethresholdEditFieldLabel.Tooltip = app.MaxvethresholdEditField.Tooltip;
            
            % Create MaxvethresholdEditField_2
            app.MaxvethresholdEditField_2 = uieditfield(app.GridLayout, 'numeric');
            app.MaxvethresholdEditField_2.Layout.Row = 11;
            app.MaxvethresholdEditField_2.Layout.Column = 6;
            app.MaxvethresholdEditField_2.Value = 10;
            app.MaxvethresholdEditField_2.Tooltip = 'Threshold multiplier that specifies the maximum negative peak amplitude of a spike';
            
            % Create MaxvethresholdEditField_2Label
            app.MaxvethresholdEditField_2Label = uilabel(app.GridLayout);
            app.MaxvethresholdEditField_2Label.HorizontalAlignment = 'right';
            app.MaxvethresholdEditField_2Label.Layout.Row = 11;
            app.MaxvethresholdEditField_2Label.Layout.Column = 5;
            app.MaxvethresholdEditField_2Label.Text = 'Max -ve threshold';
            app.MaxvethresholdEditField_2Label.Tooltip = app.MaxvethresholdEditField_2.Tooltip;
            
            % Create MinvethresholdEditField
            app.MinvethresholdEditField = uieditfield(app.GridLayout, 'numeric');
            app.MinvethresholdEditField.Layout.Row = 10;
            app.MinvethresholdEditField.Layout.Column = 6;
            app.MinvethresholdEditField.Value = 2;
            app.MinvethresholdEditField.Tooltip = 'Threshold multiplier that specifies the minimum negative peak amplitude of a spike';
            
            % Create MinvethresholdEditFieldLabel
            app.MinvethresholdEditFieldLabel = uilabel(app.GridLayout);
            app.MinvethresholdEditFieldLabel.HorizontalAlignment = 'right';
            app.MinvethresholdEditFieldLabel.Layout.Row = 10;
            app.MinvethresholdEditFieldLabel.Layout.Column = 5;
            app.MinvethresholdEditFieldLabel.Text = 'Min -ve threshold';
            app.MinvethresholdEditFieldLabel.Tooltip = app.MinvethresholdEditField.Tooltip;
            
            % Create SubsamplingEditField
            app.SubsamplingEditField = uieditfield(app.GridLayout, 'text');
            app.SubsamplingEditField.HorizontalAlignment = 'right';
            app.SubsamplingEditField.Layout.Row = 9;
            app.SubsamplingEditField.Layout.Column = 6;
            app.SubsamplingEditField.Tooltip = '(optional) Vector of start and end times in the recording to be analysed in [s], e.g. ‘30, 60’ will analyze 30 s of the recording between 30th and 60th second';
            
            
            % Create SubsamplingEditFieldLabel
            app.SubsamplingEditFieldLabel = uilabel(app.GridLayout);
            app.SubsamplingEditFieldLabel.HorizontalAlignment = 'right';
            app.SubsamplingEditFieldLabel.Layout.Row = 9;
            app.SubsamplingEditFieldLabel.Layout.Column = 5;
            app.SubsamplingEditFieldLabel.Text = 'Subsampling';
            app.SubsamplingEditFieldLabel.Tooltip = app.SubsamplingEditField.Tooltip;
            
            
            % Create WaveletsEditField
            app.WaveletsEditField = uieditfield(app.GridLayout, 'text');
            app.WaveletsEditField.HorizontalAlignment = 'right';
            app.WaveletsEditField.Layout.Row = 8;
            app.WaveletsEditField.Layout.Column = 6;
            app.WaveletsEditField.Value = 'mea';
            app.WaveletsEditField.Tooltip = 'List of wavelets to be used in spike detection. Available: mea, bior1.5, bior1.3, db2';
            
            
            % Create WaveletsEditFieldLabel
            app.WaveletsEditFieldLabel = uilabel(app.GridLayout);
            app.WaveletsEditFieldLabel.HorizontalAlignment = 'right';
            app.WaveletsEditFieldLabel.Layout.Row = 8;
            app.WaveletsEditFieldLabel.Layout.Column = 5;
            app.WaveletsEditFieldLabel.Text = 'Wavelets';
            app.WaveletsEditFieldLabel.Tooltip = app.WaveletsEditField.Tooltip;
            
            % Create CostparametersEditField
            app.CostparametersEditField = uieditfield(app.GridLayout, 'text');
            app.CostparametersEditField.HorizontalAlignment = 'right';
            app.CostparametersEditField.Layout.Row = 7;
            app.CostparametersEditField.Layout.Column = 6;
            app.CostparametersEditField.Value = '0';
            app.CostparametersEditField.Tooltip = 'List of cost parameters (separated by comma). Cost parameter = Cost(comcission)/Cost(omission)';
            
            
            % Create CostparametersEditFieldLabel
            app.CostparametersEditFieldLabel = uilabel(app.GridLayout);
            app.CostparametersEditFieldLabel.HorizontalAlignment = 'right';
            app.CostparametersEditFieldLabel.Layout.Row = 7;
            app.CostparametersEditFieldLabel.Layout.Column = 5;
            app.CostparametersEditFieldLabel.Text = 'Cost parameters';
            app.CostparametersEditFieldLabel.Tooltip = app.CostparametersEditField.Tooltip;
            
            % Create GroundedEditField
            app.GroundedEditField = uieditfield(app.GridLayout, 'text');
            app.GroundedEditField.HorizontalAlignment = 'right';
            app.GroundedEditField.Layout.Row = 6;
            app.GroundedEditField.Layout.Column = 6;
            app.GroundedEditField.Tooltip = 'Vector of grounded electrode XY coordinates separated by commas; e.g. 15, 23, 32';
            
            % Create GroundedEditFieldLabel
            app.GroundedEditFieldLabel = uilabel(app.GridLayout);
            app.GroundedEditFieldLabel.HorizontalAlignment = 'right';
            app.GroundedEditFieldLabel.Layout.Row = 6;
            app.GroundedEditFieldLabel.Layout.Column = 5;
            app.GroundedEditFieldLabel.Text = 'Grounded';
            app.GroundedEditFieldLabel.Tooltip = app.GroundedEditField.Tooltip;
            
            % Create WidthmsEditField
            app.WidthmsEditField = uieditfield(app.GridLayout, 'text');
            app.WidthmsEditField.HorizontalAlignment = 'right';
            app.WidthmsEditField.Layout.Row = 5;
            app.WidthmsEditField.Layout.Column = 6;
            app.WidthmsEditField.Value = '0.5, 1';
            app.WidthmsEditField.Tooltip = 'Width of the voltage transient (spike) in [ms], recommended: 0.5, 1';
            
            
            % Create WidthmsEditFieldLabel
            app.WidthmsEditFieldLabel = uilabel(app.GridLayout);
            app.WidthmsEditFieldLabel.HorizontalAlignment = 'right';
            app.WidthmsEditFieldLabel.Layout.Row = 5;
            app.WidthmsEditFieldLabel.Layout.Column = 5;
            app.WidthmsEditFieldLabel.Text = 'Width [ms]';
            app.WidthmsEditFieldLabel.Tooltip = app.WidthmsEditField.Tooltip;
            
            % Create NoscalesEditField
            app.NoscalesEditField = uieditfield(app.GridLayout, 'numeric');
            app.NoscalesEditField.Limits = [3 6];
            app.NoscalesEditField.Layout.Row = 4;
            app.NoscalesEditField.Layout.Column = 6;
            app.NoscalesEditField.Value = 5;
            app.NoscalesEditField.Tooltip = 'Number of scales across which wavelet will be stretched; recommended: 5';
            
            % Create NoscalesEditFieldLabel
            app.NoscalesEditFieldLabel = uilabel(app.GridLayout);
            app.NoscalesEditFieldLabel.HorizontalAlignment = 'right';
            app.NoscalesEditFieldLabel.Layout.Row = 4;
            app.NoscalesEditFieldLabel.Layout.Column = 5;
            app.NoscalesEditFieldLabel.Text = 'No. scales';
            app.NoscalesEditFieldLabel.Tooltip = app.NoscalesEditField.Tooltip;
            
            % Create NospikesEditField
            app.NospikesEditField = uieditfield(app.GridLayout, 'numeric');
            app.NospikesEditField.Limits = [50 1000];
            app.NospikesEditField.Layout.Row = 3;
            app.NospikesEditField.Layout.Column = 6;
            app.NospikesEditField.Value = 200;
            app.NospikesEditField.Tooltip = 'Number of spikes used to adapt the wavelet, recommended: 200';
            
            % Create NospikesEditFieldLabel
            app.NospikesEditFieldLabel = uilabel(app.GridLayout);
            app.NospikesEditFieldLabel.HorizontalAlignment = 'right';
            app.NospikesEditFieldLabel.Layout.Row = 3;
            app.NospikesEditFieldLabel.Layout.Column = 5;
            app.NospikesEditFieldLabel.Text = 'No. spikes';
            app.NospikesEditFieldLabel.Tooltip = app.NospikesEditField.Tooltip;
            
            % Create MultiplierEditField
            app.MultiplierEditField = uieditfield(app.GridLayout);
            app.MultiplierEditField.Layout.Row = 2;
            app.MultiplierEditField.Layout.Column = 6;
            app.MultiplierEditField.Value = num2str(3.5);
            app.MultiplierEditField.HorizontalAlignment = 'right';
            app.MultiplierEditField.Tooltip = 'The threshold multiplier used in spike detection. List separated by commas. At least 1 required. First entry will be used to extract waveform to adapt wavelet.';
            
            
            % Create MultiplierEditFieldLabel
            app.MultiplierEditFieldLabel = uilabel(app.GridLayout);
            app.MultiplierEditFieldLabel.HorizontalAlignment = 'right';
            app.MultiplierEditFieldLabel.Layout.Row = 2;
            app.MultiplierEditFieldLabel.Layout.Column = 5;
            app.MultiplierEditFieldLabel.Text = 'Multiplier';
            app.MultiplierEditFieldLabel.Tooltip = app.MultiplierEditField.Tooltip;
            
            % Create SaveButton
            app.SaveButton = uibutton(app.GridLayout, 'push');
            app.SaveButton.ButtonPushedFcn = createCallbackFcn(app, @SaveButtonPushed, true);
            app.SaveButton.Layout.Row = 14;
            app.SaveButton.Layout.Column = 6;
            app.SaveButton.Text = 'Save';
            app.SaveButton.Tooltip = 'Save parameters before running spike detection';
            
            % Create DatafolderpathEditField
            app.DatafolderpathEditField = uieditfield(app.GridLayout, 'text');
            app.DatafolderpathEditField.ValueChangedFcn = createCallbackFcn(app, @DatafolderpathEditFieldValueChanged, true);
            app.DatafolderpathEditField.Layout.Row = 2;
            app.DatafolderpathEditField.Layout.Column = 3;
            app.DatafolderpathEditField.Tooltip = app.LoaddataButton.Tooltip;
            
            % Create SavefolderpathEditField
            app.SavefolderpathEditField = uieditfield(app.GridLayout, 'text');
            app.SavefolderpathEditField.ValueChangedFcn = createCallbackFcn(app, @SavefolderpathEditFieldValueChanged, true);
            app.SavefolderpathEditField.Layout.Row = 3;
            app.SavefolderpathEditField.Layout.Column = 3;
            app.SavefolderpathEditField.Tooltip = app.OutputfolderButton.Tooltip;
            app.SavefolderpathEditField.Value = [pwd, filesep];
            
            % Create ListoffilesTextAreaLabel
            app.ListoffilesTextAreaLabel = uilabel(app.GridLayout);
            app.ListoffilesTextAreaLabel.HorizontalAlignment = 'center';
            app.ListoffilesTextAreaLabel.FontSize = 14;
            app.ListoffilesTextAreaLabel.FontWeight = 'bold';
            app.ListoffilesTextAreaLabel.Layout.Row = 4;
            app.ListoffilesTextAreaLabel.Layout.Column = [2 3];
            app.ListoffilesTextAreaLabel.Text = 'List of files';
            
            % Create ListoffilesTextArea
            app.ListoffilesTextArea = uitextarea(app.GridLayout);
            app.ListoffilesTextArea.Editable = 'off';
            app.ListoffilesTextArea.FontName = 'Courier';
            app.ListoffilesTextArea.Layout.Row = [5 7];
            app.ListoffilesTextArea.Layout.Column = [2 3];
            app.ListoffilesTextArea.FontColor = [0 0 0];
            app.ListoffilesTextArea.Position = [258 277 150 157];
            
            % Create AnalysedFilesTextAreaLabel
            app.AnalysedFilesTextAreaLabel = uilabel(app.GridLayout);
            app.AnalysedFilesTextAreaLabel.HorizontalAlignment = 'center';
            app.AnalysedFilesTextAreaLabel.FontSize = 14;
            app.AnalysedFilesTextAreaLabel.FontWeight = 'bold';
            app.AnalysedFilesTextAreaLabel.Layout.Row = 8;
            app.AnalysedFilesTextAreaLabel.Layout.Column = [2 3];
            app.AnalysedFilesTextAreaLabel.Text = 'Analysed files';
            
            % Create AnalysedFilesTextArea
            app.AnalysedFilesTextArea = uitextarea(app.GridLayout);
            app.AnalysedFilesTextArea.Editable = 'off';
            app.AnalysedFilesTextArea.Layout.Row = [9 11];
            app.AnalysedFilesTextArea.Layout.Column = [2 3];
            app.AnalysedFilesTextArea.FontName = 'Courier';
            app.AnalysedFilesTextArea.FontWeight = 'bold';
            app.AnalysedFilesTextArea.FontColor = [0.4667 0.6745 0.1882];
            app.AnalysedFilesTextArea.Value = {''};
            
            
            % Create DetectspikesButton
            app.DetectspikesButton = uibutton(app.GridLayout, 'push');
            app.DetectspikesButton.ButtonPushedFcn = createCallbackFcn(app, @DetectspikesButtonPushed, true);
            app.DetectspikesButton.FontSize = 14;
            app.DetectspikesButton.FontWeight = 'bold';
            app.DetectspikesButton.Layout.Row = [13 14];
            app.DetectspikesButton.Layout.Column = [2 3];
            app.DetectspikesButton.Text = 'Detect spikes';
            app.DetectspikesButton.Tooltip = 'Run spike detection (save parameters first!)';
            
            % Create SpiketimeunitDropDownLabel
            app.SpiketimeunitDropDownLabel = uilabel(app.GridLayout);
            app.SpiketimeunitDropDownLabel.HorizontalAlignment = 'right';
            app.SpiketimeunitDropDownLabel.Layout.Row = 13;
            app.SpiketimeunitDropDownLabel.Layout.Column = 5;
            app.SpiketimeunitDropDownLabel.Text = 'Spike time unit';
            app.SpiketimeunitDropDownLabel.Tooltip = 'Select time unit in which the spikes will be saved';
            
            % Create SpiketimeunitDropDown
            app.SpiketimeunitDropDown = uidropdown(app.GridLayout);
            app.SpiketimeunitDropDown.Items = {'[frames]', '[s]', '[ms]'};
            app.SpiketimeunitDropDown.ValueChangedFcn = createCallbackFcn(app, @SpiketimeunitDropDownValueChanged, true);
            app.SpiketimeunitDropDown.Layout.Row = 13;
            app.SpiketimeunitDropDown.Layout.Column = 6;
            app.SpiketimeunitDropDown.Value = '[frames]';
            app.SpiketimeunitDropDown.Tooltip = app.SpiketimeunitDropDownLabel.Tooltip;
            
            % Show the figure after all components are created
            app.UIFigure.Visible = 'on';
        end
    end
    
    % App creation and deletion
    methods (Access = public)
        
        % Construct app
        function app = getSpikesApp
            
            % Create UIFigure and components
            createComponents(app)
            
            % Register the app with App Designer
            registerApp(app, app.UIFigure)
            
            if nargout == 0
                clear app
            end
        end
        
        % Code that executes before app deletion
        function delete(app)
            
            % Delete UIFigure when app is deleted
            delete(app.UIFigure)
        end
    end
end