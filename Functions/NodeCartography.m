function [NdCartDiv, PopNumNC] = NodeCartography(Z, PC, lagval, e, FN, Params, figFolder, oneFigureHandle)
% This also makes a plot  
% node cartography 
% see Guimera and Amaral, 2005
% 'Functional cartography of complex metabolic networks'
% author RCFeord 2020
% Updated by Tim Sit
% 
% Parameters 
% ---------
% Params.autoSetCartographyBoudariesPerLag : boolean 
%     whether to use a specific set of boundaries for each lag value
% Params.hubBoundaryWMdDeg : float 
%     default value : 2.5; boundary that separates hub and non-hubs
% Params.periPartCoef = 0.625; % boundary that separates peripheral node and none-hub connector
% Params.proHubpartCoef = 0.3; % boundary that separates provincial hub and connector hub
% Params.nonHubconnectorPartCoef = 0.8; % boundary that separates non-hub connector and non-hub kinless node
% Params.connectorHubPartCoef = 0.75;  % boundary that separates connector hub and kinless hub
% 
% Returns
% -------
% NdCartDiv : 
% PopNumNC : 

%% figure

p = [50 50 600 700];
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

t = tiledlayout(2,1);
t.Title.String = strcat(regexprep(FN,'_','','emptymatch'),{' '},num2str(lagval(e)),{' '},'ms',{' '},'lag');

%% define colour scheme

c1 = [0.8 0.902 0.310]; % light green, Peripheral node
c2 = [0.580 0.706 0.278]; % medium green, Non-hub connector
c3 = [0.369 0.435 0.122]; % dark green, Non-hub kinless node 
c4 = [0.2 0.729 0.949]; % light blue, Provincial hub
c5 = [0.078 0.424 0.835]; % medium blue, Connector hub
c6 = [0.016 0.235 0.498]; % dark blue, Kinless hub

%% create cartography boundaries

% Determine whether we need a specific boundary per lag 
if Params.autoSetCartographyBoudariesPerLag
    hubBoundaryWMdDeg = Params.(strcat('hubBoundaryWMdDeg', sprintf('_%.fmsLag', lagval(e))));
    periPartCoef = Params.(strcat('periPartCoef', sprintf('_%.fmsLag', lagval(e))));
    proHubpartCoef = Params.(strcat('proHubpartCoef', sprintf('_%.fmsLag', lagval(e))));
    nonHubconnectorPartCoef = Params.(strcat('nonHubconnectorPartCoef', sprintf('_%.fmsLag', lagval(e))));
    connectorHubPartCoef = Params.(strcat('connectorHubPartCoef', sprintf('_%.fmsLag', lagval(e))));
else
    hubBoundaryWMdDeg = Params.hubBoundaryWMdDeg;
    periPartCoef = Params.periPartCoef;
    proHubpartCoef = Params.proHubpartCoef;
    nonHubconnectorPartCoef = Params.nonHubconnectorPartCoef;
    connectorHubPartCoef = Params.connectorHubPartCoef;
end 


nexttile

% Old hard-coded ranges
% partCoefRange = [0, 1];  % range of participation coefficient
% wMdDegRange = [-2, 4]; % range of within-module degree (z-score)

% Define participation coefficient range based on min max values
partCoefRange = [min(PC), max(PC)]; 
if isempty(PC)
    partCoefRange = [0, 1];
elseif (partCoefRange(1) == partCoefRange(2)) || all(isnan(PC)) 
    partCoefRange = [0, 1];
end 

% Define within-module degree z-score (y axis) range
wMdDegRange = [];

if isempty(Z)
    wMdDegRange = [-2, 4];
elseif (wMdDegRange(1) == wMdDegRange(2)) || all(isnan(Z))
    wMdDegRange = [-2, 4];
else
    if min(Z) < 0
        wMdDegRange(1) = min(Z) * 1.1; 
    else
        wMdDegRange(1) = min(Z) * 0.9; 
    end 

    if max(Z) > 0
        wMdDegRange(2) = max(Z) * 1.1;
    else
        wMdDegRange(2) = max(Z) * 0.9;
    end 
end 


