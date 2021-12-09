function electrodeHeatMaps(FN,spikeMatrix,channels,spikeFreqMax,Params)

%% create channels variable if it doesn't exist
if ~exist('channels')
       channels = [47,48,46,45,38,37,28,36,27,17,26,16,35,25,15,14,24,34,13,23,12,22,33,21,32,31,44,43,41,42,52,51,53,54,61,62,71,63,72,82,73,83,64,74,84,85,75,65,86,76,87,77,66,78,67,68,55,56,58,57];
end

%% plot

F1 = figure;
F1.OuterPosition = [50 100 1150 570];
tiledlayout(1,2)
aesthetics; axis off; hold on

%% coordinates

coords(:,1) = floor(channels/10);
coords(:,2) = channels - coords(:,1)*10;
xc = coords(:,1);
yc = coords(:,2);

%% calculate spiking frequency

spikeCount = sum(spikeMatrix); 
spikeCount = full(spikeCount / (size(spikeMatrix, 1) / 25000));

%% plot electrodes

mycolours = colormap;

nexttile
uniqueXc = sort(unique(xc));
nodeScaleF = (uniqueXc(2)-uniqueXc(1))*2/3;
for i = 1:length(spikeCount)
    pos = [xc(i)-(0.5*nodeScaleF) yc(i)-(0.5*nodeScaleF) nodeScaleF nodeScaleF];
        try
            rectangle('Position',pos,'Curvature',[1 1],'FaceColor',mycolours(ceil(length(mycolours)*((spikeCount(i)-min(spikeCount))/(prctile(spikeCount,99,'all')-min(spikeCount)))),1:3),'EdgeColor','w','LineWidth',0.1) 
        catch
            if (spikeCount(i)-min(spikeCount))/(prctile(spikeCount,95,'all')-min(spikeCount)) == 0
                rectangle('Position',pos,'Curvature',[1 1],'FaceColor',mycolours(ceil(length(mycolours)*((spikeCount(i)-min(spikeCount))/(prctile(spikeCount,99,'all')-min(spikeCount)))+0.00001),1:3),'EdgeColor','w','LineWidth',0.1)
            else
                 rectangle('Position',pos,'Curvature',[1 1],'FaceColor',mycolours(length(mycolours),1:3),'EdgeColor','w','LineWidth',0.1) 
            end
        end
end
ylim([min(yc)-1 max(yc)+1])
xlim([min(xc)-1 max(xc)+1])
axis off

cb = colorbar;
cb.Box = 'off';
cb.Ticks = [0 0.2 0.4 0.6 0.8 1];
cb.TickLabels = {num2str(min(spikeCount)), num2str(round(1/5*prctile(spikeCount,99,'all'),2)), num2str(round(2/5*prctile(spikeCount,99,'all'),2)), num2str(round(3/5*prctile(spikeCount,99,'all'),2)), num2str(round(4/5*prctile(spikeCount,99,'all'),2)), num2str(round(prctile(spikeCount,99,'all'),2))};
cb.TickDirection = 'out';
cb.Label.String = 'mean firing rate (Hz)';
title({strcat(regexprep(FN,'_','','emptymatch'),' Electrode heatmap scaled to recording'),' '});

nexttile
uniqueXc = sort(unique(xc));
nodeScaleF = (uniqueXc(2)-uniqueXc(1))*2/3;
for i = 1:length(spikeCount)
    pos = [xc(i)-(0.5*nodeScaleF) yc(i)-(0.5*nodeScaleF) nodeScaleF nodeScaleF];
        try
            rectangle('Position',pos,'Curvature',[1 1],'FaceColor',mycolours(ceil(length(mycolours)*((spikeCount(i)-min(spikeCount))/(spikeFreqMax-min(spikeCount)))),1:3),'EdgeColor','w','LineWidth',0.1)
        catch
            if (spikeCount(i)-min(spikeCount))/(spikeFreqMax-min(spikeCount)) == 0
                rectangle('Position',pos,'Curvature',[1 1],'FaceColor',mycolours(ceil(length(mycolours)*((spikeCount(i)-min(spikeCount))/(spikeFreqMax-min(spikeCount)))+0.00001),1:3),'EdgeColor','w','LineWidth',0.1)
            else
                 rectangle('Position',pos,'Curvature',[1 1],'FaceColor',mycolours(length(mycolours),1:3),'EdgeColor','w','LineWidth',0.1) 
            end
        end
end
ylim([min(yc)-1 max(yc)+1])
xlim([min(xc)-1 max(xc)+1])
axis off

cb = colorbar;
cb.Box = 'off';
cb.Ticks = [0 0.2 0.4 0.6 0.8 1];
cb.TickLabels = {num2str(min(spikeCount)), num2str(round(1/5*spikeFreqMax,2)), num2str(round(2/5*spikeFreqMax,2)), num2str(round(3/5*spikeFreqMax,2)), num2str(round(4/5*spikeFreqMax,2)), num2str(round(spikeFreqMax,2))};
cb.TickDirection = 'out';
cb.Label.String = 'mean firing rate (Hz)';
title({strcat(regexprep(FN,'_','','emptymatch'),' Electrode heatmap scaled to entire data batch'),' '});




% save figure
if Params.figMat == 1
    saveas(gcf,'heatmap.fig');
end
if Params.figPng == 1
    saveas(gcf,'heatmap.png');
end
if Params.figEps == 1
    saveas(gcf,'heatmap.eps');
end

close all;

end