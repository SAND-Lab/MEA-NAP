function spikeLatencies = getSpikeLatencyRelStim(allStimTimes, spikeTimesStimRemoved, searchWindowEnd)
%GETSPIKELATENCYRELSTIM Calculate time-to-first-spike latency relative to stimulation
%   spikeLatencies = getSpikeLatencyRelStim(allStimTimes, spikeTimesStimRemoved, searchWindowEnd)
%
%   INPUT:
%       allStimTimes - vector of stimulation times (in seconds)
%       spikeTimesStimRemoved - vector of spike times (in seconds)
%       searchWindowEnd - end of search window in seconds relative to stim
%
%   OUTPUT:
%       spikeLatencies - vector of first-spike latencies in MILLISECONDS for each stim event
%                        NaN if no spike found in search window

spikeLatencies = zeros(length(allStimTimes), 1);

for stimIdx = 1:length(allStimTimes)
    
    stimTime = allStimTimes(stimIdx);
    spikeTimesRelStim = spikeTimesStimRemoved - stimTime;
    
    % Find spikes within the search window (0 to searchWindowEnd)
    validSpikes = spikeTimesRelStim(spikeTimesRelStim > 0 & spikeTimesRelStim <= searchWindowEnd);
    
    if isempty(validSpikes)
        latency_s = nan;
    else
        latency_s = min(validSpikes);  % First spike in window
    end
    
    % Convert to milliseconds
    spikeLatencies(stimIdx) = latency_s * 1000;
    
end 

end

