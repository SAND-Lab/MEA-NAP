function propIncreased = computeTrialProportion(all_spike_times_s, allStimTimes, poststim_window_s, baseline_window_s)
% COMPUTETRIALPROPORTION Proportion of trials with more post-stim than pre-stim spikes.
%
% For a single electrode, this function:
% 1. For each stimulus trial, counts spikes in the pre-stim and post-stim windows.
% 2. Returns the proportion of trials where the post-stim spike count exceeds
%    the pre-stim spike count.
%
% Both windows are supplied explicitly and are expected to be of equal
% duration, so that raw spike counts are directly comparable. The caller is
% responsible for starting the post-stim window after the blanked artifact
% window (see getStimArtifactDuration) and matching the baseline duration
% to it.
%
% INPUTS
% ------
% all_spike_times_s : double vector
%     Vector of spike times in seconds for one electrode.
% allStimTimes : double vector
%     All stimulation event times in seconds to align to.
% poststim_window_s : [1 x 2] double
%     Post-stimulus window [start, end] in seconds relative to stim times.
% baseline_window_s : [1 x 2] double
%     Window for baseline (pre-stim) spike counting [start, end] in seconds.
%
% OUTPUTS
% -------
% propIncreased : double
%     Proportion of trials where post-stim spike count > pre-stim spike count.
%     Returns 0 if no spikes or no trials.

    if isempty(all_spike_times_s) || isempty(allStimTimes)
        propIncreased = 0;
        return;
    end

    numTrials = length(allStimTimes);
    postGreaterCount = 0;

    for trialIdx = 1:numTrials
        stimTime = allStimTimes(trialIdx);

        % Pre-stim spike count
        preStart = stimTime + baseline_window_s(1);
        preEnd   = stimTime + baseline_window_s(2);
        nPre = sum(all_spike_times_s >= preStart & all_spike_times_s < preEnd);

        % Post-stim spike count (window starts after the blanked artifact)
        postStart = stimTime + poststim_window_s(1);
        postEnd   = stimTime + poststim_window_s(2);
        nPost = sum(all_spike_times_s >= postStart & all_spike_times_s < postEnd);

        if nPost > nPre
            postGreaterCount = postGreaterCount + 1;
        end
    end

    propIncreased = postGreaterCount / numTrials;
end
