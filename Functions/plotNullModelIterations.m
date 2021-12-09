function [] = plotNullModelIterations(met, met2, lagval, e, FN, Params)

p = [100 100 1000 600];
set(0, 'DefaultFigurePosition', p)

figure();

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

if Params.figMat == 1
    saveas(gcf,strcat('10_adjM',num2str(lagval(e)),'msNullModels.fig'));
end
if Params.figPng == 1
    saveas(gcf,strcat('10_adjM',num2str(lagval(e)),'msNullModels.png'));
end
if Params.figEps == 1
    saveas(gcf,strcat('10_adjM',num2str(lagval(e)),'msNullModels.eps'));
end

close all

    
end