function spikeLatencies = getSpikeLatencyRelStim(allStimTimes, spikeTimesStimRemoved)
%GETSPIKELATENCYRELSTIM Summary of this function goes here
%   Detailed explanation goes here

spikeLatencies = zeros(length(allStimTimes), 1);

for stimIdx = 1:length(allStimTimes)
    
    stimTime = allStimTimes(stimIdx);
    spikeTimesRelStim = spikeTimesStimRemoved - stimTime;
    spikeTimesRelStim = min(spikeTimesRelStim(spikeTimesRelStim > 0));
    if isempty(spikeTimesRelStim)
        spikeTimesRelStim = nan;
    end
    
    spikeLatencies(stimIdx) = spikeTimesRelStim;
    
end 

end

