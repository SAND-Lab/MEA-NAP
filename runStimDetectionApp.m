function runStimDetectionApp(MEANAPapp)
%RUNSTIMDETECTIONAPP Summary of this function goes here
%   Detailed explanation goes here
% MEANAPapp : app object 
% Main MEANAP application object, to sync settings / parameters across
% these two apps

stimDetectionAppObj = stimDetectionApp;
stimDetectionAppObj.UIFigure.Name = 'Stim Detection';

%% Move settings from MEA-NAP GUI to this GUI 
stimDetectionAppObj.StimdetectionmethodDropDown.Items = MEANAPapp.StimdetectionmethodDropDown.Items;
stimDetectionAppObj.StimdetectionmethodDropDown.Value = MEANAPapp.StimdetectionmethodDropDown.Value;

stimDetectionAppObj.StimrefractoryperiodsEditField.Value = MEANAPapp.StimrefractoryperiodsEditField.Value;

stimDetectionAppObj.StimDurationForPlotsEditField.Value = MEANAPapp.StimdurationforplotssEditField.Value;

stimDetectionAppObj.DetectionvalueEditField.Value = MEANAPapp.DetectionthresholdmultiplierEditField.Value;

stimDetectionAppObj.SamplingrateHzEditField.Value = MEANAPapp.SamplingFrequencyEditField.Value;

%% Set up original parameters (to see what is changed)
dataFpath = stimDetectionAppObj.DatapathEditField.Value;  % raw data path 
stimThreshold = stimDetectionAppObj.DetectionvalueEditField.Value; 
channelToPlot = stimDetectionAppObj.ChannelDropDown.Value;
fs = stimDetectionAppObj.SamplingrateHzEditField.Value;
stimDetectionMethod = stimDetectionAppObj.StimdetectionmethodDropDown.Value;

% Same left position 
stimDetectionAppObj.UIAxes_2.Position(1) = stimDetectionAppObj.UIAxes.Position(1);

% Same width 
stimDetectionAppObj.UIAxes_2.Position(3) = stimDetectionAppObj.UIAxes.Position(3);



