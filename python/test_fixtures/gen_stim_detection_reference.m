function gen_stim_detection_reference()
% Generate ground-truth stim-detection fixtures by calling MEA-NAP's own
% detectStimTimes.m + getStimPatterns.m directly on the two testMEAstim raw
% recordings, replicating the params of the OutputData20Jul2026 reference run.
%
% detectStimTimes.m / getStimPatterns.m / checkStimPattern.m are identical on
% feat/plot-parity and origin/main, so the working-tree copies are used.
%
% Saves one -v7 .mat per recording into python/test_fixtures/ with per-channel
% stim times, pattern IDs, and the non-stim blank durations needed to derive
% blankDurMode / artifactDuration.

repo = '/home/timsit/MEA-NAP';
addpath(genpath(fullfile(repo, 'Functions')));

rawDir = fullfile(repo, 'local', 'testMEAstim');
outDir = fullfile(repo, 'python', 'test_fixtures');

recNames = {'OWT220207_1H_DIV57_HUB45_3UA', 'OWT220207_1H_DIV57_PER72_3UA'};

% Params for the reference run (from Parameters_OutputData20Jul2026.csv)
Params = struct();
Params.stimDetectionMethod  = 'longblank';
Params.stimDetectionVal     = 150;
Params.stimRefractoryPeriod = 2.9;
Params.stimDuration         = 0.00012;
Params.fs                   = 25000;
Params.minBlankingDuration  = 0.004;
Params.stimTimeDiffThreshold = 0.005;
Params.stimRawDataProcessing = 'none';
Params.verboseLevel         = 'Low';
Params.postStimWindowDur    = 0.5;   % ms

for r = 1:numel(recNames)
    name = recNames{r};
    fprintf('=== %s ===\n', name);
    S = load(fullfile(rawDir, [name '.mat']));   % dat, channels, fs
    rawData = S.dat;
    if strcmp(Params.stimRawDataProcessing, 'medianAbs')
        rawData = abs(rawData - median(rawData, 1));
    end
    channels = S.channels;
    numChannels = size(rawData, 2);
    coords = zeros(numChannels, 2);   % coords don't affect detection/patterns

    tic;
    stimInfo = detectStimTimes(rawData, Params, channels, coords);
    [stimInfo, stimPatterns] = getStimPatterns(stimInfo, Params);
    fprintf('  detection: %.1f s\n', toc);

    % Flatten per-channel outputs
    pattern            = zeros(numChannels, 1);
    numStimPerChannel  = zeros(numChannels, 1);
    elecStimTimes      = cell(numChannels, 1);
    nonStimBlankDurs   = [];   % pooled across channels (for blankDurMode)
    for c = 1:numChannels
        si = stimInfo{c};
        pattern(c)           = si.pattern;
        elecStimTimes{c}     = si.elecStimTimes(:)';
        numStimPerChannel(c) = numel(si.elecStimTimes);
        if isfield(si, 'nonStimBlankStarts') && isfield(si, 'nonStimBlankEnds')
            d = si.nonStimBlankEnds(:) - si.nonStimBlankStarts(:);
            nonStimBlankDurs = [nonStimBlankDurs; d];
        end
    end

    % blankDurMode = mode of non-stim blank durations (as in stimActivityAnalysis)
    if isempty(nonStimBlankDurs)
        blankDurMode = 0;
    else
        blankDurMode = mode(nonStimBlankDurs);
    end
    artifactDuration = blankDurMode + Params.postStimWindowDur / 1000;

    % Consolidated stim times of pattern-1 electrodes (the trial times used by
    % the population analysis). getStimPatterns groups electrodes; pattern 1's
    % representative times:
    if ~isempty(stimPatterns)
        pattern1Times = stimPatterns{1}(:)';
    else
        pattern1Times = [];
    end

    outPath = fullfile(outDir, [name '_stim_detection_reference.mat']);
    save(outPath, 'channels', 'pattern', 'numStimPerChannel', 'elecStimTimes', ...
         'blankDurMode', 'artifactDuration', 'pattern1Times', ...
         'nonStimBlankDurs', '-v7');
    fprintf('  saved %s (blankDurMode=%.6g, artifactDuration=%.6g, nPatterns=%d)\n', ...
            outPath, blankDurMode, artifactDuration, numel(stimPatterns));
end

fprintf('DONE\n');
end
