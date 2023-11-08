function plotStats(statsTable, plotSaveFolder, Params, oneFigureHandle)
%UNTITLED Summary of this function goes here
%   Detailed explanation goes here


pValThreshold = Params.pValThreshold; 

uniqueMetrics = sort(unique(statsTable.Metric));
uniqueTests = unique(statsTable.Test);
uniqueLags = unique(statsTable.Lag);

numTest = length(uniqueTests);
numMetric = length(uniqueMetrics);
numLags = length(uniqueLags);

% get metric full name 
uniqueMetricLabels = {};
for metricIdx = 1:length(uniqueMetrics)
    metricLoc = find(contains(Params.networkLevelNetMetToPlot, uniqueMetrics{metricIdx}));
    
    if isempty(metricLoc)
        labelText = uniqueMetrics{metricIdx};
    else 
        labelText = Params.networkLevelNetMetLabels{metricLoc};
    end 

    uniqueMetricLabels{end+1} = labelText;
end 


for lagIdx = 1:numLags
    
    lagTable = statsTable(statsTable.Lag == uniqueLags(lagIdx), :);
    
    sigMatrix = zeros(numTest, numMetric);

    for testIdx = 1:numTest
        
        testTable = lagTable(ismember(lagTable.Test, uniqueTests{testIdx}) & ...
            ismember(lagTable.('Test-statistic'), 'P-value'), :);
        testTable = sortrows(testTable, 'Metric');
        
        sigMatrix(testIdx, :) = testTable.Value < pValThreshold;

    end 
    
    plotWidth = length(uniqueMetricLabels) * 90;
    plotHeight = numTest * 75;
    p = [100 100 plotWidth plotHeight]; 

    if Params.showOneFig 
         % Make it so figure handle in oneFigure don't appear
         set(0, 'DefaultFigureVisible', 'off')
    end 
    
    if Params.showOneFig
        if isgraphics(oneFigureHandle)
            set(oneFigureHandle, 'Position', p);
        else 
            oneFigureHandle = figure;
            set(oneFigureHandle, 'Position', p);
        end 
    else
        figure
        set(gcf, 'Position', p);
    end 
    

    colormap gray
    imagesc(1 - sigMatrix)  % either 1 - sigMatrix or reverse colormap
    xticks(1:numMetric);
    xticklabels(uniqueMetricLabels);     % xticklabels(uniqueMetrics);
    yticks(1:numTest);
    yaxisproperties= get(gca, 'YAxis');
    yaxisproperties.TickLabelInterpreter = 'none'; 
    yticklabels(uniqueTests);
    set(gcf, 'color', 'w')
    title(sprintf('Lag %.f ms, p < %.4f', uniqueLags(lagIdx), pValThreshold))
    
    % TODO: add a black square to show that means p < threshold 
    % hold on
    ax = gca; ax.Clipping = 'off';
    ax.XAxis.TickLength = [0 0];
    ax.YAxis.TickLength = [0 0];
    custom_colormap = [0 0 0; 1 1 1];
    colormap(custom_colormap);
    colorbar('Ticks', 0:1, 'TickLabels', {sprintf('p < %.4f', pValThreshold), 'n.s.'});
    % rectangle('Position', [length(uniqueMetricLabels) + 1, numTest * 0.5, 1, 1]);


    % figName = fullfile(plotSaveFolder, sprintf('sig_table_%.fms_lag, p < %.4f', ...
    %      uniqueLags(lagIdx), pValThreshold));
    figName = fullfile(plotSaveFolder, sprintf('sig_table_%.fms_lag', uniqueLags(lagIdx)));

    pipelineSaveFig(figName, Params.figExt, Params.fullSVG, oneFigureHandle)
    close all 


end 






end