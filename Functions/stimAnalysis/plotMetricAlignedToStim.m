function plotMetricAlignedToStim(frAlignedToStim, rasterBins, Info, Params, ...
    ylabel_txt, figFolder, figName, figureHandle)
%PLOTMETRICALIGNEDTOSTIM Summary of this function goes here
%   Detailed explanation goes here
   % figureHandle = figure;
    numChannels = size(frAlignedToStim, 1);
    set(figureHandle, 'Position', [100, 100, 600, 500]);
    t = tiledlayout(2, 1);
    ax1 = nexttile;
    meanFRalignedToStim = squeeze(mean(frAlignedToStim, [1, 2]));
    plot(rasterBins(2:end), meanFRalignedToStim)
    hold on 

    % This needs information about the blank duration, I guess that
    % can be passed through Params
    fill([0, Params.blankDurMode + Params.postStimWindowDur/1000, ...
          Params.blankDurMode + Params.postStimWindowDur/1000, 0], ...
          [0, 0, max(meanFRalignedToStim), max(meanFRalignedToStim)], [0.5, 0.5, 0.5], 'FaceAlpha', 0.3,'LineStyle','none')
    
    box off 
    set(gca, 'TickDir', 'out');
    ylabel(ylabel_txt)
    xlim([rasterBins(1), rasterBins(end)])
    title(Info.FN{1}, 'Interpreter', 'none');
    
    ax2 = nexttile;
    imagesc(rasterBins(2:end), 1:numChannels, squeeze(mean(frAlignedToStim, 2)))
    box off
    linkaxes([ax1, ax2], 'x');

    cbar = colorbar('eastoutside');
    ylabel(cbar, 'Firing rate (spikes/s)', 'FontSize', 12);
    ylabel('Channel')
    xlabel('Time from stimulation (s)')
    set(gca, 'TickDir', 'out');
    set(gcf, 'color', 'w')
    

    % save figure
    pipelineSaveFig(fullfile(figFolder, figName), Params.figExt, Params.fullSVG, gcf);
end

