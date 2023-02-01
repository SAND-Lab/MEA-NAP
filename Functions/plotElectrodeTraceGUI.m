%% Parameters 

rawDataFolder = '/media/timothysit/Elements/MAT_files/MPT_MEC/';
fileName = 'MPT200108_2B_DIV14.mat';
channelNameToPlot = 14;
plotTimeRange = [0, 60];  % in seconds

data = load(fullfile(rawDataFolder, fileName));

channelIdxToPlot = find(data.channels == channelNameToPlot);
plotTimeSamplesRange = plotTimeRange * data.fs + 1;  % 1 indexing
numSamplesToPlot = plotTimeSamplesRange(2) - plotTimeSamplesRange(1);
secTimeBins = linspace(plotTimeRange(1), plotTimeRange(2), numSamplesToPlot + 1);

%% Plot

figure 

plot(secTimeBins, data.dat(plotTimeSamplesRange(1):plotTimeSamplesRange(2), channelIdxToPlot))
xlabel('Time (seconds)')
title(sprintf('Channel %.f', channelNameToPlot));
