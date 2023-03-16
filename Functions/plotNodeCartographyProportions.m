function [] = plotNodeCartographyProportions(NetMet, lagval, FN, Params, figFolder)
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

if ~isfield(Params, 'oneFigure')
    figure();
else 
    set(Params.oneFigure, 'Position', p);
end 

t = tiledlayout(1,2);
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

%% add diagram

nexttile
imshow('NodeCartographyFull.jpg')

%% bar chart

nexttile
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
pipelineSaveFig(figPath, Params.figExt, Params.fullSVG);


if ~isfield(Params, 'oneFigure')
    close all
else 
    set(0, 'CurrentFigure', Params.oneFigure);
    clf reset
end 

end


