function figHandle = plotStimTimes(rawData, stimInfo, Params, figHandle)


if ~exist('figHandle', 'var') 
    figHandle = figure();
elseif ~isgraphics(figHandle)
    figHandle = figure();
end 

p = [100 100 600 1500];
set(figHandle, 'Position', p);


stimResamplingHz = 1000;
numTimeSamples = size(rawData, 1);
stimDataDurS = numTimeSamples / Params.fs;
stimResampleN = round(stimDataDurS * stimResamplingHz);
stimResampleTimes = linspace(0, stimDataDurS, stimResampleN);

for channelIdx = 1:length(stimInfo)
    
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


    vert_offset = channelIdx * 1.2;
    plot(stimResampleTimes, stimVector + vert_offset)
    hold on

    % Text label of channel idx 
    text(-1, vert_offset + 0.5, num2str(channelIdx), 'HorizontalAlignment', 'right');
    % Text label of channel name
    text(stimDataDurS+1, vert_offset + 0.5, num2str(stimInfo{channelIdx}.channelName));
end
box off 
yticks([])
ylabel('Channel (with some vertical offset)');
xlabel('Time (sec)');
set(gcf, 'color', 'white')
set(gca, 'TickDir', 'out')
ax1 = gca();
ax1.YAxis.Visible = 'off'; 


end