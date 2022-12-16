function [] = electrodeSpecificMetrics(ND, NS, MEW, Eloc, BC, PC, Z, lagval, e, FN, Params, figFolder)
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

% Plot within-module degree z-score
nexttile(11,[3,1])

skipPlot = (numel(Z) == 1) && isnan(Z);
if ~skipPlot
    HalfViolinPlot(Z,1,[0.3 0.3 0.3],0.3)
    aesthetics
    set(gca,'TickDir','out');
    set(gca,'xtick',[])
    ylabel('within-module degree z-score')
    if nanmin(Z) == nanmax(Z)
        ylim([0, nanmax(Z) + 0.1])  % handle edge case of eg. all zeros
    else
        ylim([nanmin(Z)-abs(nanmin(Z))*0.2 nanmax(Z)+0.2*nanmax(Z)])
    end 
end 

% Plot local efficiency
nexttile(12,[3,1])
skipPlot = (numel(Eloc) == 1) && isnan(Eloc);
if ~skipPlot
    HalfViolinPlot(Eloc,1,[0.3 0.3 0.3],0.3)
    aesthetics
    set(gca,'TickDir','out');
    set(gca,'xtick',[])
    ylabel('local connectivity')
    ylim([0 nanmax(Eloc)+0.2*nanmax(Eloc)])
end 

% Plot participation coefficient 
nexttile(13,[3,1])
skipPlot = (numel(PC) == 1) && isnan(PC);
if ~skipPlot
    HalfViolinPlot(PC,1,[0.3 0.3 0.3],0.3)
    aesthetics
    set(gca,'TickDir','out');
    set(gca,'xtick',[])
    ylabel('participation coefficient')
    ylim([0 nanmax(PC)+0.2*nanmax(PC)])
end 

% Plot betweeness centrality 
skipPlot = (numel(BC) == 1) && isnan(BC);
nexttile(14,[3,1])
if ~skipPlot
    HalfViolinPlot(BC,1,[0.3 0.3 0.3],0.3)
    aesthetics
    set(gca,'TickDir','out');
    set(gca,'xtick',[])
    ylabel('betweeness centrality')
    if nanmin(BC) == nanmax(BC)
        ylim([0, nanmax(BC) + 0.1])  % handle edge case of eg. all zeros
    else
        ylim([0 nanmax(BC)+0.2*nanmax(BC)])
    end 
end 


%% save figure
figName = strcat('8_adjM', num2str(lagval(e)),'msGraphMetricsByNode');
figPath = fullfile(figFolder, figName);

if ~isfield(Params, 'oneFigure')
    pipelineSaveFig(figPath, Params.figExt, Params.fullSVG, F1);
else 
    pipelineSaveFig(figPath, Params.figExt, Params.fullSVG, Params.oneFigure);
end 

if ~isfield(Params, 'oneFigure')
    close all
else 
    set(0, 'CurrentFigure', Params.oneFigure);
    clf reset
end 

end
