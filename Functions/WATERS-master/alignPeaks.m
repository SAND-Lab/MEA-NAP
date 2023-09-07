function [spikeTimes, spikeWaveforms] = alignPeaks(spikeTimes, trace, win,...
    artifactFlg, varargin)

% Description:
%   Aligns spikes by negative peaks and removes artifacts by amplitude

% INPUT:
%   spikeTimes: vector containing spike times
%   trace: [n x 1] filtered voltage trace
%   win: [scalar] window around the spike in [frames]; 
%        this is the width of the bin that is used to search for the peak 
%        c.f. with waveform_width, which is the half width of the aligned
%        spike (so the full width will be [-waveform_width peak
%        +waveform_wdith])
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

% TODO: should be a user option to use multiplier or absolute threshold
% Comment out to use the multiplier
% threshold = 5;
% if artifactFlg
%     minPeakThr = threshold * varargin{1};
%     maxPeakThr = -threshold * varargin{2};
%     posPeakThr = -threshold * varargin{3};
% end

% NOTE: currently 'win' refers to the width of the bin that is searched for
% the peak, NOT to the width of the waveform (hard-coded to 25);
% TODO: Pass it as an argument
waveform_width = 25;

minThr = -inf; maxThr = inf; posThr = inf;
traceLength = length(trace);

% Uses absolute threshold in microvolts
if artifactFlg
    minThr = varargin{1}; % e.g. -7 uV
    maxThr = varargin{2}; % e.g. -100 uV
    posThr = varargin{3}; % % e.g. 100 uV
end

% Filter out spikeTimes too close to the borders
validSpikes = (spikeTimes+win<traceLength-1) & (spikeTimes-win>1);
spikeTimes = spikeTimes(validSpikes);

% Array to store spikes and waveforms
spikeWaveforms = zeros(length(spikeTimes),waveform_width*2+1);
sFr = zeros(length(spikeTimes),1);

% Calculate bins for all spikes at once
bins = arrayfun(@(s) trace(s-win:s+win), spikeTimes, 'UniformOutput', false);

% For each bin
for i = 1:length(bins)
    bin = bins{i};
    negativePeak = min(bin);
    positivePeak = max(bin);
    pos = find(bin == negativePeak, 1, 'first');

    if artifactFlg && (negativePeak < minThr || positivePeak > posThr || negativePeak > maxThr)
        continue
    end

    newSpikeTime = spikeTimes(i)+pos-win;

    if newSpikeTime+waveform_width < traceLength && newSpikeTime-waveform_width > 1
        waveform = trace(newSpikeTime-waveform_width:newSpikeTime+waveform_width);
        sFr(i) = newSpikeTime;
        spikeWaveforms(i, :) = waveform;
    end
end

% remove zero entries
validIdx = sFr ~= 0;
spikeTimes = sFr(validIdx);
spikeWaveforms = spikeWaveforms(validIdx,:);

end


