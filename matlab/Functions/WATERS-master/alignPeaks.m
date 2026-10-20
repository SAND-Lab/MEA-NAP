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

% NOTE: currently 'win' refers to the width of the bin that is searched for
% the peak, NOT to the width of the waveform (hard-coded to 25);
% TODO: Pass it as an argument

% 2025-11-23 Tim 
% There seems to be some issue with the window (Sfr) assignment indexing
% So for now I am separating whatever that step is doing with the artifact
% removal, in order to make sure the artifact removal steps actually works

waveform_width = 25;

% Obtain thresholds for artifact removal
threshold = median(trace) - median(abs(trace - mean(trace)))/0.6745;

% TODO: should be a user option to use multiplier or absolute threshold
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
spikeWaveforms = zeros(length(spikeTimes),waveform_width*2+1);

for i = 1:length(spikeTimes)
    
    if spikeTimes(i)+win < length(trace)-1 && spikeTimes(i)-win > 1
        
        % Look into a window around the spike
        bin = trace(spikeTimes(i)-win:spikeTimes(i)+win);
        
        negativePeak = min(bin);
        positivePeak = max(bin);
        pos = find(bin == negativePeak);
        
        % 2025-11-23 : Tim: The issue here is that with the new spike time, you
        % may introduce something that actually crosses the thresholds...
        % Remove artifacts and assign new timestamps
        if artifactFlg
            if (negativePeak < minPeakThr) && (positivePeak < posPeakThr) && (negativePeak > maxPeakThr)
                newSpikeTime = spikeTimes(i)+pos-win;
                if newSpikeTime+waveform_width < length(trace) && newSpikeTime-waveform_width > 1
                    
                    waveform = trace(newSpikeTime-waveform_width:newSpikeTime+waveform_width);
                    % Double check the new waveform is also valid
                    negativePeak = min(waveform);
                    positivePeak = max(waveform);
                    if (negativePeak < minPeakThr) && (positivePeak < posPeakThr) && (negativePeak > maxPeakThr)
                        sFr(i) = newSpikeTime;
                        spikeWaveforms(i, :) = waveform;
                    end 
                    
                end
            end
            
        else
            newSpikeTime = spikeTimes(i)+pos-win;
            if newSpikeTime+waveform_width < length(trace) && newSpikeTime-waveform_width > 1
                waveform = trace(newSpikeTime-waveform_width:newSpikeTime+waveform_width);
                sFr(i) = newSpikeTime;
                spikeWaveforms(i, :) = waveform;
            end
        end
        %
    end
end

% Pre-allocation & logical indexing made it a lot faster
% than using (end+1) indexing in the loop above
spikeTimes = sFr(sFr~=0);
spikeWaveforms = spikeWaveforms(sFr~=0,:);

end

