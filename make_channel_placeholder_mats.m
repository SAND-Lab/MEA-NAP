function make_channel_placeholder_mats(spikeDataFolder, outputFolder)
% MAKE_CHANNEL_PLACEHOLDER_MATS Create tiny "<name>.mat" stand-ins for MEA-NAP's
% `rawData` folder when you only have pre-existing "<name>_spikes.mat" files
% and no original raw recording.
%
% Why this is needed: setUpSpreadSheet.m (called for every MEA-NAP run,
% including headless Step-2-onward runs) reads a `channels` variable from
% fullfile(rawData, [ExpName '.mat']) for every recording in the batch CSV,
% to build Params.channels/Params.coords. It does NOT read the voltage trace,
% only `channels` -- so a few-KB file containing just that variable is enough.
%
% This script copies `channels` straight out of each recording's own
% "<name>_spikes.mat" (the same file MEA-NAP's Step 2 already loads it from
% via Functions/formatSpikeTimes.m), so the two are guaranteed consistent.
%
% Parameters
% ----------
% spikeDataFolder : path to folder containing "<name>_spikes.mat" files
% outputFolder    : path to write "<name>.mat" placeholder files to
%                   (point MEApipeline_headless_fromStep2.m's `rawData` here)
%
% Example
% -------
% make_channel_placeholder_mats('/path/to/SpikeDetectedData', '/path/to/ChannelPlaceholders')

if ~isfolder(outputFolder)
    mkdir(outputFolder)
end

spikeFiles = dir(fullfile(spikeDataFolder, '*_spikes.mat'));
fprintf('Found %d spike files in %s\n', length(spikeFiles), spikeDataFolder);

for i = 1:length(spikeFiles)
    spikeFname = spikeFiles(i).name;
    recordingName = erase(spikeFname, '_spikes.mat');
    outPath = fullfile(outputFolder, [recordingName '.mat']);

    if isfile(outPath)
        fprintf('  [%d/%d] %s -> already exists, skipping\n', i, length(spikeFiles), recordingName);
        continue
    end

    s = load(fullfile(spikeDataFolder, spikeFname), 'channels');
    if ~isfield(s, 'channels')
        error('%s has no ''channels'' variable -- cannot build a placeholder for it', spikeFname);
    end
    channels = s.channels;
    save(outPath, 'channels');
    fprintf('  [%d/%d] %s -> %s (%d channels)\n', i, length(spikeFiles), recordingName, outPath, numel(channels));
end

fprintf('Done. Wrote placeholders to %s\n', outputFolder);

end
