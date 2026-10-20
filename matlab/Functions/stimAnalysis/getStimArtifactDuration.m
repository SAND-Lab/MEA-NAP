function artifactDuration = getStimArtifactDuration(Params)
% GETSTIMARTIFACTDURATION  Duration (s) blanked out after each stimulus.
%
% Spikes between the stimulus onset and the end of this window have already
% been removed by batchProcessSpikesFromStim (see allArtifactWindowEnd
% there), so any post-stimulus spike count must start after it, otherwise
% the window includes a stretch that is empty by construction.
%
% The duration is the blank itself plus the post-stim ignore window set in
% the app. For the 'longblank' detection method blankDurMode is the mode of
% the non-stim blank durations; for axionStimEvents each blank has zero
% duration and only the ignore window applies.
%
% INPUT
% -----
% Params : struct
%     Uses .artifactDuration_s if already computed, otherwise
%     .blankDurMode (s) and .postStimWindowDur (ms). Missing fields are
%     treated as zero.
%
% OUTPUT
% ------
% artifactDuration : double, seconds

    if isfield(Params, 'artifactDuration_s') && ~isempty(Params.artifactDuration_s)
        artifactDuration = Params.artifactDuration_s;
        return;
    end

    if isfield(Params, 'blankDurMode') && ~isempty(Params.blankDurMode)
        blankDur = Params.blankDurMode;
    else
        blankDur = 0;
    end

    if isfield(Params, 'postStimWindowDur') && ~isempty(Params.postStimWindowDur)
        ignoreDur = Params.postStimWindowDur / 1000;
    else
        ignoreDur = 0;
    end

    artifactDuration = blankDur + ignoreDur;

end
