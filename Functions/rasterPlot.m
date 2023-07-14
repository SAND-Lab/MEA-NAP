function rasterPlot(File,spikeMatrix,Params,spikeFreqMax, figFolder, oneFigureHandle)
% creata a raster plot of the recording
% Parameters 
% -----------
% File : char 
% spikeMatrix : matrix 
% Params : structure 
% spikeFreqMax : float 
% figFolder : path to directory 
%     absolute path to folder to save the raster plot

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

if Params.showOneFig
    if isgraphics(oneFigureHandle)
        set(oneFigureHandle, 'Position', p);
    else 
        oneFigureHandle = figure;
        set(oneFigureHandle, 'Position', p);
    end 
else 
    F1 = figure;
end 

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
ylimit_cbar = prctile(downSpikeMatrix(:),Params.rasterPlotUpperPercentile,'all');
ylimit_cbar = max([ylimit_cbar, 1]);  % ensures it is minimum of 1

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
ylimit_cbar = max([ylimit_cbar, 1]);  % ensures it is minimum of 1
caxis([0,ylimit_cbar])
yticks([1, 10:10:60])
title({strcat(regexprep(File,'_','','emptymatch'),' raster scaled to entire data batch'),' '});
ax = gca;
ax.TitleFontSizeMultiplier = 0.7;

%% save the figure
figName = 'Raster';
figPath = fullfile(figFolder, figName);

if Params.showOneFig
    pipelineSaveFig(figPath, Params.figExt, Params.fullSVG, oneFigureHandle);
else
    pipelineSaveFig(figPath, Params.figExt, Params.fullSVG)
end 

if Params.showOneFig
    clf(oneFigureHandle)
else 
    close(F1);
end 

  
end
