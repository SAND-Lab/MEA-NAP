function [spikeTimes, spikeWaveforms, trace, threshold] = detectSpikesCWT(...
    data, fs, Wid, wname, L, Ns, multiplier, nSpikes, ttx, ...
    minPeakThrMultiplier, maxPeakThrMultiplier, posPeakThrMultiplier, ...
    multiple_templates, multi_template_method, channelInfo, plot_folder, ...
    run_detection_in_chunks, chunk_length, threshold_calculation_window, ...
    absThreshold, filterLowPass, filterHighPass, remove_artifacts, refPeriod, ...
    getTemplateRefPeriod)

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
%                          This is used for artifact removal
%   
%   maxPeakThrMultiplier: [scalar] specifies the maximal spike amplitude
%
%   posPeakThrMultiplier: [scalar] specifies the maximal positive peak of the spike
%   remove_artifacts: [0, 1, or boolean] set to 1 to remove artifacts based
%   on some lower and upper bound in voltage 
%   refPeriod : [float]
%   refractory period to be imposed between detected spikes (ms) for
%   spike detection 
%   getTemplateRefPeriod : [float]
%   refractory period to be imposed between detected spikes (ms) for
%   adapting templates (to avoid compound spike waveforms)


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
% Log
% Author:
%   Jeremy Chabros, University of Cambridge, 2020
%   email: jjc80@cam.ac.uk
%   github.com/jeremi-chabros
% Modified by Tim Sit 
% 2023-11-16 : Added SWTTEO detection
%              and removed try-catch for custom wavelet method ('mea')


% Filter signal
lowpass = filterLowPass;  
highpass = filterHighPass; 
wn = [lowpass highpass] / (fs / 2);
filterOrder = 3;
[b, a] = butter(filterOrder, wn);
trace = filtfilt(b, a, double(data));

win = 10;   % [frames]

% Setting this to zero by default
threshold = nan;

if ~exist('absThreshold', 'var')
    absThreshold = nan;
end 

if strcmp(wname, 'mea') && ~ttx
    
    %   Use threshold-based spike detection to obtain the median waveform
    %   from nSpikes
    [aveWaveform, ~] = getTemplate(trace, multiplier, getTemplateRefPeriod, fs, nSpikes, ...
        multiple_templates, multi_template_method, channelInfo, plot_folder);

    if multiple_templates
        
        if ~exist('aveWaveform', 'var')
            warning('Cannot get average waveform, likely multiplier too high');
        else 
            num_ave_waveform = size(aveWaveform, 2);

            for waveform_idx = 1:num_ave_waveform 
                wavelet_name = strcat('mea', num2str(waveform_idx));
                waveform = aveWaveform(:, waveform_idx);
                adaptWavelet(waveform, wavelet_name);
            end 
        end 
        
    else
        %   Adapt custom wavelet from the waveform obtained above
        try
            adaptWavelet(aveWaveform);
        catch
            warning('Failed to adapt custom wavelet');
        end
    end
    
end

spikeWaveforms = [];
spikeTimes = [];
filterFlag = 0;


if startsWith(wname, 'thr')
    % Detect spikes with threshold method
    multiplier = strrep(wname, 'p', '.');
    multiplier = strrep(multiplier, 'thr', '');
    multiplier = str2num(multiplier);
    absoluteThreshold = nan;
    [spikeTrain, ~, threshold] = detectSpikesThreshold(trace, multiplier, ... 
        refPeriod, fs, filterFlag, absoluteThreshold, threshold_calculation_window);
    spikeTimes = find(spikeTrain == 1);  % (this is actually spike frames...)

    % Align spikes by negative peak & remove artifacts by amplitude
    [spikeTimes, spikeWaveforms] = alignPeaks(spikeTimes, trace, win, remove_artifacts,...
        minPeakThrMultiplier,...
        maxPeakThrMultiplier,...
        posPeakThrMultiplier);

