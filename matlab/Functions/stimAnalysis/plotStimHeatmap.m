function figHandle = plotStimHeatmap(stimInfo, figHandle)
%PLOTSTIMHEATMAP Summary of this function goes here
%   Detailed explanation goes here

if ~exist('figHandle', 'var') 
    figHandle = figure();
elseif ~isgraphics(figHandle)
    figHandle = figure();
end 

p = [100 100 600 600];
set(figHandle, 'Position', p);

numNodes = length(stimInfo);

nodeScaleF = 1;

for nodeIdx = 1:numNodes
    xc = stimInfo{nodeIdx}.coords(1);
    yc = stimInfo{nodeIdx}.coords(2);
    circlePos =  [xc - (0.5*nodeScaleF), yc - (0.5*nodeScaleF), nodeScaleF, nodeScaleF];

    if length(stimInfo{nodeIdx}.elecStimTimes) == 0
        nodeColor = 'white';
        rectangle('Position', circlePos,'Curvature',[1 1],'FaceColor',nodeColor,'EdgeColor','black','LineWidth', 1) 
    else 
        nodeColor = 'black';
        rectangle('Position', circlePos,'Curvature',[1 1],'FaceColor',nodeColor,'EdgeColor','red','LineWidth', 1.5)
        text(xc - (0.1*nodeScaleF), yc, num2str(stimInfo{nodeIdx}.pattern), 'Color', 'white', 'FontSize', 12);
    end
end

axis off

end

