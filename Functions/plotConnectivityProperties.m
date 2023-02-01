function [] = plotConnectivityProperties(adjM, e, lagval, maxSTTC, meanSTTC, ... 
    ND, NS, MEW, FN, Params, figFolder)
%
% Plots connectivity properties given the adjacency matrix (adjM)
% Parameters
% ----------
% adjM : matrix 
%    adjacency matrix
% e : int
%    index of the lagvals variable 
% lagval : int
%    lag value used in spike-tile timing coefficient (STTC)
% maxSTTC : float 
% meanSTTC : float 
%    mean value of STTC values (can be thresholded or not)
% MEW : 
%   mean edge weight of each node (currently unused, but kept for
%   historical reasons)
% Params : struct
% Returns 
% -------
% None
% 
% Figures generated 
% -----------------

p = [10 10 1100 600];

if ~isfield(Params, 'oneFigure')
    F1 = figure;
    F1.OuterPosition = p;
    t = tiledlayout(6,6);
    t.Title.String = strcat(regexprep(FN,'_','','emptymatch'),{' '},num2str(lagval(e)),{' '},'ms',{' '},'lag');
else 
    set(0, 'DefaultFigurePosition', p)
    set(Params.oneFigure, 'Position', p);
    t = tiledlayout(Params.oneFigure, 6,6);
    t.Title.String = strcat(regexprep(FN,'_','','emptymatch'),{' '},num2str(lagval(e)),{' '},'ms',{' '},'lag');
    %title(strcat(regexprep(FN,'_','','emptymatch'),{' '},num2str(lagval(e)),{' '},'ms',{' '},'lag'));
end 

nexttile(t, 1,[3 2]);
imagesc(adjM)
xlabel('nodes')
ylabel('nodes')
title('adjacency matrix')
c = colorbar;
c.Label.String = 'correlation coefficient';
aesthetics
set(gca,'TickDir','out');

nexttile(t, 19,[3 1]);
bar(maxSTTC(e))

max_adjM = max(adjM(:));
max_adjM = max([max_adjM, 0.0001]);

ylim([0 max_adjM + 0.15 * max_adjM])
title('max corr. value')
aesthetics
set(gca,'TickDir','out');
set(gca,'xtick',[])

nexttile(t, 20,[3 1]);
bar(meanSTTC(e))
ylim([0 max_adjM + 0.15 * max_adjM])
title('mean corr. value')
aesthetics
set(gca,'TickDir','out');
set(gca,'xtick',[])

nexttile(t, 4,[2 3]);
histogram(ND,50)
xlabel('node degree')
ylabel('frequency')
aesthetics
set(gca,'TickDir','out');

nexttile(t, 16,[2 3]);
histogram(NS,50)
xlabel('node strength')
ylabel('frequency')
aesthetics
set(gca,'TickDir','out');

nexttile(t, 28,[2 3]);
% histogram(EW,50)
if Params.excludeEdgesBelowThreshold 
    significantEdges = adjM(adjM > 0);
else 
    significantEdges = adjM(:);
end 

histogram(significantEdges);
xlabel('edge weight')
ylabel('frequency')
aesthetics
set(gca,'TickDir','out');
   
%% save figure
figName = strcat(['1_adjM', num2str(lagval(e)),'msConnectivityStats']);
figPath = fullfile(figFolder, figName); 

if ~isfield(Params, 'oneFigure')
    pipelineSaveFig(figPath, Params.figExt, Params.fullSVG);
else 
    pipelineSaveFig(figPath, Params.figExt, Params.fullSVG, Params.oneFigure);
end 

if ~isfield(Params, 'oneFigure')
    close all
else 
    % Reset the oneFigure figure handle shared by all plots
    set(0, 'CurrentFigure', Params.oneFigure);
    clf reset
end

    
end