elseif startsWith(wname, 'absthr')
    absThreshold = strrep(wname, 'p', '.');
    absThreshold = strrep(absThreshold, 'thr', '');
    absThreshold = str2num(absThreshold);
    [spikeTrain, ~, ~] = detectSpikesThreshold(trace, 0, refPeriod, fs, 0, absThreshold, threshold_calculation_window);
    spikeTimes = find(spikeTrain == 1);
    threshold = absThreshold;
elseif startsWith(wname, 'customAbs')
    multiplier = 0;
    [spikeTrain, ~, ~] = detectSpikesThreshold(trace, multiplier, ...
        refPeriod, fs, filterFlag, absThreshold, threshold_calculation_window);
    spikeTimes = find(spikeTrain == 1);
    threshold = absThreshold;

    % Align spikes by negative peak & remove artifacts by amplitude
    [spikeTimes, spikeWaveforms] = alignPeaks(spikeTimes, trace, win, remove_artifacts,...
        minPeakThrMultiplier,...
        maxPeakThrMultiplier,...
        posPeakThrMultiplier);
            
elseif startsWith(wname, 'mea') && multiple_templates

    mult_template_spike_times = {};
    mult_template_spike_waveforms = {};

    for waveform_idx = 1:num_ave_waveform 
        wavelet_name = strcat('mea', num2str(waveform_idx));
        % Detect spikes with wavelet method
        if run_detection_in_chunks
            j=1;
            spikeTimes = [];
            for segment = 1:round(length(trace)/fs/chunk_length)
                if j+(chunk_length*fs)<=length(trace)
                    spikeVec = j + detectSpikesWavelet(trace(j:j+(chunk_length*fs)), fs/1000, Wid, Ns, 'l', L, wavelet_name, 0, 0);
                else
                    spikeVec = j + detectSpikesWavelet(trace(j:end), fs/1000, Wid, Ns, 'l', L, wavelet_name, 0, 0);
                end
                spikeTimes = horzcat(spikeTimes, spikeVec);
                j = j+(chunk_length*fs);
            end
        else
            spikeTimes = detectSpikesWavelet(trace, fs/1000, Wid, Ns, 'l', L, wavelet_name, 0, 0);
        end 
        % Align spikes by negative peak & remove artifacts by amplitude
        [spikeTimes, spikeWaveforms] = alignPeaks(spikeTimes, trace, win, remove_artifacts,...
            minPeakThrMultiplier,...
            maxPeakThrMultiplier,...
            posPeakThrMultiplier);

        mult_template_spike_times{waveform_idx} = spikeTimes;
        mult_template_spike_waveforms{waveform_idx} = spikeWaveforms;
    end 

    % Outputs a cell rather than the usual vector of spike times
    spikeTimes = mult_template_spike_times; 
    spikeWaveforms = mult_template_spike_waveforms;

elseif strcmp(wname, 'swtteo')
    detectionParams = struct();
    spikeTimes = SWTTEO(trace, fs, detectionParams);

else 
    % Detect spikes with wavelet method
    if run_detection_in_chunks
        j=1;
        spikeTimes = [];
        for segment = 1:round(length(trace)/fs/chunk_length)
            if j+(chunk_length*fs)<=length(trace)
                spikeVec = j + detectSpikesWavelet(trace(j:j+(chunk_length*fs)), fs/1000, Wid, Ns, 'l', L, wname, 0, 0);
            else
                spikeVec = j + detectSpikesWavelet(trace(j:end), fs/1000, Wid, Ns, 'l', L, wname, 0, 0);
            end
            spikeTimes = horzcat(spikeTimes, spikeVec);
            j = j+(chunk_length*fs);
        end
    else 
        spikeTimes = detectSpikesWavelet(trace, fs/1000, Wid, Ns, 'l', L, wname, 0, 0);
    end 
    % Align spikes by negative peak & remove artifacts by amplitude
    [spikeTimes, spikeWaveforms] = alignPeaks(spikeTimes, trace, win, remove_artifacts,...
        minPeakThrMultiplier,...
        maxPeakThrMultiplier,...
        posPeakThrMultiplier);
end
    
end
