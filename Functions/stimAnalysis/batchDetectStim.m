function batchDetectStim(ExpName, Params, app)
%BATCHDETECTSTIM Summary of this function goes here
%   Detailed explanation goes here

if Params.guiMode == 1
   app.MEANAPStatusTextArea.Value = [app.MEANAPStatusTextArea.Value; ...
   sprintf('Running stimulus detection')];
end

spikeDetectionFolder = fullfile(Params.outputDataFolder, ...
            Params.outputDataFolderName, '1_SpikeDetection', '1A_SpikeDetectedData');

experimentMatFileFolder = fullfile(Params.outputDataFolder, ...
            Params.outputDataFolderName, 'ExperimentMatFiles');

stimDetectionFolder = fullfile(Params.outputDataFolder, ...
            Params.outputDataFolderName, '1_SpikeDetection', '1C_StimDetectionChecks');
if ~isfolder(stimDetectionFolder)
    mkdir(stimDetectionFolder)
end 

for expIdx = 1:length(ExpName)

    stimRawData = load(fullfile(Params.rawData, ExpName{expIdx}));
    rawData = stimRawData.dat;

    if strcmp(Params.stimRawDataProcessing, 'medianAbs')
        rawData = abs(rawData - median(rawData, 1));
    end

    stimInfo = detectStimTimes(rawData, Params, stimRawData.channels, Params.coords{expIdx});
    [stimInfo, stimPatterns] = getStimPatterns(stimInfo, Params);

    % save stimInfo to spike data
    spikeDetectionFilePath = fullfile(spikeDetectionFolder, [ExpName{expIdx} '_spikes.mat']);
    save(spikeDetectionFilePath, 'stimInfo', 'stimPatterns', '-append');

    % plot stim detection check (better to do it here since we have
    % filteredData already)
    experimentMatFilePath = fullfile(experimentMatFileFolder, ...
            strcat(char(ExpName(expIdx)),'_',Params.outputDataFolderName,'.mat'));
    expInfo = load(experimentMatFilePath,'Info');
    stimGenotypeSubFolder = fullfile(stimDetectionFolder, expInfo.Info.Grp{1});
    if ~isfolder(stimGenotypeSubFolder)
        mkdir(stimGenotypeSubFolder)
    end 

    expSubFolder = fullfile(stimGenotypeSubFolder, expInfo.Info.FN{1});
    if ~isfolder(expSubFolder)
        mkdir(expSubFolder)
    end

    % Plot stim detection checks
    plotStimDetectionChecks(rawData, stimInfo, expSubFolder, Params);

end

end

