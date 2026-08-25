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
    pValMatrix = zeros(numTest, numMetric);
    effectMatrix = zeros(numTest, numMetric);

    for testIdx = 1:numTest
        
        testTable = lagTable(ismember(lagTable.Test, uniqueTests{testIdx}) & ...
            ismember(lagTable.('Test-statistic'), 'P-value'), :);
        testTable = sortrows(testTable, 'Metric');
        
        sigMatrix(testIdx, :) = testTable.Value < pValThreshold;
        pValMatrix(testIdx, :) = testTable.Value;

        % TODO: fill in effect matrix with the direction of the difference
        % if any
        slopeTable = lagTable(ismember(lagTable.Test, uniqueTests{testIdx}) & ...
            ismember(lagTable.('Test-statistic'), 'slope'), :);
        slopeTable = sortrows(slopeTable, 'Metric');
        effectMatrix(testIdx, :) = slopeTable.Value;

    end 
    
    plotWidth = length(uniqueMetricLabels) * 50;
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
    end 
    
    if Params.usePvalColormap && Params.usePvalDirection
        colormap(brewermap([], '-RdBu'))
        pValMatrixLog10 = abs(log10(pValMatrix));
        % threshold the log10 values
        pValMatrixLog10(pValMatrix > Params.pValThreshold) = 0;
        effectSignMatrix = sign(effectMatrix) .* pValMatrixLog10;
        maxAbsEffectsize = max(abs(effectSignMatrix(:)));
        imagesc(effectSignMatrix, [-5, 5]) % make sure 0 is center
        cbar = colorbar('XTick', [-5, -2, 0, 2, 5], ...
                        'XTickLabel', {'p < 10^{-5}', 'p = 0.01', 'NS', 'p = 0.01', 'p < 10^{-5}'}); 
        
        annotation('textarrow', [0.93, 0.93], [0.72, 0.72], 'Units', 'normalized', ...
            'String', 'Increasing', 'TextRotation', 270, 'HeadStyle', 'none', 'LineStyle', 'none', 'color', 'red')

        annotation('textarrow', [0.93, 0.93], [0.43, 0.43], 'Units', 'normalized', ...
            'String', 'Decreasing', 'TextRotation', 270, 'HeadStyle', 'none', 'LineStyle', 'none', 'color', 'blue')

        
    elseif Params.usePvalColormap
        colormap gray
        imagesc(log10(pValMatrix))
        cbar = colorbar; 
    else
        colormap gray
        imagesc(1 - sigMatrix)  % either 1 - sigMatrix or reverse colormap
    end 

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
    % ax = gca; ax.Clipping = 'off';
    % rectangle('Position', [length(uniqueMetricLabels) * 1.5, numTest * 0.5, 10, 10]);


    figName = fullfile(plotSaveFolder, sprintf('sig_table_%.fms_lag, p < %.4f', ...
        uniqueLags(lagIdx), pValThreshold));

    pipelineSaveFig(figName, Params.figExts, Params.fullSVG, oneFigureHandle)
    close all 


end 






end