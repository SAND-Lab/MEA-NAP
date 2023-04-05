%% Parameters 

rawDataFolder = '/media/timothysit/Elements/MAT_files/MPT_MEC/';
fileName = 'MPT200108_2B_DIV14.mat';
channelNameToPlot = 14;
plotTimeRange = [0, 60];  % in seconds
filterTrace = 1;  % 0 : plot raw trace, 1 : plot filtered trace
filterLowPass = 600;
filterHighPass = 8000;
traceColor = 'black';

data = load(fullfile(rawDataFolder, fileName));

channelIdxToPlot = find(data.channels == channelNameToPlot);
plotTimeSamplesRange = plotTimeRange * data.fs + 1;  % 1 indexing
numSamplesToPlot = plotTimeSamplesRange(2) - plotTimeSamplesRange(1);
secTimeBins = linspace(plotTimeRange(1), plotTimeRange(2), numSamplesToPlot + 1);

channelTrace = data.dat(:, channelIdxToPlot);

if filterTrace
    wn = [filterLowPass filterHighPass] / (fs / 2);
    filterOrder = 3;
    [b, a] = butter(filterOrder, wn);
    channelTrace = filtfilt(b, a, double(channelTrace));
end 


%% Plot

figure 

plot(secTimeBins, channelTrace(plotTimeSamplesRange(1):plotTimeSamplesRange(2)), 'color', traceColor)
xlabel('Time (seconds)')
title(sprintf('Channel %.f', channelNameToPlot));


%