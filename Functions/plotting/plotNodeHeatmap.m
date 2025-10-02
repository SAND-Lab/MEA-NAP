function plotNodeHeatmap(FN, Ephys, channels, maxVal, Params, coords, ...
    metricVarName, metricLabel, cmap, useLogScale, figFolder, figName, oneFigureHandle, subsetChannelName)
%PLOTNODEHEATMAP Summary of this function goes here
%   Detailed explanation goes here

% subsetChannelName : not impelemented yet, but the idea is to allow
% plotting a subset of available channels
%% plot
p = [50 100 1150 570];

if Params.showOneFig
    if isgraphics(oneFigureHandle)
        set(oneFigureHandle, 'OuterPosition', p);
    else 
        oneFigureHandle = figure;
        set(oneFigureHandle, 'OuterPosition', p);
    end 
else 
    F1 = figure;
    F1.OuterPosition = p;
end 

tiledlayout(1,2)
aesthetics; axis off; hold on

%% coordinates

% Perform transpose if not column vector 
if size(channels, 1) == 1
    channels = channels'; 
end 

xc = coords(:, 1);
yc = coords(:, 2); 

%% Assign metric variable 

metricVals = Ephys.(metricVarName);

if useLogScale == 1
    metricVals = log10(metricVals);
    maxVal = log10(maxVal);
end

%% plot electrodes
% TODO: I think a lot of rectangle coloring can be simplified
numCbarTicks = 5;

%% NaN color handling 
NaNColor = [0.8, 0.8, 0.8]; % grey 

%% Left electrode plot (scaled to individual recording)


nexttile
uniqueXc = sort(unique(xc));
nodeScaleF = 2/3; 

makeMinSpikeCountZero = 1;

if makeMinSpikeCountZero == 1
    minSpikeCountToPlot = 0;
else 
    minSpikeCountToPlot = min(spikeCount);
end 

numChannels = length(channels);
for i = 1:numChannels

    pos = [xc(i)-(0.5*nodeScaleF) yc(i)-(0.5*nodeScaleF) nodeScaleF nodeScaleF];
        try
            if isnan(metricVals(i))
                colorToUse = NaNColor;
            else
                colorToUse = cmap(ceil(length(cmap) * ((metricVals(i) - minSpikeCountToPlot)/(prctile(metricVals,99,'all')-minSpikeCountToPlot))),1:3);
            end 
            rectangle('Position',pos,'Curvature',[1 1],'FaceColor',colorToUse,'EdgeColor','w','LineWidth',0.1) 
        catch
            if (metricVals(i) - minSpikeCountToPlot) / (prctile(metricVals,95,'all') - minSpikeCountToPlot) == 0
                rectangle('Position',pos,'Curvature',[1 1],'FaceColor', ...
                    cmap(ceil(length(cmap)*((metricVals(i)- minSpikeCountToPlot)/(prctile(metricVals,99,'all')-minSpikeCountToPlot))+0.00001),1:3),'EdgeColor','w','LineWidth',0.1)
            else
                rectangle('Position',pos,'Curvature',[1 1],'FaceColor',cmap(length(cmap),1:3),'EdgeColor','w','LineWidth',0.1) 
            end
        end
    if Params.includeChannelNumberInPlots 
        text(pos(1) + 0.5 * nodeScaleF, pos(2) + 0.5 * nodeScaleF, ...
            sprintf('%.f', channels(i)), 'HorizontalAlignment','center')
    end 
end
ylim([min(yc) - 1, max(yc) + 1])
xlim([min(xc) - 1, max(xc) + 1])

if prctile(metricVals,99,'all') <= minSpikeCountToPlot
    cAxisMaxVal = minSpikeCountToPlot + 1;
elseif isnan(prctile(metricVals,99,'all'))
    cAxisMaxVal = minSpikeCountToPlot + 1;
else 
    cAxisMaxVal = prctile(metricVals,99,'all');
end

axis off
colormap(cmap);
caxis([minSpikeCountToPlot, cAxisMaxVal]);
cb = colorbar;

