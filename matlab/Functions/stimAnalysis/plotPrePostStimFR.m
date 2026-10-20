function plotPrePostStimFR(spikeData, allStimTimes, Params, figFolder, figName, Info)
%PLOTPREPOSTSTIMFR Summary of this function goes here
%   Detailed explanation goes here
    numStimEvent = length(allStimTimes);
    numChannels = length(spikeData.stimInfo);

    % Start the post-stim window after the blanked artifact window - spikes in
    % it were already removed by batchProcessSpikesFromStim, so including it
    % would drag the post-stim rate down. Match the pre-stim window to the
    % same effective duration for a like-for-like rate comparison.
    artifactDuration = getStimArtifactDuration(Params);
    postStimWindow = [artifactDuration, Params.stimAnalysisWindow(2)];
    effectiveWindowDur = postStimWindow(2) - postStimWindow(1);
    preStimWindow = [-effectiveWindowDur, 0];

    if effectiveWindowDur <= 0
        error(['plotPrePostStimFR: the blanked artifact window (%.4f s) is at least ' ...
               'as long as the post-stimulus analysis window (%.4f s), leaving no ' ...
               'data to plot.'], artifactDuration, Params.stimAnalysisWindow(2));
    end

    spikeMethod = Params.SpikesMethod;
    
    preStimWindowDur = preStimWindow(2) - preStimWindow(1);
    postStimWindowDur = postStimWindow(2) - postStimWindow(1);
    
    preStimFR = zeros(numChannels, 1) + nan;
    postStimFR = zeros(numChannels, 1) + nan;
    
    
    for channelIdx= 1:numChannels
        channelSpikeTimes = spikeData.spikeTimes{channelIdx}.(spikeMethod);
        
        numSpikesPreStim = zeros(numStimEvent, 1) + nan;
        numSpikesPostStim = zeros(numStimEvent, 1) + nan;
    
        for stimEventIdx = 1:numStimEvent 
            stimTime = allStimTimes(stimEventIdx);
    
            numSpikesPreStim(stimEventIdx) = length(find(...
                (channelSpikeTimes >= stimTime + preStimWindow(1)) & ...
                (channelSpikeTimes <= stimTime + preStimWindow(2)) ...
                )); 
    
            numSpikesPostStim(stimEventIdx) = length(find(...
                (channelSpikeTimes >= stimTime + postStimWindow(1)) & ...
                (channelSpikeTimes <= stimTime + postStimWindow(2)) ...
                )); 
        end 
    
        preStimFR(channelIdx) = mean(numSpikesPreStim) / preStimWindowDur;
        postStimFR(channelIdx) = mean(numSpikesPostStim) / postStimWindowDur;
    end 

    prePostVals = [preStimFR, postStimFR];
    prePostMin = min(prePostVals(:)); 
    prePostMax = max(prePostVals(:));
    unityVals = linspace(prePostMin, prePostMax, 100);
    
    
    figureHandle = figure;
    set(figureHandle, 'Position', [100, 100, 400, 400]);
    scatter(preStimFR, postStimFR);
    hold on 
    plot(unityVals, unityVals, 'LineStyle', '--')
    xlabel('Pre-stim firing rate (spikes/s)')
    ylabel('Post-stim firing rate (spikes/s)')
    set(gcf, 'color', 'w')
    set(gca, 'TickDir', 'out');
    title(Info.FN{1}, 'Interpreter', 'none');

    % save figure
    
    % figName = '9_FR_before_after_stimulation';
    pipelineSaveFig(fullfile(figFolder, figName), Params.figExt, Params.fullSVG, gcf);
    close(figureHandle);  % Close the figure after saving
end

