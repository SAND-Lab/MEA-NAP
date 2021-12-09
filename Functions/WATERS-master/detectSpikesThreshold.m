function [spikeTrain, filtTrace, threshold] = ...
    detectSpikesThreshold(trace, multiplier, refPeriod, fs, filterFlag, absoluteThreshold, ...
    threshold_calculation_window)

% Description:
%   Threshold-based spike detection

% INPUT:
%   trace: [n x 1] raw or filtered voltage trace
%   multiplier: [scalar] threshold multiplier used for spike detection
%   refPeriod: [scalar] refractory period [ms] after a spike in which
%                       no spikes will be detected
%   fs: [scalar] sampling frequency in [Hz]
%   filterFlag: specifies whether to filter the trace (1); (0) otherwise
%   absoluteThreshold : [scalar] absolute threshold, and if provided
%   ignores the multiplier argument
%   threshold_calculation_window [2 x 1] or [1 x 2]
%   start and end window to calculate thresholds in terms of proportion of
%   the recording 0 means start of recording and 1 means end of recording
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

if ~exist('threshold_calculation_window', 'var')
    threshold_calculation_window = [0, 1];
end 

if ~exist('absoluteThreshold', 'var')
    absoluteThreshold = nan;
end 

% Calculate the threshold (median absolute deviation)
% See: https://en.wikipedia.org/wiki/Median_absolute_deviation
if ~isnan(absoluteThreshold)
    threshold = absoluteThreshold;
else
    window_frame_start = round(length(trace) * threshold_calculation_window(1) + 1);
    window_frame_end = round(length(trace) * threshold_calculation_window(2));
    subset_trace = trace(window_frame_start:window_frame_end);
    s = median(abs(trace-mean(subset_trace)))/0.6745;     % Faster than mad(X,1);
    m = median(subset_trace);                % Note: filtered trace is already zero-mean
    threshold = m - multiplier*s;

end 
% else
%     s = median(abs(trace-mean(trace)))/0.6745;     % Faster than mad(X,1);
%     m = median(trace);                % Note: filtered trace is already zero-mean
%     threshold = m - multiplier*s;

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
