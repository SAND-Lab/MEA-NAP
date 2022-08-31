function plotElectrodeLayout(HomeDir, Params)
%PLOTELECTRODELAYOUT Plots the layout of the electrodes specified in Params
%   Detailed explanation goes here

num_channels = size(Params.coords, 1);
p = [100 100 1400 550];
if Params.showOneFig 
    if ~isfield(Params, 'oneFigure')
        Params.oneFigure = figure;
    end 
    set(0, 'DefaultFigurePosition', p)
    set(Params.oneFigure, 'Position', p);
else
    F1 = figure;
    set(0, 'DefaultFigurePosition', p)
    set(F1, 'Position', p);
end 


subplot(1, 2, 1)
title('Provided electrode layout (channel index)')
for n_channel = 1:num_channels
    txt_to_plot = sprintf('%.f', n_channel);
    text(Params.coords(n_channel, 1), Params.coords(n_channel, 2), txt_to_plot)
end 
xlabel('X coordinates')
ylabel('Y coordinates')
xlim([min(Params.coords(:, 1)) - 1, max(Params.coords(:, 1) + 1)])
ylim([min(Params.coords(:, 2)) - 1, max(Params.coords(:, 2) + 1)])

subplot(1, 2, 2)
title('Provided electrode layout (channel ID)')
for n_channel = 1:num_channels
    txt_to_plot = sprintf('%.f', Params.channels(n_channel));
    text(Params.coords(n_channel, 1), Params.coords(n_channel, 2), txt_to_plot)
end 
xlabel('X coordinates')
ylabel('Y coordinates')
xlim([min(Params.coords(:, 1)) - 1, max(Params.coords(:, 1) + 1)])
ylim([min(Params.coords(:, 2)) - 1, max(Params.coords(:, 2) + 1)])

set(gcf, 'color', 'w')

% save figure
figFolder = fullfile(HomeDir, strcat(['OutputData', Params.Date]));
figName = 'channel_layout';
figSavePath = fullfile(figFolder, figName);

if ~isfield(Params, 'oneFigure')
    pipelineSaveFig(figSavePath, Params.figExt, Params.fullSVG, F1);
else 
    pipelineSaveFig(figSavePath, Params.figExt, Params.fullSVG, Params.oneFigure);
end 

if ~isfield(Params, 'oneFigure')
    close all
else 
    set(0, 'CurrentFigure', Params.oneFigure);
    clf reset
end 



end

