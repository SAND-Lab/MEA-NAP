function figHandle = plotStimHeatmapWmetric(nodeMetric, vrange, cmap, cmapLabel, stimInfo, patternID, figHandle)
%PLOTSTIMHEATMAP Summary of this function goes here
%   Detailed explanation goes here

if ~exist('figHandle', 'var') 
    figHandle = figure();
elseif ~isgraphics(figHandle)
    figHandle = figure();
end 

p = [100 100 700 600];
set(figHandle, 'Position', p);

numNodes = length(stimInfo);

nodeScaleF = 1;

for nodeIdx = 1:numNodes
    xc = stimInfo{nodeIdx}.coords(1);
    yc = stimInfo{nodeIdx}.coords(2);
    circlePos =  [xc - (0.5*nodeScaleF), yc - (0.5*nodeScaleF), nodeScaleF, nodeScaleF];

    if (length(stimInfo{nodeIdx}.elecStimTimes) > 0) & ismember(stimInfo{nodeIdx}.pattern, patternID) 
        nodeColor = 'white'; % [0.5, 0.5, 0.5];
    else 
        % nodeColor = 'black';
        nodeColor = valuesToColormap(nodeMetric(nodeIdx), cmap, vrange(1), vrange(2));
    end
    rectangle('Position', circlePos,'Curvature',[1 1],'FaceColor',nodeColor,'EdgeColor','black','LineWidth', 1) 
end

% colorbar 
colormap(cmap);
cb = colorbar();
clim(vrange);
ylabel(cb, cmapLabel, 'FontSize', 12);

% remove ticks and axis 
axis off 

set(gcf, 'color', 'w')

end

