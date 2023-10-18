function [] = plotNullModelIterations(met, met2, lagval, e, FN, Params, figFolder, oneFigureHandle)
%{

Parameters
----------

met : 
met2 : 
lagval : int
e : 
FN : 
Params : struct


Returns 
-------

%}

p = [100 100 1000 600];
set(0, 'DefaultFigurePosition', p)

if ~Params.showOneFig
    figure();
else 
    set(oneFigureHandle, 'Position', p);
end 

t = tiledlayout(2,1);
t.Title.String = strcat(regexprep(FN,'_','','emptymatch'),{' '},num2str(lagval(e)),{' '},'ms',{' '},'lag');

nexttile
plot(met,'LineWidth',2)
ylabel('small world coefficient')
xlabel('iterations/10')
title('lattice null model')
aesthetics
set(gca,'TickDir','out');

nexttile
plot(met2,'LineWidth',2)
title('random null model')
ylabel('small world coefficient')
xlabel('iterations/10')
aesthetics
set(gca,'TickDir','out');


%% save figure
figName = strcat(['8_adjM', num2str(lagval(e)), 'msNullModels']);
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