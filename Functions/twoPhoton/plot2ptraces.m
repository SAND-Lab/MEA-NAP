function plot2ptraces(suite2pFolder, Params, fileName, figFolder, oneFigureHandle)
%PLOT2PTRACES Summary of this function goes here
%   Detailed explanation goes here

%% Set up figure 
p =  [50 100 700 550];

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

aesthetics;

%% Read data

Fpath = fullfile(suite2pFolder, 'F.npy');
FdenoisedPath = fullfile(suite2pFolder, 'Fdenoised.npy');
peakPath = fullfile(suite2pFolder, 'peakStartFrames.npy');
iscellFpath = fullfile(suite2pFolder, 'iscell.npy');
iscell = readNPY(iscellFpath);
iscell_indices = find(iscell(:, 1));

F = readNPY(Fpath);
Fdenoised = readNPY(FdenoisedPath);
peakStartFrames = readNPY(peakPath);

if strcmp(Params.num2ptraces, 'all')
    cell_indices = iscell_indices;
else 
    num_rand_cell = min([str2double(Params.num2ptraces), length(iscell_indices)]);
    cell_indices = randsample(iscell_indices, num_rand_cell);
end 

%% Do plotting
LineWidth = 1.5;

for cell_to_plot = 1:length(cell_indices)
    cell_idx = cell_indices(cell_to_plot);
    peakStartFrames_cell = peakStartFrames(cell_idx, :);
    peakStartFrames_cell = peakStartFrames_cell(~isnan(peakStartFrames_cell));
    peakStartFrames_cell = peakStartFrames_cell + 1; % from 0-indexing in python to 1-indexing in matlab
    F_cell = F(cell_idx, :);
    Fdenoised_cell = Fdenoised(cell_idx, :);
   
    subplot(3, 1, 1)
    plot(1:length(F_cell), F_cell, 'Color', 'k', 'LineWidth', LineWidth)
    title(strcat([fileName, ' cell ' num2str(cell_idx)]));
    box off
    legend('Original', 'Location', 'northeastoutside')
    set(gca,'TickDir','out'); 
    ylabel('Fluorescence')

    subplot(3, 1, 2)
    F_scaled = (F_cell - min(F_cell)) / (max(F_cell) - min(F_cell)) * max(Fdenoised_cell);
    plot(1:length(F_scaled), F_scaled, 'Color', 'k', 'LineWidth', LineWidth)
    hold on 
    plot(Fdenoised_cell, 'LineWidth', LineWidth, 'Color', 'r')
    box off
    set(gca,'TickDir','out'); 
    ylabel('Arbitrary units')
    legend('Scaled', 'Denoised', 'Location', 'northeastoutside')

    subplot(3, 1, 3)
    plot(1:length(Fdenoised_cell), Fdenoised_cell, 'Color', 'r', 'LineWidth', LineWidth)
    hold on 
    num_peaks = length(peakStartFrames_cell);
    % peak_plot_heights = repmat(max(Fdenoised_cell) * 1.2, num_peaks);
    peak_plot_heights = Fdenoised_cell(peakStartFrames_cell);
    scatter(peakStartFrames_cell, peak_plot_heights, 'bx')
    box off
    set(gca,'TickDir','out'); 
    ylabel('Arbitrary units')
    legend('Denoised', 'Event start', 'Location', 'northeastoutside')
    xlabel('Recording frames')
    
    
    
    % save figure
    figName = strcat(['unit_', num2str(cell_idx), '_2ptraces']);
    figPath = fullfile(figFolder, figName);

    if Params.showOneFig 
        pipelineSaveFig(figPath, Params.figExt, Params.fullSVG, oneFigureHandle);
    else 
        pipelineSaveFig(figPath, Params.figExt, Params.fullSVG);
    end 

    if ~Params.showOneFig
        close all
    else 
        set(0, 'CurrentFigure', oneFigureHandle);
        clf reset
    end 
    
end 

end

