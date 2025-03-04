function plotStimDetectionChecks(filteredData, stimInfo, expSubFolder, Params)
%PLOTSTIMDETECTIONCHECKS Summary of this function goes here
%   Detailed explanation goes here

%% 1 | Individual Filtered traces 
numNoStimTraceToPlot = 5; 
numStimTraceToPlot = 5;

numNoStimTracePlotted = 0;
numStimTracePlotted = 0;


for elecIndex = 1:length(stimInfo)
    
    elecStimTimes = stimInfo{elecIndex}.elecStimTimes;

    if isempty(elecStimTimes)
        if numNoStimTracePlotted <= numNoStimTraceToPlot
            figName = sprintf('1_noStimElec_%.f', elecIndex);
            figHandle = plotIdvStimDataAndTrace(filteredData, elecIndex, stimInfo, Params); 
            pipelineSaveFig(fullfile(expSubFolder, figName), Params.figExt, Params.fullSVG, figHandle);
            numNoStimTracePlotted = numNoStimTracePlotted + 1;
            close(figHandle)
        end
    else 
        if numStimTracePlotted <= numStimTraceToPlot
            figName = sprintf('1_stimElec_%.f', elecIndex);
            figHandle = plotIdvStimDataAndTrace(filteredData, elecIndex, stimInfo, Params); 
            pipelineSaveFig(fullfile(expSubFolder, figName), Params.figExt, Params.fullSVG, figHandle);
            numStimTracePlotted = numStimTracePlotted + 1;
            close(figHandle)
        end
    end

end


%% 2 | Overall stimulation trace 

figName = '2_overall_stimulation_trace';
figHandle = plotStimTimes(filteredData, stimInfo, Params, figHandle);
pipelineSaveFig(fullfile(expSubFolder, figName), Params.figExt, Params.fullSVG, figHandle);
close(figHandle)



%% 3 | Stimulation heatmap 

figName = '3_stimulation_heatmap'; 
figHandle = plotStimHeatmap(stimInfo, figHandle);
pipelineSaveFig(fullfile(expSubFolder, figName), Params.figExt, Params.fullSVG, figHandle);
close(figHandle)



end