%% Run app 
while isvalid(stimDetectionAppObj)
   
    % Output folder selection button 
    if stimDetectionAppObj.SelectfileButton.Value == 1
        [baseName, folder] = uigetfile();
        fullFileName = fullfile(folder, baseName);
        stimDetectionAppObj.DatapathEditField.Value = fullFileName;
        stimDetectionAppObj.SelectfileButton.Value = 0;
        figure(stimDetectionAppObj.UIFigure)  % put app back to focus
    end 

    dataFpathChanged = ~strcmp(dataFpath, stimDetectionAppObj.DatapathEditField.Value);
    stimThresholdChanged = (stimThreshold ~= stimDetectionAppObj.DetectionvalueEditField.Value);
    selectedChannelChanged = ~strcmp(channelToPlot, stimDetectionAppObj.ChannelDropDown.Value);
    fsChanged = ~(stimDetectionAppObj.SamplingrateHzEditField.Value == fs);
    stimDetectionMethodChanged = ~strcmp(stimDetectionMethod,  stimDetectionAppObj.StimdetectionmethodDropDown.Value);

    if dataFpathChanged
        dataFpath = stimDetectionAppObj.DatapathEditField.Value;
        % load raw data
        rawData = load(dataFpath);

        % update possible channels 
        possibleChannels = sort(rawData.channels);
        possibleChannelsCell = arrayfun(@num2str, possibleChannels, 'UniformOutput', 0);
        stimDetectionAppObj.ChannelDropDown.Items = possibleChannelsCell;
        
        % update sampling rate
        if isfield(rawData, 'fs')
            stimDetectionAppObj.SamplingrateHzEditField.Value = rawData.fs;
        end

    end 

    if fsChanged
        fs = stimDetectionAppObj.SamplingrateHzEditField.Value;
        MEANAPapp.SamplingFrequencyEditField.Value = stimDetectionAppObj.SamplingrateHzEditField.Value;
    end

    % Update detection parameters to GUI
    if stimThresholdChanged
        MEANAPapp.DetectionthresholdmultiplierEditField.Value = stimDetectionAppObj.DetectionvalueEditField.Value;
    end
    
    if stimDetectionMethodChanged
        stimDetectionMethod = stimDetectionAppObj.StimdetectionmethodDropDown.Value;
        MEANAPapp.StimdetectionmethodDropDown.Value = stimDetectionMethod;
    end

    if stimThresholdChanged || dataFpathChanged || fsChanged || stimDetectionMethodChanged
        Params = getParamsFromApp(MEANAPapp);
        stimInfo = detectStimTimes(rawData.dat, Params, rawData.channels, Params.coords);
        [stimInfo, stimPatterns] = getStimPatterns(stimInfo, Params);
        numStimPatterns = length(stimPatterns);
        
        % Plot stim detection heatmap  (TODO: add channel name)
        cla(stimDetectionAppObj.UIAxes2) 
        numNodes = length(stimInfo);
        nodeScaleF = 1;
        
        numStimElectrodes = 0;
        for nodeIdx = 1:numNodes
            xc = stimInfo{nodeIdx}.coords(1);
            yc = stimInfo{nodeIdx}.coords(2);
            circlePos =  [xc - (0.5*nodeScaleF), yc - (0.5*nodeScaleF), nodeScaleF, nodeScaleF];
        
            if length(stimInfo{nodeIdx}.elecStimTimes) == 0
                nodeColor = 'white';
                textColor = 'black';
            else 
                nodeColor = Params.stimPatternColors{stimInfo{nodeIdx}.pattern};
                textColor = 'white';
                numStimElectrodes = numStimElectrodes + 1;
            end
            rectangle(stimDetectionAppObj.UIAxes2, 'Position', circlePos,'Curvature',[1 1],'FaceColor',nodeColor,'EdgeColor','black','LineWidth', 1) 
            text(stimDetectionAppObj.UIAxes2, xc - (0.3*nodeScaleF), yc, num2str(stimInfo{nodeIdx}.channelName), 'Color', textColor);
        end
        title(stimDetectionAppObj.UIAxes2, '');
        


        % Update text
        channelToPlot = stimDetectionAppObj.ChannelDropDown.Value;
        channelIdxToPlot = find(rawData.channels == str2num(channelToPlot));
        elecStimTimes = stimInfo{channelIdxToPlot}.elecStimTimes;
        elecNumStimEvents = length(elecStimTimes); 
        stimDetectionAppObj.Numberofstimeventsdetected0Label.Text = sprintf('Number of stim events detected: %.f', elecNumStimEvents);
        stimDetectionAppObj.Numberofstimulationelectrodes0Label.Text = sprintf('Number of stimulation electrodes: %.f', numStimElectrodes);
        stimDetectionAppObj.Numberofstimulationpatterns0Label.Text = sprintf('Number of stimulation patterns: %.f', length(stimPatterns)); 
        
    end

    if stimThresholdChanged || selectedChannelChanged || dataFpathChanged
        Params = getParamsFromApp(MEANAPapp);
        % Plot stim detection trace
        stimResamplingHz = 1000;
        numTimeSamples = size(rawData.dat, 1);
        stimDataDurS = numTimeSamples / rawData.fs;
        stimResampleN = round(stimDataDurS * stimResamplingHz);
        stimResampleTimes = linspace(0, stimDataDurS, stimResampleN);

        channelToPlot = stimDetectionAppObj.ChannelDropDown.Value;
        channelIdxToPlot = find(rawData.channels == str2num(channelToPlot));
        
        stimVector = zeros(stimResampleN, 1);
        
        elecStimTimes = stimInfo{channelIdxToPlot}.elecStimTimes;
        % elecStimDur = stimInfo{channelIdx}.elecStimDur;
        elecStimDur = Params.stimDurationForPlotting;
        for stimIdx = 1:length(elecStimTimes)
                
            stimLoc = find(stimResampleTimes >= elecStimTimes(stimIdx) & ...
                (stimResampleTimes) <= elecStimTimes(stimIdx) + elecStimDur ...
                );
            stimVector(stimLoc) = 1;
        end
    
   
        plot(stimDetectionAppObj.UIAxes_2, stimResampleTimes, stimVector)
        title(stimDetectionAppObj.UIAxes_2, '');
        ylim(stimDetectionAppObj.UIAxes_2, [-0.5, 1.5]);
        linkaxes([stimDetectionAppObj.UIAxes, stimDetectionAppObj.UIAxes_2], 'x')
        xlabel(stimDetectionAppObj.UIAxes_2, 'Time (s)')
        ylabel(stimDetectionAppObj.UIAxes_2, 'Stimulation')
        % Adjust plot size
        % Get y axis extent
        ax1LabelWidth = stimDetectionAppObj.UIAxes.YLabel.Extent(3);
        ax2LabelWidth = stimDetectionAppObj.UIAxes_2.YLabel.Extent(3);
        
        if ax1LabelWidth > ax2LabelWidth
            labelDiff = ax1LabelWidth - ax2LabelWidth;
            stimDetectionAppObj.UIAxes_2.Position(1) = stimDetectionAppObj.UIAxes_2.Position(1) + labelDiff;
            stimDetectionAppObj.UIAxes_2.Position(3) = stimDetectionAppObj.UIAxes_2.Position(3) - labelDiff;
        end
        
        % Update num stim events detected txt
        channelToPlot = stimDetectionAppObj.ChannelDropDown.Value;
        channelIdxToPlot = find(rawData.channels == str2num(channelToPlot));
        elecStimTimes = stimInfo{channelIdxToPlot}.elecStimTimes;
        elecNumStimEvents = length(elecStimTimes); 
        stimDetectionAppObj.Numberofstimeventsdetected0Label.Text = sprintf('Number of stim events detected: %.f', elecNumStimEvents);
        
        % Plot entire stimulation trace
        cla(stimDetectionAppObj.UIAxes3);
        numTimeSamples = size(rawData.dat, 1);
        stimDataDurS = numTimeSamples / Params.fs;
        stimResampleN = round(stimDataDurS * stimResamplingHz);
        stimResampleTimes = linspace(0, stimDataDurS, stimResampleN);
        
        for channelIdx = 1:length(stimInfo)
            
            stimVector = zeros(stimResampleN, 1);
            
            elecStimTimes = stimInfo{channelIdx}.elecStimTimes;
            % elecStimDur = stimInfo{channelIdx}.elecStimDur;
            elecStimDur = Params.stimDurationForPlotting;
            for stimIdx = 1:length(elecStimTimes)
                    
                stimLoc = find(stimResampleTimes >= elecStimTimes(stimIdx) & ...
                    (stimResampleTimes) <= elecStimTimes(stimIdx) + elecStimDur ...
                    );
                stimVector(stimLoc) = 1;
            end
        
        
            vert_offset = channelIdx * 1.2;
            if numStimPatterns >= 2
                % Plot with pattern color 
                if stimInfo{channelIdx}.pattern == 0
                    patternColor = [0.75, 0.75, 0.75];  % light gray
                else
                    patternColor = Params.stimPatternColors{stimInfo{channelIdx}.pattern};
                end 
                plot(stimDetectionAppObj.UIAxes3, stimResampleTimes, stimVector + vert_offset, 'Color', patternColor)
            else 
                % Plot with no color specified
                plot(stimDetectionAppObj.UIAxes3, stimResampleTimes, stimVector + vert_offset)
            end
            
            hold(stimDetectionAppObj.UIAxes3, 'on')
        
            % Text label of channel idx 
            % text(stimDetectionAppObj.UIAxes3, -1, vert_offset + 0.5, num2str(channelIdx), 'HorizontalAlignment', 'right');
            % Text label of channel name
            % text(stimDetectionAppObj.UIAxes3, stimDataDurS+1, vert_offset + 0.5, num2str(stimInfo{channelIdx}.channelName));
        end
        yticks(stimDetectionAppObj.UIAxes3, [])
        ylabel(stimDetectionAppObj.UIAxes3, 'Channel (with some vertical offset)');
        xlabel(stimDetectionAppObj.UIAxes3, 'Time (sec)');
        title(stimDetectionAppObj.UIAxes3, '');
        % set(gcf, 'color', 'white')
        % set(stimDetectionAppObj.UIAxes3, 'TickDir', 'out')
        % stimDetectionAppObj.UIAxes3.YAxis.Visible = 'off'; 
    
    end
    
    % Plot channel raw trace
    if selectedChannelChanged || stimThresholdChanged || dataFpathChanged
        
        channelToPlot = stimDetectionAppObj.ChannelDropDown.Value;
        channelIdxToPlot = find(rawData.channels == str2num(channelToPlot));
        stimThreshold = stimDetectionAppObj.DetectionvalueEditField.Value;

        numTimeSamples = size(rawData.dat, 1);
        timeStampInSec = (1:numTimeSamples) ./ rawData.fs;
        
        cla(stimDetectionAppObj.UIAxes) 
        plot(stimDetectionAppObj.UIAxes, timeStampInSec, rawData.dat(:, channelIdxToPlot));
        hold(stimDetectionAppObj.UIAxes, 'on')
        plot(stimDetectionAppObj.UIAxes, timeStampInSec, repmat(stimThreshold, 1, numTimeSamples));
        xlabel(stimDetectionAppObj.UIAxes, 'Time (s)');
        ylabel(stimDetectionAppObj.UIAxes, 'Raw signal')
        title(stimDetectionAppObj.UIAxes, sprintf('Channel %s', channelToPlot))
        
        % Adjust plot size
        % Get y axis extent
        ax1LabelWidth = stimDetectionAppObj.UIAxes.YLabel.Extent(3);
        ax2LabelWidth = stimDetectionAppObj.UIAxes_2.YLabel.Extent(3);
        
        if ax1LabelWidth > ax2LabelWidth
            labelDiff = ax1LabelWidth - ax2LabelWidth;
            stimDetectionAppObj.UIAxes_2.Position(1) = stimDetectionAppObj.UIAxes_2.Position(1) + labelDiff;
            stimDetectionAppObj.UIAxes_2.Position(3) = stimDetectionAppObj.UIAxes_2.Position(3) - labelDiff;
        end
        
    end




    pause(0.1);

    
    

end



end

