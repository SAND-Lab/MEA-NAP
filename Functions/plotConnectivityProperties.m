function [] = plotConnectivityProperties(adjM, e, lagval, maxSTTC, meanSTTC, ND, NS, EW, FN, Params)
%{

Parameters
----------

Returns 
-------


%}

p = [10 10 1100 600];
set(0, 'DefaultFigurePosition', p)

if ~isfield(Params, 'oneFigure')
    f1 = figure;
else 
    set(Params.oneFigure, 'Position', p);
end 

t = tiledlayout(6,6);
t.Title.String = strcat(regexprep(FN,'_','','emptymatch'),{' '},num2str(lagval(e)),{' '},'ms',{' '},'lag');

nexttile(1,[3 2]);
imagesc(adjM)
xlabel('nodes')
ylabel('nodes')
title('adjacency matrix')
c = colorbar;
c.Label.String = 'correlation coefficient';
aesthetics
set(gca,'TickDir','out');

nexttile(19,[3 1]);
bar(maxSTTC(e))
ylim([0 max(adjM(:))+0.15*max(adjM(:))])
title('max corr. value')
aesthetics
set(gca,'TickDir','out');
set(gca,'xtick',[])

nexttile(20,[3 1]);
bar(meanSTTC(e))
ylim([0 max(adjM(:))+0.15*max(adjM(:))])
title('mean corr. value')
aesthetics
set(gca,'TickDir','out');
set(gca,'xtick',[])

nexttile(4,[2 3]);
histogram(ND,50)
xlabel('node degree')
ylabel('frequency')
aesthetics
set(gca,'TickDir','out');

nexttile(16,[2 3]);
histogram(NS,50)
xlabel('node strength')
ylabel('frequency')
aesthetics
set(gca,'TickDir','out');

nexttile(28,[2 3]);
histogram(EW,50)
xlabel('edge weight')
ylabel('frequency')
aesthetics
set(gca,'TickDir','out');
   
%% save figure

for nFigExt = 1:length(Params.figExt)
    saveas(gcf,strcat(['1_adjM', num2str(lagval(e)),'msConnectivityStats', Params.figExt{nFigExt}]));
end 

if ~isfield(Params, 'oneFigure')
    close all
else 
    % Reset the oneFigure figure handle shared by all plots
    set(0, 'CurrentFigure', Params.oneFigure);
    clf reset
end

    
end