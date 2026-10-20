function figHandle = plotIdvStimDataAndTrace(rawData, channelIdx, stimInfo, Params)
%PLOTELECSTIMDATAANDTRACE Summary of this function goes here
%   Detailed explanation goes here



figHandle = figure;

p = [100 100 1000 600];
set(figHandle, 'Position', p);

subplot(2, 1, 1)

% Plot detection threshold
if strcmp(Params.stimDetectionMethod, 'absPosThreshold')
    yline(Params.stimDetectionVal, 'linestyle', '--');
    hold on 
end 

numTimeSamples = size(rawData, 1);
stimDataDurS = numTimeSamples / Params.fs;

% Resample the stimulation vector 
stimResamplingHz = 1000;  % TODO: specify this in Params
stimResampleN = round(stimDataDurS * stimResamplingHz);
stimResampleTimes = linspace(0, stimDataDurS, stimResampleN);

recordingTime = linspace(0, stimDataDurS, numTimeSamples);
plot(recordingTime, rawData(:, channelIdx));
box off
xlabel('Time')
ylabel('Filtered signal')
title(sprintf('Electrode %.f (Channel %.f)', stimInfo{channelIdx}.channelName, channelIdx))

subplot(2, 1, 2)
stimVector = zeros(stimResampleN, 1);
    
elecStimTimes = stimInfo{channelIdx}.elecStimTimes;
% elecStimDur = stimInfo{channelIdx}.elecStimDur;

elecStimDur = Params.stimDurationForPlotting;

for stimIdx = 1:length(elecStimTimes)
        
    stimLoc = find(stimResampleTimes >= elecStimTimes(stimIdx) & ...
        (stimResampleTimes) <= elecStimTimes(stimIdx) + elecStimDur ...
        );
    stimVector(stimLoc) = 1;
end


plot(stimResampleTimes, stimVector)
ylim([0, 1])
ylabel('Stim Pulses Detected')
xlabel('Time (s)')
box off 
set(gcf, 'color', 'w')

end

