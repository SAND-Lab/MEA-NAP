function plotStats(statsTable, plotSaveFolder, Params, oneFigureHandle)
%UNTITLED Summary of this function goes here
%   Detailed explanation goes here


pValThreshold = Params.pValThreshold; 

% find metrics that were specified to be plot in settings
subsetMetrics = intersect(Params.networkLevelNetMetToPlot, statsTable.Metric);
uniqueMetrics = sort(subsetMetrics);
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




%% Square / Circle plot

% make bluewhitecolormap 
bwrRGB = zeros(100, 3);
bwrRGB(1:50, 3) = 1; % linspace(1, 0, 50);
bwrRGB(51:100, 1) = 1; %linspace(0, 1, 50);

dprime_range = linspace(-1.5, 1.5, 100); 

for lagIdx = 1:numLags
    
    lagTable = statsTable(statsTable.Lag == uniqueLags(lagIdx), :);
    
    sigMatrix = zeros(numTest, numMetric);
    pValueMatrix = zeros(numTest, numMetric);
    effectMatrix = zeros(numTest, numMetric) + nan;

    for testIdx = 1:numTest
        
        testTable = lagTable(ismember(lagTable.Test, uniqueTests{testIdx}) & ...
            ismember(lagTable.('Test-statistic'), 'P-value'), :);
        subsetIdx = find(ismember(testTable.Metric, subsetMetrics));
        testTable = testTable(subsetIdx, :);
        testTable = sortrows(testTable, 'Metric');
        
        sigMatrix(testIdx, :) = testTable.Value < pValThreshold;
        pValueMatrix(testIdx, :) = testTable.Value;
        
        effectTable = lagTable(ismember(lagTable.Test, uniqueTests{testIdx}) & ...
            ismember(lagTable.('Test-statistic'), 'd-prime'), :);
        if size(effectTable, 1) > 1 
            effectMatrix(testIdx, :) = effectTable.Value;
        end
    end 
    
    % Circle plot 
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
    
    numTest = size(pValueMatrix, 1);
    numMetric = size(pValueMatrix, 2);
    
    maxDotSize = 500;
    maxLogPval = -log10(0.0001); % ie. a threshold of p < 0.0001
    minLogPval = 0; % implicit
    
    for testIdx = 1:numTest 
        for metricIdx = 1:numMetric 
            pVal = pValueMatrix(testIdx, metricIdx);
            if ~isnan(pVal) && (pVal < 1)
                logPVal = -log10(pVal);
                logPVal = min(logPVal, maxLogPval);
                dotSize = logPVal / maxLogPval * maxDotSize;
                if pVal < pValThreshold
                    dprime = effectMatrix(testIdx, metricIdx);
                    if isnan(dprime)
                        dprime_color = [0, 0, 0];
                        dprime_alpha = 1;
                    else
                        [~, dprime_color_idx] = min(abs(dprime_range - dprime));
                        dprime_color = bwrRGB(dprime_color_idx, :);
                        dprime_alpha = abs(length(dprime_range)/2 - dprime_color_idx) / length(dprime_range)/2;
                    end
                    scatter(metricIdx, testIdx, dotSize, 'filled', ...
                        'MarkerFaceColor', dprime_color, 'MarkerFaceAlpha', dprime_alpha, ...
                        'MarkerEdgeColor', 'black');
                else 
                    scatter(metricIdx, testIdx, dotSize, 'MarkerFaceColor', 'white', 'MarkerEdgeColor', 'black')
                end
                hold on
            end
        end 
    end
    
    % Axis labels
    xticks(1:numMetric);
    xticklabels(uniqueMetricLabels);     % xticklabels(uniqueMetrics);
    yticks(1:numTest);
    yaxisproperties= get(gca, 'YAxis');
    yaxisproperties.TickLabelInterpreter = 'none'; 
    yticklabels(uniqueTests);
    xlim([0, numMetric + 3]);
    ylim([0, numTest + 0.5])
    
    % add legend 
    log3dotSize = 3 / maxLogPval * maxDotSize;
    scatter(numMetric + 1.5, numTest - 1.5, log3dotSize, 'filled', 'MarkerFaceColor', 'black')
    text(numMetric + 2, numTest - 1.5, 'p = 0.001', 'color', [0, 0, 0]) 
    
    log2dotSize = 2 / maxLogPval * maxDotSize;
    scatter(numMetric + 1.5, numTest - 2.5, log2dotSize, 'filled', 'MarkerFaceColor', 'black')
    text(numMetric + 2, numTest - 2.5, 'p = 0.01', 'color', [0, 0, 0])
    set(gcf, 'color', 'white')
    
    log1dotSize = 1 / maxLogPval * maxDotSize;
    scatter(numMetric + 1.5, numTest - 3.5, log1dotSize, 'filled', 'MarkerFaceColor', 'white', 'MarkerEdgeColor', 'black')
    text(numMetric + 2, numTest - 3.5, 'p = 0.1', 'color', [0, 0, 0])
    set(gcf, 'color', 'white')
    
    % Add colorbar 
    cbar_ax = axes('Position',[0.86 0.2 0.025 0.4]);
    bwrRGB_img = repmat(bwrRGB, [1, 1, 100]);
    bwrRGB_img = permute(bwrRGB_img, [1 3 2]);
    im = image(flipud(bwrRGB_img));
    alpha_mask = repmat(abs(linspace(-1, 1, 100)), [100, 1])';
    im.AlphaData = alpha_mask;
    
    cbar_ax.XAxis.Visible = 'off';
    cbar_ax.XTick([]);
    ylabel('D prime');
    set(cbar_ax,'YAxisLocation','right');
    set(cbar_ax, 'box', 'off');
    set(cbar_ax, 'TickDir','out');
    yticks([1, 50, 100])
    yticklabels([1.5, 0, -1.5])
    
    % Square Plot
    %{
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
    %}

    % figName = fullfile(plotSaveFolder, sprintf('sig_table_%.fms_lag, p < %.4f', ...
    %      uniqueLags(lagIdx), pValThreshold));
    figName = fullfile(plotSaveFolder, sprintf('1_sig_table_%.fms_lag', uniqueLags(lagIdx)));

    pipelineSaveFig(figName, Params.figExt, Params.fullSVG, oneFigureHandle)
    close all 


end 






end