cb.Box = 'off';

cb.Ticks = linspace(0, cAxisMaxVal, numCbarTicks);

tickLabels = cell(numCbarTicks, 1);
for nTick = 1:numCbarTicks
    if nTick == 1
        tickLabels{nTick} = num2str(minSpikeCountToPlot);
    else
        if useLogScale == 1
             valLogScale = nTick / numCbarTicks * cAxisMaxVal;
             numberToPlot = round(10.^valLogScale, 2);
             tickLabels{nTick} = num2str(numberToPlot);
        else
            tickLabels{nTick} = num2str(round(nTick / numCbarTicks * cAxisMaxVal,2));
        end 
    end 
end 

cb.TickLabels = tickLabels;


cb.TickDirection = 'out';
cb.Label.String = metricLabel;
title({strcat(regexprep(FN,'_','','emptymatch'),' Electrode heatmap scaled to recording'),' '});

%% Right electrode plot (scaled to all recordings)

% do some sanity check for this maxVal to be used 
if maxVal <= minSpikeCountToPlot
    maxVal = minSpikeCountToPlot + 1;
elseif isnan(maxVal)
    maxVal = minSpikeCountToPlot + 1;
end


nexttile
for i = 1:numChannels
    pos = [xc(i)-(0.5*nodeScaleF) yc(i)-(0.5*nodeScaleF) nodeScaleF nodeScaleF];
        try
            if isnan(metricVals(i))
                colorToUse = NaNColor;
            else
                colorToUse = cmap(ceil(length(cmap)*((metricVals(i) - minSpikeCountToPlot) / (maxVal-minSpikeCountToPlot))),1:3);
            end 
            rectangle('Position', pos, 'Curvature', [1 1], 'FaceColor', ...
                colorToUse,'EdgeColor','w','LineWidth',0.1)
       catch
            if (metricVals(i)-minSpikeCountToPlot)/(maxVal - minSpikeCountToPlot) == 0
                rectangle('Position',pos,'Curvature',[1 1],'FaceColor', ...
                    cmap(ceil(length(cmap)*((metricVals(i) - minSpikeCountToPlot) / (maxVal-minSpikeCountToPlot))+0.00001),1:3),'EdgeColor','w','LineWidth',0.1)
            else
                 rectangle('Position',pos,'Curvature',[1 1],'FaceColor',cmap(length(cmap),1:3),'EdgeColor','w','LineWidth',0.1) 
            end
        end
end
ylim([min(yc)-1 max(yc)+1])
xlim([min(xc)-1 max(xc)+1])
axis off

colormap(cmap);
caxis([minSpikeCountToPlot, maxVal]);
cb = colorbar;
cb.Box = 'off';
cb.Ticks = linspace(0, maxVal, numCbarTicks);

tickLabels = cell(numCbarTicks, 1);
for nTick = 1:numCbarTicks
    if nTick == 1
        tickLabels{nTick} = num2str(minSpikeCountToPlot);
    else 
        if useLogScale == 1
             valLogScale = nTick / numCbarTicks * maxVal;
             numberToPlot = round(10.^valLogScale, 2);
             tickLabels{nTick} = num2str(numberToPlot);
        else
            tickLabels{nTick} = num2str(round(nTick / numCbarTicks * maxVal, 2));
        end 
    end 
end 

cb.TickLabels = tickLabels;
cb.TickDirection = 'out';
cb.Label.String = metricLabel;
title({strcat(regexprep(FN,'_','','emptymatch'),' Electrode heatmap scaled to entire data batch'),' '});

% save figure
figPath = fullfile(figFolder, figName);

if Params.showOneFig
    pipelineSaveFig(figPath, Params.figExt, Params.fullSVG, oneFigureHandle);
else
    pipelineSaveFig(figPath, Params.figExt, Params.fullSVG)
end 

if Params.showOneFig
    clf(oneFigureHandle, 'reset')
else 
    close(F1);
end 


end

