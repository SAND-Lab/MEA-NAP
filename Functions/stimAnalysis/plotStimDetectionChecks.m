function plotStimDetectionChecks(filteredData, stimInfo, expSubFolder, Params)
%PLOTSTIMDETECTIONCHECKS Summary of this function goes here
%   Detailed explanation goes here

%% 1 | Overall stimulation trace 

figName = '1_StimsDetected';
figHandle = figure;
figHandle = plotStimTimes(filteredData, stimInfo, Params, figHandle);
pipelineSaveFig(fullfile(expSubFolder, figName), Params.figExt, Params.fullSVG, figHandle);
close(figHandle)

%% 2 | Stimulation heatmap 

figName = '2_StimsHeatmap';
figHandle = plotStimHeatmap(stimInfo, figHandle);
pipelineSaveFig(fullfile(expSubFolder, figName), Params.figExt, Params.fullSVG, figHandle);
close(figHandle)

%% 3 | Individual Filtered traces 
channelNames = [];
numStimElecs = 0;

for i = 1:length(stimInfo)
    channelNames = [channelNames stimInfo{i}.channelName];
    if stimInfo{i}.pattern > 0
        numStimElecs = numStimElecs + 1;
    end
end

numNoStimTracesToPlot = 5;
stimChannels = [];
nonStimChannels = [];
numPlots = 0;

% list of stimulated electrodes and non stim electrodes
for i = 1:length(stimInfo)
    if isempty(stimInfo{i}.elecStimTimes)
        if (i ~= 15)        % excluding reference electrode from being plotted
            nonStimChannels = [nonStimChannels i];
        end
    else
        stimChannels = [stimChannels i];
    end
end

numStimTracesToPlot = length(stimChannels);

while numPlots < (numNoStimTracesToPlot)
    randomIndex = randi(length(nonStimChannels));

    figName = sprintf('3_NoStimsElectrode_%.f', channelNames(nonStimChannels(randomIndex)));
    figHandle = plotIdvStimDataAndTrace(filteredData, nonStimChannels(randomIndex), stimInfo, Params);
    pipelineSaveFig(fullfile(expSubFolder, figName), Params.figExt, Params.fullSVG, figHandle);
    nonStimChannels(randomIndex) = []; % remove selected channel to avoid repeats
    numPlots = numPlots + 1;
    close(figHandle)

end 

numPlots = 0;   % reset for next plots

while numPlots < (numStimTracesToPlot)
    for stimIndex = 1:length(stimChannels)

        figName = sprintf('3_StimsElectrode_%.f', channelNames(stimChannels(stimIndex)));
        figHandle = plotIdvStimDataAndTrace(filteredData, stimChannels(stimIndex), stimInfo, Params);
        pipelineSaveFig(fullfile(expSubFolder, figName), Params.figExt, Params.fullSVG, figHandle);
        numPlots = numPlots + 1;
        close(figHandle)

    end

end

end

