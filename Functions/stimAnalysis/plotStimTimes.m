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

electrodes = [];

for i = 1:length(stimInfo)
    electrodes = [electrodes stimInfo{i}.channelName];
end

sortedElecs = sort(electrodes);
channels = length(stimInfo);

for channelIdx = 1:length(stimInfo)
    stimVector = zeros(stimResampleN, 1);

    currElec = sortedElecs(channelIdx); % get current electrode (sorted)
    currChannel = find(electrodes == currElec); % get current channel in unsorted electrode list
    elecStimTimes = stimInfo{currChannel}.elecStimTimes;
    elecStimDur = Params.stimDurationForPlotting;

    for stimIdx = 1:length(elecStimTimes)
            
        stimLoc = find(stimResampleTimes >= elecStimTimes(stimIdx) & ...
            (stimResampleTimes) <= elecStimTimes(stimIdx) + elecStimDur ...
            );
        stimVector(stimLoc) = 1;
    end


    vert_offset = channels * 1.2;
    plot(stimResampleTimes, stimVector + vert_offset)
    hold on

    % Text label of channel idx 
    text(-1, vert_offset + 0.5, num2str(currElec), 'HorizontalAlignment', 'right');
    % Text label of channel name
    text(stimDataDurS+1, vert_offset + 0.5, num2str(currChannel));

    channels = channels - 1;
end

box off 
yticks([])
t1 = text(-20, 30, 'Electrode ID', "FontSize", 10);
t2 = text(320, 39, 'Channel Index', "FontSize", 10);
t1.Rotation = 90;
t2.Rotation = 270;
xlabel('Time (s)');
set(gcf, 'color', 'white')
set(gca, 'TickDir', 'out')
ax1 = gca();
ax1.YAxis.Visible = 'off'; 

end
