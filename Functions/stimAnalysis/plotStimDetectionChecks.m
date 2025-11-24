function plotStimDetectionChecks(filteredData, stimInfo, expSubFolder, Params)
%PLOTSTIMDETECTIONCHECKS Summary of this function goes here
%   Detailed explanation goes here

%% 1 | Individual Filtered traces 
numNoStimTraceToPlot = 5; 
numStimTraceToPlot = 5;

numNoStimTracePlotted = 0;
numStimTracePlotted = 0;

channelNames = [];

for i = 1:length(stimInfo)
    channelNames = [channelNames stimInfo{i}.channelName];
end

for elecIndex = 1:length(stimInfo)
    
    elecStimTimes = stimInfo{elecIndex}.elecStimTimes;

    if isempty(elecStimTimes)
        if numNoStimTracePlotted <= numNoStimTraceToPlot
             figName = sprintf('3_NoStimsElectrode_%.f', channelNames(elecIndex));
            figHandle = plotIdvStimDataAndTrace(filteredData, elecIndex, stimInfo, Params); 
            pipelineSaveFig(fullfile(expSubFolder, figName), Params.figExt, Params.fullSVG, figHandle);
            numNoStimTracePlotted = numNoStimTracePlotted + 1;
            close(figHandle)
        end
    else 
        if numStimTracePlotted <= numStimTraceToPlot
            figName = sprintf('3_StimsElectrode_%.f', channelNames(elecIndex));
            figHandle = plotIdvStimDataAndTrace(filteredData, elecIndex, stimInfo, Params); 
            pipelineSaveFig(fullfile(expSubFolder, figName), Params.figExt, Params.fullSVG, figHandle);
            numStimTracePlotted = numStimTracePlotted + 1;
            close(figHandle)
        end
    end

end


%% 2 | Overall stimulation trace 

figName = '1_StimsDetected';
figHandle = plotStimTimes(filteredData, stimInfo, Params, figHandle);
pipelineSaveFig(fullfile(expSubFolder, figName), Params.figExt, Params.fullSVG, figHandle);
close(figHandle)



%% 3 | Stimulation heatmap 

figName = '2_StimsHeatmap';
figHandle = plotStimHeatmap(stimInfo, figHandle);
pipelineSaveFig(fullfile(expSubFolder, figName), Params.figExt, Params.fullSVG, figHandle);
close(figHandle)



end

