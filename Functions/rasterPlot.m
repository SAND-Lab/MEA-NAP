function rasterPlot(File,spikeMatrix,Params,spikeFreqMax)

% creata a raster plot of the recording

%% Downsample spike matrix

% sampling frequency
fs = Params.fs;

% duration of the recording
duration_s = length(spikeMatrix)/fs; % in seconds

spikeMatrix = full(spikeMatrix);

% downsample matrix to 1 frame per second
downSpikeMatrix = downSampleSum(spikeMatrix, duration_s);

%% plot the raster

p = [100 100 1500 800];
set(0, 'DefaultFigurePosition', p)
F1 = figure;
tiledlayout(2,1)

nexttile
h = imagesc(downSpikeMatrix');
        
xticks((duration_s)/(duration_s/60):(duration_s)/(duration_s/60):duration_s)
xticklabels({'1','2','3','4','5','6','7','8','9','10','11','12','13','14','15'})

c = parula;c = c(1:round(length(c)*.85),:);
colormap(c);

aesthetics
ylabel('Electrode')
xlabel('Time (min)')
cb = colorbar;
ylabel(cb, 'Firing Rate (Hz)')
cb.TickDirection = 'out';
set(gca,'TickDir','out');
cb.Location = 'Eastoutside';
cb.Box = 'off';
set(gca, 'FontSize', 14)
ylimit_cbar = prctile(downSpikeMatrix(:),99,'all');
caxis([0,ylimit_cbar])
yticks([1, 10:10:60])
title({strcat(regexprep(File,'_','','emptymatch'),' raster scaled to recording'),' '});
ax = gca;
ax.TitleFontSizeMultiplier = 0.7;

nexttile
h = imagesc(downSpikeMatrix');
        
xticks((duration_s)/(duration_s/60):(duration_s)/(duration_s/60):duration_s)
xticklabels({'1','2','3','4','5','6','7','8','9','10','11','12','13','14','15'})

c = parula;c = c(1:round(length(c)*.85),:);
colormap(c);

aesthetics
ylabel('Electrode')
xlabel('Time (min)')
cb = colorbar;
ylabel(cb, 'Firing Rate (Hz)')
cb.TickDirection = 'out';
set(gca,'TickDir','out');
cb.Location = 'Eastoutside';
cb.Box = 'off';
set(gca, 'FontSize', 14)
ylimit_cbar = spikeFreqMax;
caxis([0,ylimit_cbar])
yticks([1, 10:10:60])
title({strcat(regexprep(File,'_','','emptymatch'),' raster scaled to entire data batch'),' '});
ax = gca;
ax.TitleFontSizeMultiplier = 0.7;

%% save the figure

if Params.figMat == 1
    saveas(gcf,'Raster.fig');
end

if Params.figPng == 1
    saveas(gcf,'Raster.png');
end

if Params.figEps == 1
    saveas(gcf,'Raster.eps');
end

close(F1); 

  
end
