function [spikeTimes, spikeWaveforms] = alignPeaks(spikeTimes, trace, win,...
    artifactFlg, varargin)

% Description:
%   Aligns spikes by negative peaks and removes artifacts by amplitude

% INPUT:
%   spikeTimes: vector containing spike times
%   trace: [n x 1] filtered voltage trace
%   win: [scalar] window around the spike in [frames];
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

% NOTE: currently 'win' refers to the width of the bin that is searched for
% the peak, NOT to the width of the waveform (hard-coded to 25);
% TODO: Pass it as an argument

% Obtain thresholds for artifact removal
threshold = median(trace) - median(abs(trace - mean(trace)))/0.6745;

% Comment out to use the multiplier
% if artifactFlg
%     minPeakThr = threshold * varargin{1};
%     maxPeakThr = -threshold * varargin{2};
%     posPeakThr = -threshold * varargin{3};
% end

% Uses absolute threshold in microvolts
if artifactFlg
    minPeakThr = varargin{1}; % e.g. -7 uV
    maxPeakThr = varargin{2}; % e.g. -100 uV
    posPeakThr = varargin{3}; % % e.g. 100 uV
end

sFr = zeros(length(spikeTimes),1);
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
            if (negativePeak < minPeakThr) && (positivePeak < posPeakThr) && (negativePeak > maxPeakThr)
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

