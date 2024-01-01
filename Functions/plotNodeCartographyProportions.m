function [] = plotNodeCartographyProportions(NetMet, lagval, FN, Params, figFolder, oneFigureHandle)
% Plot proportion of nodes belonging to each node cartography group
% Parameters
% ----------
% NetMet : structure 
% lagval : int 
% FN : 
% Params : structure 
% figFolder : path to directory 
%       absolute path of folder where you want to save the plot 
% Returns
% -------
% 
% 
%


%% figure
p = [100 100 1200 600];
set(0, 'DefaultFigurePosition', p)

if Params.showOneFig
    if isgraphics(oneFigureHandle)
        set(oneFigureHandle, 'Position', p);
    else 
        oneFigureHandle = figure;
        set(oneFigureHandle, 'Position', p);
    end 
else
    figure
    set(gcf, 'Position', p);
end 

t = tiledlayout(2,2);
t.TileSpacing = 'compact';
t.Padding = 'compact';
t.Title.String = strcat(regexprep(FN,'_','','emptymatch'));

%% colours

c1 = [0.8 0.902 0.310]; % light green
c2 = [0.580 0.706 0.278]; % medium green
c3 = [0.369 0.435 0.122]; % dark green
c4 = [0.2 0.729 0.949]; % light blue
c5 = [0.078 0.424 0.835]; % medium blue
c6 = [0.016 0.235 0.498]; % dark blue

%% Add custom boundary scatter diagram 
nexttile
dotSize = 500;
scatter(0.2, 2.75,  dotSize, c4, 'filled');
hold on 
scatter(0.5, 2.75,  dotSize, c5, 'filled');
hold on 
scatter(0.8, 2.75, dotSize, c6, 'filled');

yline(2)
plot([0.3, 0.3], [2, 3], '--', 'color', [.5 .5 .5]);
plot([0.7, 0.7], [2, 3], '--', 'color', [.5 .5 .5]);
plot([0.45, 0.45], [0, 2], '--', 'color', [.5 .5 .5]);
plot([0.72, 0.72], [0, 2], '--', 'color', [.5 .5 .5]);

scatter(0.25, 1,  dotSize, c1, 'filled');
hold on 
scatter(0.6, 1, dotSize, c2, 'filled');
hold on
scatter(0.8, 1,  dotSize, c3, 'filled');

ylim([0, 3])
xlim([0, 1])
xticks([]) 
yticks([])
aesthetics
xlabel('Participation coefficient');
ylabel('Within-module degree z-score');

% hline(Params.(sprintf('hubBoundaryWMdDeg_%.fmsLag', lag)));


%% add diagram

nexttile(3)
imshow('NodeCartographyDiagram.jpg')

%% bar chart

nexttile([2, 1])
numNodeCartographyGroups = 6;

for l = 1:length(lagval)
    for i = 1:numNodeCartographyGroups
        % eval(['NdPrp(l,i) = NetMet.adjM' num2str(lagval(l)) 'mslag.NCpn' num2str(i) ';']);
        lagNetMet = NetMet.(['adjM', num2str(lagval(l)), 'mslag']);
        
        if lagNetMet.aN >= Params.minNumberOfNodesToCalNetMet
            NdPrp(l, i) = lagNetMet.(['NCpn' num2str(i)]);
            xlab{l} = num2str(lagval(l));
        end
    end
end
  
x = 1:length(lagval);
b = bar(x,NdPrp,'stacked');

for t = 1:6
    eval(['b(t).FaceColor = c' num2str(t) ';']);
end
xticks(1:length(lagval))
xticklabels(xlab)
xlabel('STTC lag (ms)')
ylabel('proportion of nodes')
aesthetics
set(gca,'TickDir','out');


%% save figure

figName = 'NodeCartographyProportions';
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


