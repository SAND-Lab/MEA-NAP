function plotNetworkBursts(spikeTimes, Ephys, Info, Params, figFolder, oneFigureHandle)
%PLOTNETWORKBURSTS Plots single file burst detection result
%   Detailed explanation goes here
% spikeTimes : struct
% figFolder : directory 
% oneFigureHandle : matlab figure object

% Set figure size 
set(gcf, 'Position', [100, 100, 900, 1200]);

% Convert spike time to matrix
fs = 10;
spikeMatrix = SpikeTimesToMatrix(spikeTimes, fs, Params.SpikesMethod,Info);
recordingTime = linspace(0, size(spikeMatrix, 1)/fs, size(spikeMatrix, 1));
spikeMatrixWithBursts = zeros(size(spikeMatrix)) + nan;

% Raster plot 
rasterAx = subplot(5, 4, [1, 2, 3, 4]);
imagesc(spikeMatrix', 'XData', recordingTime);
xlabel('Time (s)')
ylabel('Electrodes');
title('Downsampled raster')

% Raster plot only highlighting the bursts
burstAx = subplot(5, 4, [5, 6, 7, 8]);

for burstIdx = 1:Ephys.numNbursts
    
    % NOTE: one-indexing here, so cannot have burstTimes between 0 - 0.5...
    burstStartIdx = max([1, round(Ephys.burstTimes(burstIdx, 1) * fs)]);
    burstEndIdx = round(Ephys.burstTimes(burstIdx, 2) * fs);

    spikeMatrixWithBursts(burstStartIdx:burstEndIdx, :) = ...
        spikeMatrix(burstStartIdx:burstEndIdx, :);

end

imagesc(spikeMatrixWithBursts', 'XData', recordingTime);
ylabel('Electrodes')
xlabel('Time (s)')
title('Raster with only bursts')


if strcmp(Params.networkBurstDetectionMethod, 'Threshold')
    % plot the zscored firing rate
    subplot(5, 4, [9, 10, 11, 12]);

    plot(Ephys.burstDetectionInfo.zScoredMean);
    
    % Also plot the threshold used
    yline(Ephys.burstDetectionInfo.zScoreThreshold);

    xlabel('Time (s)')
    ylabel('z-scored mean')
    title('Network mean activity')


end


% ITI distribution plot
subplot(5, 4, [13, 14, 17, 18]);

% get the combined spike times ISI 
combinedSpikeTimes = combineAllChannelSpikeTimes(spikeTimes, Params.SpikesMethod);
combinedISI = diff(combinedSpikeTimes);
outSideBurstISI = combinedISI;  % make a copy and then set things to NaN later
withinBurstISI = [];
% Set ISI values to NaN for those outside bursts
for burstIdx = 1:Ephys.numNbursts
    [~, burstStartIdx] = min(abs(Ephys.burstTimes(burstIdx, 1) - combinedSpikeTimes));
    [~, burstEndIdx] = min(abs(Ephys.burstTimes(burstIdx, 2) - combinedSpikeTimes));
    outSideBurstISI(burstStartIdx:burstEndIdx-1) = nan; % Set ISIs within bursts to NaN
    withinBurstISI = [withinBurstISI; combinedISI(burstStartIdx:burstEndIdx-1)];
end

combinedISI(combinedISI == 0) = nan;
binEdges = logspace(log10(min(combinedISI)), log10(max(combinedISI)), 100);

% plot normalized histogram of outsideBurstISI and withinBurstISI
histogram(outSideBurstISI, binEdges, 'Normalization', 'probability', 'DisplayStyle', 'stairs');
hold on;
histogram(withinBurstISI, binEdges, 'Normalization', 'probability', 'DisplayStyle', 'stairs');
xscale('log')
xlabel('Inter-Spike Interval (s)');
ylabel('Probability');
% yscale('log')
title('ISI Distribution: Within vs. Outside Bursts');
legend('Outside Bursts', 'Within Bursts');


% Threshold parameter sweep result (specific to the threhsold detection
% method)
if strcmp(Params.networkBurstDetectionMethod, 'Threshold')
    subplot(5 , 4, [15, 16, 19, 20]);
    
    plot(Ephys.burstDetectionInfo.networkBurstsThresholds, Ephys.burstDetectionInfo.numBurstsPerThreshold)
    hold on
    scatter(Ephys.burstDetectionInfo.zScoreThreshold, size(Ephys.burstTimes, 1));
    legend('Tested thresholds', 'Chosen threshold')
    ylabel('Number of network bursts')
    xlabel('Burst detection z-score threshold')
    title('Number of bursts as function of threshold')
end 

% Save the figure to a folder
figName = '8_BurstDetectionInfo';

% save figure
figPath = fullfile(figFolder, figName);

if Params.showOneFig
    pipelineSaveFig(figPath, Params.figExt, Params.fullSVG, oneFigureHandle);
else
    pipelineSaveFig(figPath, Params.figExt, Params.fullSVG)
end 

if Params.showOneFig
    clf(oneFigureHandle, 'reset')
else 
    close(F1);
end 


end