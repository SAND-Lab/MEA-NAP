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
duration_s = size(spikeMatrix, 1) / fs; % in seconds
numChannels = size(spikeMatrix, 2);
if Params.suite2pMode == 0 
    % Resampling spike data
    spikeMatrix = full(spikeMatrix);
    % downsample matrix to 1 frame per second
    downSpikeMatrix = downSampleSum(spikeMatrix, duration_s);
else 
    timesToInterpolate = 1:floor(duration_s);
    newSampleCount = length(timesToInterpolate);
    if strcmp(Params.twopActivity, 'peaks')
        downSpikeMatrix = spikeMatrix;
    else
        originalTimes = linspace(1, duration_s, size(spikeMatrix, 1));
        downSpikeMatrix = zeros(newSampleCount, numChannels);
        for channel_idx = 1:numChannels 
            downSpikeMatrix(:, channel_idx) = interp1(originalTimes, spikeMatrix(:, channel_idx), timesToInterpolate);
        end
    end 
end



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

sec_in_min = 60;
duration_min = duration_s / sec_in_min;
xticklabel_txt = 1:floor(duration_min);
xticks(sec_in_min:sec_in_min:duration_s)
xticklabels(xticklabel_txt);

c = parula;
c = c(1:round(length(c)*.85),:);
colormap(c);

if Params.suite2pMode 
   ylabel_txt = 'Unit';
   cbar_label = 'Activity';
else 
   ylabel_txt = 'Electrode';
   cbar_label = 'Firing Rate (Hz)';
end

numYticks = min([max([numChannels, 1]), 7]);
ytickValues = linspace(1, max([numChannels, numYticks]), numYticks);
ytickValues = round(ytickValues);

aesthetics
ylabel(ylabel_txt)
xlabel('Time (min)')
cb = colorbar;
ylabel(cb, cbar_label)
cb.TickDirection = 'out';
set(gca,'TickDir','out');
cb.Location = 'Eastoutside';
cb.Box = 'off';
set(gca, 'FontSize', 14)
ylimit_cbar = prctile(downSpikeMatrix(:),Params.rasterPlotUpperPercentile,'all');
ylimit_cbar = max([ylimit_cbar, 1]);  % ensures it is minimum of 1

caxis([0,ylimit_cbar])
yticks(ytickValues)
title({strcat(regexprep(File,'_','','emptymatch'),' raster scaled to recording'),' '});
ax = gca;
ax.TitleFontSizeMultiplier = 0.7;

nexttile
h = imagesc(downSpikeMatrix');
        
xticks((duration_s)/(duration_s/60):(duration_s)/(duration_s/60):duration_s)
xticklabels(xticklabel_txt)

if strcmp(Params.rasterColormap, 'parula')
    c = parula;c = c(1:round(length(c)*.85),:);
    colormap(c);
elseif strcmp(Params.rasterColormap, 'gray')
   colormap(flipud(gray))  
end

aesthetics
ylabel(ylabel_txt)
xlabel('Time (min)')
cb = colorbar;
ylabel(cb, cbar_label)
cb.TickDirection = 'out';
set(gca,'TickDir','out');
cb.Location = 'Eastoutside';
cb.Box = 'off';
set(gca, 'FontSize', 14)
ylimit_cbar = spikeFreqMax;
ylimit_cbar = max([ylimit_cbar, 1]);  % ensures it is minimum of 1
caxis([0,ylimit_cbar])
yticks(ytickValues)
title({strcat(regexprep(File,'_','','emptymatch'),' raster scaled to entire data batch'),' '});
ax = gca;
ax.TitleFontSizeMultiplier = 0.7;

%% save the figure
figName = '3_Raster';
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
