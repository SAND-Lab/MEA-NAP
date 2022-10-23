function [] = electrodeSpecificMetrics(ND, NS, MEW, Eloc, BC, PC, Z, lagval, e, FN, Params)
% Plots electrode-level metrics for individual recordings
% TODO: allow this to accept arbitrary number of parameters to plot, 
% this allows easier extensions in the future.
% 
% Parameters
% ----------
% MEW : mean edge weight
% Returns
% -------
%

%% figure

p = [100 100 1400 550];
set(0, 'DefaultFigurePosition', p)

if ~isfield(Params, 'oneFigure')
    F1 = figure;
else 
    set(Params.oneFigure, 'Position', p);
end 

t = tiledlayout(4,7);
t.Title.String = strcat(regexprep(FN,'_','','emptymatch'),{' '},num2str(lagval(e)),{' '},'ms',{' '},'lag');

%% images

nexttile
imshow('ND.png')

nexttile
imshow('EW.png')

nexttile
imshow('NS.png')

nexttile
imshow('WMZ.png')

nexttile
imshow('Eloc.png')

nexttile
imshow('PC.png')

nexttile
imshow('BC.png')

%% half violin plots

nexttile(8,[3,1])
HalfViolinPlot(ND,1,[0.3 0.3 0.3],0.3)
aesthetics
set(gca,'TickDir','out');
set(gca,'xtick',[])
ylabel('node degree')
ylim([0 max(ND)+0.2*max(ND)])

nexttile(9,[3,1])
HalfViolinPlot(MEW,1,[0.3 0.3 0.3],0.3)
aesthetics
set(gca,'TickDir','out');
set(gca,'xtick',[])
ylabel('mean edge weight')
ylim([0 max(MEW)+0.2*max(MEW)])

nexttile(10,[3,1])
HalfViolinPlot(NS,1,[0.3 0.3 0.3],0.3)
aesthetics
set(gca,'TickDir','out');
set(gca,'xtick',[])
ylabel('node strength')
ylim([0 max(NS)+0.2*max(NS)])

nexttile(11,[3,1])
HalfViolinPlot(Z,1,[0.3 0.3 0.3],0.3)
aesthetics
set(gca,'TickDir','out');
set(gca,'xtick',[])
ylabel('within-module degree z-score')
try
    ylim([min(Z)-abs(min(Z))*0.2 max(Z)+0.2*max(Z)])
catch
    ylim([0 1])
end

nexttile(12,[3,1])
HalfViolinPlot(Eloc,1,[0.3 0.3 0.3],0.3)
aesthetics
set(gca,'TickDir','out');
set(gca,'xtick',[])
ylabel('local connectivity')
try
    ylim([0 max(Eloc)+0.2*max(Eloc)])
catch
    ylim([0 1])
end

nexttile(13,[3,1])
HalfViolinPlot(PC,1,[0.3 0.3 0.3],0.3)
aesthetics
set(gca,'TickDir','out');
set(gca,'xtick',[])
ylabel('participation coefficient')
try
    ylim([0 max(PC)+0.2*max(PC)])
catch
    ylim([0 1])
end

nexttile(14,[3,1])
HalfViolinPlot(BC,1,[0.3 0.3 0.3],0.3)
aesthetics
set(gca,'TickDir','out');
set(gca,'xtick',[])
ylabel('betweeness centrality')
try
    ylim([0 max(BC)+0.2*max(BC)])
catch
    ylim([0 0.1])
end


%% save figure
figName = strcat('8_adjM', num2str(lagval(e)),'msGraphMetricsByNode');

if ~isfield(Params, 'oneFigure')
    pipelineSaveFig(figName, Params.figExt, Params.fullSVG, F1);
else 
    pipelineSaveFig(figName, Params.figExt, Params.fullSVG, Params.oneFigure);
end 

if ~isfield(Params, 'oneFigure')
    close all
else 
    set(0, 'CurrentFigure', Params.oneFigure);
    clf reset
end 

end
