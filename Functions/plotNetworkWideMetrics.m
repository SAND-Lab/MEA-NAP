function [] = plotNetworkWideMetrics(NetMet, meanSTTC, maxSTTC, lagval, FN, Params)

%% figure

p = [50 50 1400 700];
set(0, 'DefaultFigurePosition', p)

figure();
t = tiledlayout(4,5);
t.TileSpacing = 'compact';
t.Padding = 'compact';
t.Title.String = strcat(regexprep(FN,'_','','emptymatch'));
%% set up lag values labels for x axis

for l = 1:length(lagval)
        xlab{l} = num2str(lagval(l));
end

%% set up NetMet variables for plotting

Var = {'Dens', 'Q', 'nMod','Eglob', 'CC', 'PL', 'SW','SWw'};

for i = 1:length(Var)
    for e = 1:length(lagval)
        VN = cell2mat(Var(i));
        VNs = strcat('NetMet.adjM',num2str(lagval(e)),'mslag.',VN);
        eval([VN '(e) =' VNs ';']);
    end
end

%% start plotting

nexttile
imshow('EW.png')

nexttile
imshow('EW.png')

nexttile
imshow('Dens.png')

nexttile
imshow('nMod.png')

nexttile
imshow('MS.png')

nexttile
plot(meanSTTC,'LineWidth',1.5,'Marker','o','MarkerFaceColor','auto')
xticks(1:length(lagval))
xticklabels(xlab)
xlabel('STTC lag (ms)')
ylabel('edge weight (mean)')
aesthetics
set(gca,'TickDir','out');

nexttile
plot(maxSTTC,'LineWidth',1.5,'Marker','o','MarkerFaceColor','auto')
xticks(1:length(lagval))
xticklabels(xlab)
xlabel('STTC lag (ms)')
ylabel('edge weight (max)')
aesthetics
set(gca,'TickDir','out');

nexttile
plot(Dens,'LineWidth',1.5,'Marker','o','MarkerFaceColor','auto')
xticks(1:length(lagval))
xticklabels(xlab)
xlabel('STTC lag (ms)')
ylabel('density')
aesthetics
set(gca,'TickDir','out');

nexttile
plot(nMod,'LineWidth',1.5,'Marker','o','MarkerFaceColor','auto')
xticks(1:length(lagval))
xticklabels(xlab)
xlabel('STTC lag (ms)')
ylabel('number of modules')
aesthetics
set(gca,'TickDir','out');

nexttile
plot(Q,'LineWidth',1.5,'Marker','o','MarkerFaceColor','auto')
xticks(1:length(lagval))
xticklabels(xlab)
xlabel('STTC lag (ms)')
ylabel('modularity score')
aesthetics
set(gca,'TickDir','out');

nexttile
imshow('CC.png')

nexttile
imshow('PL.png')

nexttile
imshow('Eglob.png')

nexttile(14,[1 2])
imshow('SW.png')

nexttile
plot(CC,'LineWidth',1.5,'Marker','o','MarkerFaceColor','auto')
xticks(1:length(lagval))
xticklabels(xlab)
xlabel('STTC lag (ms)')
ylabel('mean clustering coefficient (norm)')
aesthetics
set(gca,'TickDir','out');

nexttile
plot(PL,'LineWidth',1.5,'Marker','o','MarkerFaceColor','auto')
xticks(1:length(lagval))
xticklabels(xlab)
xlabel('STTC lag (ms)')
ylabel('characteritics path length (norm)')
aesthetics
set(gca,'TickDir','out');

nexttile
plot(Eglob,'LineWidth',1.5,'Marker','o','MarkerFaceColor','auto')
xticks(1:length(lagval))
xticklabels(xlab)
xlabel('STTC lag (ms)')
ylabel('global efficiency')
aesthetics
set(gca,'TickDir','out');

nexttile
plot(SW,'LineWidth',1.5,'Marker','o','MarkerFaceColor','auto')
xticks(1:length(lagval))
xticklabels(xlab)
xlabel('STTC lag (ms)')
ylabel('small world coefficent \sigma')
aesthetics
set(gca,'TickDir','out');

nexttile
plot(SWw,'LineWidth',1.5,'Marker','o','MarkerFaceColor','auto')
xticks(1:length(lagval))
xticklabels(xlab)
xlabel('STTC lag (ms)')
ylabel('small world coefficent \omega')
aesthetics
set(gca,'TickDir','out');

%% save figure

if Params.figMat == 1
    saveas(gcf,'NetworkWideMetrics.fig');
end
if Params.figPng == 1
    saveas(gcf,'NetworkWideMetrics.png');
end
if Params.figEps == 1
    saveas(gcf,'NetworkWideMetrics.eps');
end

close all

end