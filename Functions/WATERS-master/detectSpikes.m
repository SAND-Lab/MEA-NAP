classdef detectSpikes
    
    % Description:
    % This script serves as a way to merge all the methods required for
    % spike detection into one class with hope to facilitate running it
    % on large datasets with maximal flexibility and minimal user input
    
    properties (Access = public)
        dataPath; % required: path to the folder containing recordings
        savePath; % required: path to the desired output destination
        params;   % required: parameters for spike detection; see:
        option;   % optional
        files;    % optional If passing path (NOT files)
    end
    
    methods (Access = public)
        
        function getSpikes(self)
            
            % Description:
            %	Master script for spike detection using CWT method. Runs spike
            %	detection through recordings, cost parameters, electrodes, and
            %	wavelets.
            
            if ~endsWith(self.dataPath, filesep)
                self.dataPath = [self.dataPath filesep];
            end
            addpath(self.dataPath);
            
            % TODO: get rid of this atrocity
            multiplier = self.params.multiplier;
            thresholds = self.params.thresholds;
            grd = self.params.grd;
            costList = self.params.costList;
            wnameList = self.params.wnameList;
            unit = self.params.unit;
            
            % struct fields cannot contain dots
            thrList = strcat( 'thr', thresholds);
            thrList = strrep(thrList, '.', 'p')';
            wnameList = horzcat(wnameList', thrList);
            
            % Get files
            % Modify the '*string*.mat' wildcard to include a subset of recordings
            % TODO: maybe pass the file spec wild card as an argument
            if isprop(self, 'option') && strcmp(self.option, 'list') && isprop(self, 'files')
                if ~iscell(self.files)
                    self.files = {self.files};
                end
            else
                self.files = dir([self.dataPath '*.mat']);
            end
            
            for recording = 1:numel(self.files)
                
                if isprop(self, 'option') && strcmp(self.option, 'list')
                    fileName = self.files{recording};
                else
                    fileName = [self.dataPath self.files(recording).name];
                end
                
                % Load data
                disp(['Loading ' fileName ' ...']);
                file = load(fileName);
                disp('File loaded');
                
                data = file.dat;
                channels = file.channels;
                fs = file.fs;
                self.params.fs = fs;
                self.params.ttx = contains(fileName, 'TTX');
                self.params.duration = length(data)/fs;
                
                % Truncate the data if desired
                if isfield(self.params, 'subsample_time')
                    if ~isempty(self.params.subsample_time)
                        if self.params.subsample_time(1) == 1
                            start_frame = 1;
                            
                        else
                            start_frame = self.params.subsample_time(1) * fs;
                            
                        end
                        end_frame = self.params.subsample_time(2) * fs;
                        
                    end
                    data = data(start_frame:end_frame, :);
                    self.params.duration = length(data)/fs;
                end
                
                for L = costList
                    % Dunno if this is the way to go... At this point it's
                    % more intuitive to just specify L as an absolute value
                    % as opposed to a ratio
                    %                     L = log(L)/36.7368; % Convert from commission/omission ratio to actual cost parameter
                    
                    if startsWith(fileName, self.dataPath)
                        saveName = [self.savePath strrep(fileName(1:end-4), self.dataPath, '') '_L_' num2str(L) '_spikes.mat'];
                    else
                        saveName = [self.savePath fileName(1:end-4) '_L_' num2str(L) '_spikes.mat'];
                    end
                    
                    if ~exist(saveName, 'file') % Avoid running if file already exists
                        self.params.L = L;
                        tic
                        disp('Detecting spikes...');
                        disp(['L = ' num2str(L)]);
                        
                        % Pre-allocate for your own good
                        spikeTimes = cell(1,60);
                        spikeWaveforms = cell(1,60);
                        mad = zeros(1,60);
                        variance = zeros(1,60);
                        
                        % Run spike detection
                        for channel = 1:length(channels)
                            
                            % Pre-allocate again
                            spikeStruct = struct();
                            waveStruct = struct();
                            trace = data(:, channel);
                            
                            for wname = 1:numel(wnameList)
                                
                                wname = char(wnameList{wname});
                                valid_wname = strrep(wname, '.', 'p');
                                
                                spikeWaves = [];
                                spikeFrames = [];
                                
                                if ~(ismember(channel, grd))
                                    
                                    [spikeFrames, spikeWaves, trace] = detect_spikes_cwt(...
                                        self, trace, wname, L, multiplier);
                                    
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
                        end
                        
                        toc
                        
                        % Save results
                        save_suffix = ['_' strrep(num2str(L), '.', 'p')];
                        self.params.save_suffix = save_suffix;
                        self.params.fs = fs;
                        self.params.variance = variance;
                        self.params.mad = mad;
                        
                        spikeDetectionResult = struct();
                        spikeDetectionResult.method = 'CWT';
                        spikeDetectionResult.params = self.params;
                        
                        disp(['Saving results to: ' saveName]);
                        
                        varsList = {'spikeTimes', 'channels', 'spikeDetectionResult', ...
                            'spikeWaveforms'};
                        save(saveName, varsList{:}, '-v7.3');
                        disp(' ');
                    end
                end
            end
        end
        %%
        function [spikeTimes, spikeWaveforms, trace] = detect_spikes_cwt(...
                self, data, wname, L, multiplier)
            
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
            
            
            fs = self.params.fs;
            Wid = self.params.wid;
            Ns = self.params.ns;
            nSpikes = self.params.nSpikes;
            ttx = self.params.ttx;
            minPeakThrMultiplier = self.params.minPeakThrMultiplier;
            maxPeakThrMultiplier = self.params.maxPeakThrMultiplier;
            posPeakThrMultiplier = self.params.posPeakThrMultiplier;
            
            refPeriod = 0.2; % Only used by the threshold method
            
            % TODO: the workaround here would be to ALWAYS run alignPeaks.m
            % after any spike detection method and return:
            % unique(spikeTimes) instead of just spikeTimes
            
            % Filter signal
            try
                lowpass = 600;   % TODO: look into this
                highpass = 8000; % and this
                wn = [lowpass highpass] / (fs / 2);
                filterOrder = 3; % Used to be smth different, dunno anymore
                [b, a] = butter(filterOrder, wn);
                trace = filtfilt(b, a, double(data));
            catch
                % Note: some errors will appear irrespective of the
                % appropriate toolboxes being installed. Didn't bother to
                % code for all the cases and the same message will be
                % returned...
                error('Signal Processing Toolbox not found');
            end
            
            % NOTE: 'win' also specifies the number of frames before/after
            % spike to be saved. Smaller 'win' --> shorter waveform
            win = 25;   % [frames]
            
            if strcmp(wname, 'mea') && ~ttx
                
                %   Use threshold-based spike detection to obtain the median waveform
                %   from nSpikes
                try
                    [aveWaveform, ~] = get_template(self, trace, multiplier, refPeriod, fs, nSpikes);
                catch
                    warning('Failed to obtain mean waveform');
                end
                
                %   Adapt custom wavelet from the waveform obtained above
                try
                    adapt_wavelet(self, aveWaveform);
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
                    [spikeTrain, ~, ~] = detect_spikes_threshold(self, trace, multiplier, 2, fs, 0);
                    spikeTimes = find(spikeTrain == 1);
                elseif strcmp(wname, 'swtteo')
                    in.M = trace;
                    in.SaRa = fs;
                    self.params.method = 'auto';
                    self.params.filter = 0;
                    spikeTimes = SWTTEO(self, in, self.params);
                else
                    % Detect spikes with wavelet method
                    spikeTimes = detect_spikes_wavelet(self, trace, fs/1000, Wid, Ns, 'l', L, wname, 0, 0);
                end
                
                % Align spikes by negative peak & remove artifacts by amplitude
                [spikeTimes, spikeWaveforms] = align_peaks(self, spikeTimes, trace, win, 1,...
                    minPeakThrMultiplier,...
                    maxPeakThrMultiplier,...
                    posPeakThrMultiplier);
                spikeTimes = unique(spikeTimes);
            catch
                spikeTimes = [];
            end
        end
        %%
        function [aveWaveform, spikeTimes] = get_template(self, trace, multiplier, refPeriod, fs, nSpikes)
            
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
            
            [spikeTrain, ~, ~] = detect_spikes_threshold(self,...
                trace, multiplier, refPeriod, fs, 0);
            spikeTimes = find(spikeTrain == 1);
            [spikeTimes, spikeWaveforms] = align_peaks(self, spikeTimes, trace, 10,0);
            %   If fewer spikes than specified - use the maximum number possible
            if  numel(spikeTimes) < nSpikes
                nSpikes = sum(spikeTrain);
                disp(['Not enough spikes detected with specified threshold, using ', num2str(nSpikes),'instead']);
            end
            
            %   Uniformly sample n_spikes
            spikes2use = round(linspace(2, length(spikeTimes)-2, nSpikes));
            aveWaveform = median(spikeWaveforms(spikes2use,:));
        end
        %%
        function [spikeTrain, filtTrace, threshold] = detect_spikes_threshold(self,...
                trace, multiplier, refPeriod, fs, filterFlag)
            
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
            s = median(abs(trace-mean(trace)))/0.6745;     % Faster than mad(X,1);
            m = median(trace);                % Note: filtered trace is already zero-mean
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
        %%
        function [spikeTimes, spikeWaveforms] = align_peaks(self, spikeTimes, trace, win,...
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
            threshold = median(trace) - median(abs(trace - mean(trace)))/0.6745;
            if artifactFlg
                minPeakThr = -threshold * varargin{1};
                maxPeakThr = -threshold * varargin{2};
                posPeakThr = -threshold * varargin{3};
            end
            
            sFr = zeros(1,length(spikeTimes));
            spikeWaveforms = zeros(length(spikeTimes),51);
            
            for i = 1:length(spikeTimes)
                
                if spikeTimes(i)+win < length(trace)-1 && spikeTimes(i)-win > 1
                    
                    % Look into a window around the spike
                    bin = trace(spikeTimes(i)-win:spikeTimes(i)+win);
                    
                    negativePeak = min(bin);
                    positivePeak = max(bin);
                    pos = find(bin == negativePeak);
                    
                    % Remove artifacts and assign new timestamps
                    if artifactFlg
                        if (negativePeak < minPeakThr) && (positivePeak < posPeakThr)
                            newSpikeTime = spikeTimes(i)+pos-win;
                            if newSpikeTime+25 < length(trace) && newSpikeTime-25 > 1
                                waveform = trace(newSpikeTime-25:newSpikeTime+25);
                                sFr(i) = newSpikeTime;
                                spikeWaveforms(i, :) = waveform;
                            end
                        end
                    else
                        newSpikeTime = spikeTimes(i)+pos-win;
                        if newSpikeTime+25 < length(trace) && newSpikeTime-win > 1
                            waveform = trace(newSpikeTime-25:newSpikeTime+25);
                            sFr(i) = newSpikeTime;
                            spikeWaveforms(i, :) = waveform;
                        end
                    end
                end
            end
            
            % Pre-allocation & logical indexing made it a lot faster
            % than using (end+1) indexing in the loop above
            spikeTimes = sFr(sFr~=0);
            spikeWaveforms = spikeWaveforms(sFr~=0,:);
        end
        %%
        function [newWaveletIntegral, newWaveletSqN] = adapt_wavelet(self, aveWaveform)
            
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
            [Y,X,~] = pat2cwav(signal, 'orthconst', 0, 'none');
            
            % Test if a legitmate wavelet
            dxval = max(diff(X));
            newWaveletIntegral = dxval*sum(Y); %    Should be 1.0
            newWaveletSqN = dxval*sum(Y.^2);
            newWaveletSqN = round(newWaveletSqN,10); % Should be zero
            
            % Save the wavelet
            if newWaveletSqN == 1.0000 % Ugly but it is what it is
                
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
                self, Signal, SFr, Wid, Ns, option, L, wname, PltFlg, CmtFlg)
            
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
            W = determine_scales(self, wname,Wid,SFr,Ns);
            
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
                ct(ct<0)=0; % Delete if you allow positive peaks
                Index = ct(i,:) ~= 0;
                
                %make a union with coefficients from previous scales
                Index = or(Io,Index);
                Io = Index;
            end
            
            spikeFrames = parse(self, Index,SFr,Wid);
            
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
        %%
        function Scale = determine_scales(self, wname,Wid,SFr,Ns)
            
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
        %%
        function fcn = parse(self, Index,SFr,Wid)
            
            %This is a special function, it takes the vector Index which has
            %the structure [0 0 0 1 1 1 0 ... 0 1 0 ... 0]. This vector was obtained
            %by coincidence detection of certain events (lower and upper threshold
            %crossing for threshold detection, and the selfearance of coefficients at
            %different scales for wavelet detection).
            %The real challenge here is to merge multiple 1's that belong to the same
            %spike into one event and to locate that event
            
            Refract = 0.2;    %[ms] the refractory period -- can't resolve spikes
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
        %%
        function [spikepos, out_] = SWTTEO(self, in,params)
            %SWTTEO Detects Spikes Location using a modified WTEO approach
            %   Usage:  spikepos = swtteo(in);
            %           spikepos = swtteo(in,params);
            %
            %   Input parameters:
            %       in_struc:   Input structure which contains
            %                       M:      Matrix with data, stored columnwise
            %                       SaRa:   Sampling frequency
            %       optional input parameters:
            %                       none
            %   Output parameters:
            %       spikepos:   Timestamps of the detected spikes stored columnwise
            %
            %   Description:
            %       swtteo(in,params) computes the location of action potential in
            %       noisy sym5 sym5surements. This method is based on the work of N.
            %       Nabar and K. Rajgopal "A Wavelet based Teager Engergy Operator for
            %       Spike Detection in Microelectrode Array Recordings". The algorithm
            %       therein was further improved by using a stationary wavelet
            %       transform and a different thresholding concept.
            %       For an unsupervised usage the sensitivity of the algorithm can be
            %       adapted by changing the value of the variable global_fac in line
            %       108. A larger value results in fewer detected spikes but also the
            %       number of false positives decrease. Decreasing this factor makes it
            %       more sensitive to detect spikes.
            %
            %   References:
            %       tbd.
            %
            %
            %   Author: F. Lieb, February 2016
            
            if nargin<2
                params = struct;
            end
            
            %parse inputs
            [params,s,fs] = parse_input(self, in,params);
            TEO = @(x,k) (x.^2 - myTEOcircshift(self, x,[-k, 0]).*myTEOcircshift(self,x,[k, 0]));
            [L,c] = size(s);
            if L==1
                s = s';
                L = c;
                c = 1;
            end
            
            
            %do zero padding if the L is not divisible by a power of two
            pow = 2^params.wavLevel;
            if rem(L,pow) > 0
                Lok = ceil(L/pow)*pow;
                Ldiff = Lok - L;
                s = [s; zeros(Ldiff,c)];
            end
            
            %testing showed prefiltering didnt improve the results
            %prefilter signal
            if params.filter
                if ~isfield(params,'F1')
                    params.Fstop = 100;
                    params.Fpass = 200;
                    Apass = 0.2;
                    Astop = 80;
                    params.F1 = designfilt(   'highpassiir',...
                        'StopbandFrequency',params.Fstop ,...
                        'PassbandFrequency',params.Fpass,...
                        'StopbandAttenuation',Astop, ...
                        'PassbandRipple',Apass,...
                        'SampleRate',fs,...
                        'DesignMethod','butter');
                end
                f = filtfilt(params.F1,s);
            else
                f = s;
            end
            
            %non vectorized version:
            % [SWTa,~] = swt(s,wavLevel,wavelet);
            %     out22 = TEO(SWTa);
            
            %vectorized version:
            lo_D = wfilters(params.wavelet);
            out_ = zeros(size(s));
            ss = f;
            for k=1:params.wavLevel
                %Extension
                lf = length(lo_D);
                ss = extendswt(self,ss,lf);
                %convolution
                swa = conv2(ss,lo_D','valid');
                swa = swa(2:end,:); %even number of filter coeffcients
                %apply teo to swt output
                
                
                temp = abs(TEO(swa,1));
                
                if params.smoothing
                    wind = hamming(params.winlength);
                    %wind = sqrt(3*sum(wind.^2) + sum(wind)^2);
                    %temp = filtfilt(wind,1,temp);
                    if params.normalize_smoothingwindow
                        wind = wind./(sqrt(3*sum(wind.^2) + sum(wind)^2));
                    end
                    temp2 = conv2(temp,wind','same');
                    %temp = circshift(filter(wind,1,temp), [-3*1 1]);
                else
                    temp2 = temp;
                end
                
                out_ = out_ + temp2;
                
                
                %dyadic upscaling of filter coefficients
                lo_D = dyadup(lo_D,0,1);
                %updates
                ss = swa;
            end
            
            
            
            %non-vectorized version to extract spikes...
            switch params.method
                case 'auto'
                    %         global_fac = 1.11e+03;%1.6285e+03; %540;%1800;%430; %1198; %change this
                    global_fac = 430;%1.6285e+03; %540;%1800;%430; %1198; %change this
                    if c == 1
                        [CC,LL] = wavedec(s,5,'sym5');
                        lambda = global_fac*wnoisest(CC,LL,1);
                        thout = wthresh(out_,'h',lambda);
                        spikepos = get_spike_pos(self,thout,fs,s,params);
                    else
                        spikepos = cell(c,1);
                        for jj=1:c
                            [CC,LL] = wavedec(s(:,jj),5,'sym5');
                            lambda = global_fac*wnoisest(CC,LL,1);
                            thout = wthresh(out_(:,jj),'h',lambda);
                            spikepos{jj}=get_spike_pos(self,thout,fs,s(:,jj),params);
                        end
                    end
                case 'auto2'
                    %         global_fac = 9.064e+02;%1.3454e+03;%800;%1800;%430; %1198; %change this
                    global_fac = 1198;
                    params.method = 'auto';
                    if c == 1
                        [CC,LL] = wavedec(out_,5,'sym5');
                        lambda = global_fac*wnoisest(CC,LL,1);
                        thout = wthresh(out_,'h',lambda);
                        spikepos = get_spike_pos(self,thout,fs,s,params);
                    else
                        spikepos = cell(c,1);
                        for jj=1:c
                            [CC,LL] = wavedec(out_(:,jj),5,'sym5');
                            lambda = global_fac*wnoisest(CC,LL,1);
                            thout = wthresh(out_(:,jj),'h',lambda);
                            spikepos{jj}=get_spike_pos(self,thout,fs,s(:,jj),params);
                        end
                    end
                case 'numspikes'
                    if c == 1
                        spikepos=get_spike_pos(self,out_,fs,s,params);
                    else
                        spikepos = cell(1,c);
                        params_tmp = params;
                        for jj=1:c
                            % extract spike positions from wteo output
                            params_tmp.numspikes = params.numspikes(jj);
                            spikepos{jj}=get_spike_pos(self,out_(:,jj),fs,s(:,jj),params_tmp);
                        end
                    end
                case 'lambda'
                    thout = wthresh(out_,'h',params.lambda);
                    spikepos = get_spike_pos(self,thout,fs,s,params);
                case 'energy'
                    params.p = 0.80;
                    params.rel_norm =  5.718e-3;%5.718e-3;%4.842e-3;%22e-5;%1.445e-4;
                    %wavelet denoising
                    wdenoising = 0;
                    n = 9;
                    w = 'sym5';
                    tptr = 'sqtwolog'; %'rigrsure','heursure','sqtwolog','minimaxi'
                    
                    
                    if c == 1
                        if wdenoising == 1
                            out_ = wden(out_,tptr,'h','mln',n,w);
                            %high frequencies, decision variable
                            c = dgtreal(out_,{'hann',10},1,200);
                            out_ = sum(abs(c).^2,1);
                        end
                        spikepos = get_spike_pos(self,out_,fs,s,params);
                    else
                        spikepos = cell(c,1);
                        for jj=1:c
                            if wdenoising == 1
                                out_(:,jj) = wden(out_(:,jj),tptr,'h','mln',n,w);
                            end
                            spikepos{jj} = get_spike_pos(self,out_(:,jj),fs,s(:,jj),params);
                        end
                    end
                otherwise
                    error('unknown detection method specified');
            end
        end
        %%
        function [params,s,fs] = parse_input(self, in,params)
            %parse_input parses input variables
            s = in.M;
            fs = in.SaRa;
            %Default settings for detection method
            if ~isfield(params,'method')
                params.method = 'auto';
            end
            if strcmp(params.method,'numspikes')
                if ~isfield(params,'numspikes')
                    error('please specify number of spikes in params.numspikes');
                end
            end
            
            %Default settings for stationary wavelet transform
            if ~isfield(params,'wavLevel')
                params.wavLevel = 2;
            end
            if ~isfield(params, 'wavelet')
                params.wavelet = 'sym5';
            end
            if ~isfield(params, 'winlength')
                params.winlength = ceil(1.3e-3*fs); %1.3
            end
            if ~isfield(params, 'normalize_smoothingwindow')
                params.normalize_smoothingwindow = 0;
            end
            if ~isfield(params, 'smoothing')
                params.smoothing = 1;
            end
            if ~isfield(params, 'filter')
                params.filter = 0;
            end
        end
        %%
        function y = extendswt(self, x,lf)
            %EXTENDSWT extends the signal periodically at the boundaries
            [r,c] = size(x);
            y = zeros(r+lf,c);
            y(1:lf/2,:) = x(end-lf/2+1:end,:);
            y(lf/2+1:lf/2+r,:) = x;
            y(end-lf/2+1:end,:) = x(1:lf/2,:);
            
        end
        %%
        function X = myTEOcircshift(self,Y,k)
            %circshift without the boundary behaviour...
            
            colshift = k(1);
            rowshift = k(2);
            
            temp  = circshift(Y,k);
            
            if colshift < 0
                temp(end+colshift+1:end,:) = flipud(Y(end+colshift+1:end,:));
            elseif colshift > 0
                temp(1:1+colshift-1,:) = flipud(Y(1:1+colshift-1,:));
            else
                
            end
            
            if rowshift<0
                temp(:,end+rowshift+1:end) = fliplr(Y(:,end+rowshift+1:end));
            elseif rowshift>0
                temp(:,1:1+rowshift-1) = fliplr(Y(:,1:1+rowshift-1));
            else
            end
            
            X = temp;
        end
        %%
        function idx2 = get_spike_pos(self, input_sig,fs,orig_sig,params)
            %get_spike_pos computes spike positions from thresholded data
            %
            %   This function computes the exact spike locations based on a thresholded
            %   signal. The spike locations are indicated as non-zero elements in
            %   input_sig and are accordingly evaluated.
            %
            %   The outputs are the spike positions in absolute index values (no time
            %   dependance).
            %
            %   Author: F.Lieb, February 2016
            %
            
            
            %Define a fixed spike duration, prevents from zeros before this duration is
            %over
            %maxoffset
            spikeduration = 10e-4*fs; %10e-4
            %minoffset
            minoffset = 3e-4*fs; %3e-4
            
            offset = floor(5e-4*fs); %5e-4 %was 2e-4, dunno why
            L = length(input_sig);
            L2 = length(orig_sig);
            
            switch params.method
                case 'numspikes'
                    out = input_sig;
                    np = 0;
                    idx2 = zeros(1,params.numspikes);
                    while (np < params.numspikes)
                        [~, idxmax] = max(out);
                        idxl = idxmax;
                        idxr = idxmax;
                        out(idxmax) = 0;
                        offsetcounter = 0;
                        while( (out(max(1,idxl-2)) < out(max(1,idxl-1)) ||...
                                offsetcounter < minoffset) &&...
                                offsetcounter < spikeduration )
                            out(max(1,idxl-1)) = 0;
                            idxl = idxl-1;
                            offsetcounter = offsetcounter + 1;
                        end
                        offsetcounter = 0;
                        while( (out(min(L,idxr+2)) < out(min(L,idxr+1)) ||...
                                offsetcounter < minoffset ) &&...
                                offsetcounter < spikeduration )
                            out(min(L,idxr+1)) = 0;
                            idxr = idxr+1;
                            offsetcounter = offsetcounter + 1;
                        end
                        %new approach
                        
                        indexx = min(L2, idxmax-offset:idxmax+offset);
                        %indexx = min(L2,idxl-offset:idxr+offset); %old approach
                        indexx = max(offset,indexx);
                        idxx = find( abs(orig_sig(indexx)) == ...
                            max( abs(orig_sig(indexx) )),1,'first');
                        idx2(np+1) = idxmax - offset + idxx-1;
                        np = np + 1;
                    end
                case {'energy'}
                    rel_norm = params.rel_norm;
                    p = params.p;
                    ysig = input_sig;
                    normy = norm(input_sig);
                    L = length(input_sig);
                    %min and max length of signal duration
                    maxoffset = 12;
                    minoffset = 6;
                    offset = 5;
                    idx2 = [];
                    np = 0;
                    maxspikecount = 300;
                    temp = 0;
                    
                    %while( norm(ysig) > (1-p)*normy )
                    while( 1 )
                        norm_old = norm(ysig);
                        [~, idxmax] = max(ysig);
                        idxl = idxmax;
                        idxr = idxmax;
                        ysig(idxmax) = 0;
                        offsetcounter = 0;
                        while ( ( ysig(max(1,idxl-2)) < ysig(max(1,idxl-1)) ||...
                                offsetcounter < minoffset ) && ...
                                offsetcounter < maxoffset )
                            ysig(max(1,idxl-1)) = 0;
                            idxl = idxl - 1;
                            %if (ysig(max(1,idxl))==0)
                            %    break;
                            %end
                            offsetcounter = offsetcounter + 1;
                        end
                        offsetcounter = 0;
                        while ( ( ysig(min(L,idxr+2)) < ysig(min(L,idxr+1)) ||...
                                offsetcounter < minoffset ) && ...
                                offsetcounter < maxoffset )
                            ysig(min(L,idxr+1)) = 0;
                            idxr = idxr + 1;
                            %if (ysig(min(L,idxr)) == 0)
                            %    break;
                            %end
                            offsetcounter = offsetcounter + 1;
                        end
                        
                        indexx = min(L, idxmax-offset:idxmax+offset);
                        %indexx = min(L2,idxl-offset:idxr+offset); %old approach
                        indexx = max(offset,indexx);
                        idxx = find( abs(orig_sig(indexx)) == ...
                            max( abs(orig_sig(indexx) )),1,'first');
                        idx2(np+1) = idxmax - offset + idxx-1;
                        np = np + 1;
                        
                        fprintf('rel norm: %f\n', (norm_old-norm(ysig))/norm_old);
                        temp(np+1) = (norm_old-norm(ysig))/norm_old;
                        if (norm_old-norm(ysig))/norm_old < rel_norm
                            if length(idx2)>1
                                idx2 = idx2(1:end-1);
                            else
                                idx2 = [];
                            end
                            break
                        end
                        if  np > maxspikecount
                            break;
                        end
                    end
                    %figure(2), plot(temp);
                case {'auto','lambda'}
                    %helper variables
                    idx2=[];
                    iii=1;
                    test2 = input_sig;
                    %loop until the input_sig is only zeros
                    while (sum(test2) ~= 0)
                        %get the first nonzero position
                        tmp = find(test2,1,'first');
                        test2(tmp) = 0;
                        %tmp2 is the counter until the spike duration
                        tmp2 = min(length(test2),tmp + 1);%protect against end of vec
                        counter = 0;
                        %search for the end of the spike
                        while(test2(tmp2) ~= 0 || counter<spikeduration )
                            test2(tmp2) = 0;
                            tmp2 = min(length(test2),tmp2 + 1);
                            counter = counter + 1;
                        end
                        %spike location is in intervall [tmp tmp2], look for the max
                        %element in the original signal with some predefined offset:
                        indexx = min(length(orig_sig),tmp-offset:tmp2+offset);
                        indexx = max(offset,indexx);
                        idxx = find( abs(orig_sig(indexx)) == ...
                            max( abs(orig_sig(indexx) )),1,'first');
                        idx2(iii) = tmp - offset + idxx-1;
                        iii = iii+1;
                    end
                otherwise
                    error('unknown method');
            end
        end
    end
end