plot(partCoefRange,[hubBoundaryWMdDeg  hubBoundaryWMdDeg ],'--k')
hold on
plot([periPartCoef periPartCoef],[wMdDegRange(1) hubBoundaryWMdDeg ],'--k')
plot([nonHubconnectorPartCoef nonHubconnectorPartCoef],[wMdDegRange(1) hubBoundaryWMdDeg ],'--k')
plot([proHubpartCoef  proHubpartCoef ],[hubBoundaryWMdDeg  wMdDegRange(2)],'--k')
plot([connectorHubPartCoef connectorHubPartCoef],[hubBoundaryWMdDeg  wMdDegRange(2)],'--k')
xlim(partCoefRange)
ylim(wMdDegRange)

set(gcf,'color','w'); % white background
set(gca,'TickDir','out');

%% Find node identities

NdCartDiv = zeros(length(PC),1);
PCdivNonHub = [0, periPartCoef, nonHubconnectorPartCoef  1];
PCdivHub = [0, proHubpartCoef, connectorHubPartCoef, 1];
PCp1 = [];
PCp2 = [];
PCp3 = [];
PCc1 = [];
PCc2 = [];
PCc3 = [];
Zp1 = [];
Zp2 = [];
Zp3 = [];
Zc1 = [];
Zc2 = [];
Zc3 = [];

for j = 1:length(PC)
    if (Z(j) < hubBoundaryWMdDeg) && (PC(j) < periPartCoef)
        NdCartDiv(j) = 1;
        PCp1 = [PCp1 PC(j)];
        Zp1 = [Zp1 Z(j)];
    elseif (Z(j) < hubBoundaryWMdDeg) && (PC(j) >= periPartCoef) && (PC(j) < nonHubconnectorPartCoef)
        NdCartDiv(j) = 2;
        PCp2 = [PCp2 PC(j)];
        Zp2 = [Zp2 Z(j)];
    elseif (Z(j) < hubBoundaryWMdDeg) && (PC(j) >= nonHubconnectorPartCoef)
        NdCartDiv(j) = 3;
        PCp3 = [PCp3 PC(j)];
        Zp3 = [Zp3 Z(j)];
    elseif (Z(j) >= hubBoundaryWMdDeg) && (PC(j) < proHubpartCoef)
        NdCartDiv(j) = 4;
        PCc1 = [PCc1 PC(j)];
        Zc1 = [Zc1 Z(j)];
    elseif (Z(j) >= hubBoundaryWMdDeg) && (PC(j) >= proHubpartCoef) && (PC(j) < connectorHubPartCoef)
        NdCartDiv(j) = 5;
        PCc2 = [PCc2 PC(j)];
        Zc2 = [Zc2 Z(j)];
    elseif (Z(j) > hubBoundaryWMdDeg) && (PC(j) >= connectorHubPartCoef)
        NdCartDiv(j) = 6;
        PCc3 = [PCc3 PC(j)];
        Zc3 = [Zc3 Z(j)];
    end
end

PopNumNC(1) = length(PCp1); % Peripheral Node
PopNumNC(2) = length(PCp2); % Non-hub connector
PopNumNC(3) = length(PCp3); % Non-hub kinless node
PopNumNC(4) = length(PCc1); % Provincial hub
PopNumNC(5) = length(PCc2); % Connector hub 
PopNumNC(6) = length(PCc3); % Kinless hub

%% plot nodes

scatter(PCp1,Zp1,18,'MarkerEdgeColor',c1,'MarkerFaceColor',c1)
scatter(PCp2,Zp2,18,'MarkerEdgeColor',c2,'MarkerFaceColor',c2)
scatter(PCp3,Zp3,18,'MarkerEdgeColor',c3,'MarkerFaceColor',c3)
scatter(PCc1,Zc1,18,'MarkerEdgeColor',c4,'MarkerFaceColor',c4)
scatter(PCc2,Zc2,18,'MarkerEdgeColor',c5,'MarkerFaceColor',c5)
scatter(PCc3,Zc3,18,'MarkerEdgeColor',c6,'MarkerFaceColor',c6)

title('node cartography')
xlabel('participation coefficient')
ylabel('within-module degree z-score')

%% add cartography diagram

nexttile

imshow('NodeCartographyDiagram.jpg')


%% save figure
figName = strcat(['9_adjM',num2str(lagval(e)),'msNodeCartography']);
figPath = fullfile(figFolder, figName);

if Params.showOneFig
        pipelineSaveFig(figPath, Params.figExt, Params.fullSVG, oneFigureHandle)
    else 
        pipelineSaveFig(figPath, Params.figExt, Params.fullSVG)
end 

% Close figure or clear the one shared figures
if ~Params.showOneFig
    close(gcf)
else
    set(0, 'CurrentFigure', oneFigureHandle);
    clf reset
end 


end