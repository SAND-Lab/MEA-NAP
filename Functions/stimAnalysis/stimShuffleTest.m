function shuffleResults = stimShuffleTest(spikeData, allStimTimes, Params, Info)
% STIMSHUFFLETEST  Circular-shift shuffle test for trial proportion significance.
%
% Builds a null distribution of trial proportion values by circularly
% shifting each electrode's spike times by a random offset (with
% wrap-around within the recording duration), then recomputing the
% proportion of trials where post-stim spike count > pre-stim spike count.
% Significance is assessed per electrode with a one-tailed (upper) test
% (p < 0.05): an electrode is significant if its observed proportion falls
% in the top 5% of the null distribution, i.e. above the empirical 95th
% percentile. No multiple-comparison correction is applied.
%
% The metric for each electrode is: proportion of trials where the number
% of spikes in the post-stimulus window exceeds the number of spikes in
% the pre-stimulus (baseline) window.
%
% INPUTS
% ------
% spikeData : struct
%     Must contain:
%       .spikeTimes  - cell array {1 x numChannels}, each entry is a struct
%                      with a field named Params.SpikesMethod containing a
%                      vector of spike times in seconds.
%       .stimInfo    - cell array {1 x numChannels} with stimulation info
%                      (used only for numChannels).
% allStimTimes : double vector
%     All stimulation event times in seconds to align to.
% Params : struct
%     Must contain:
%       .SpikesMethod          - string, field name for spike times
%       .stimAnalysisWindow    - [preStart, postEnd] in seconds (e.g. [-0.5 1])
%     Optional:
%       .Nshuffles             - number of circular-shift shuffles.
%                                Default: 500
%       .shuffleAlpha          - significance level for the two-tailed test.
%                                Default: 0.05
% Info : struct
%     Must contain:
%       .duration_s - recording duration in seconds (for wrap-around)
%
% OUTPUTS
% -------
% shuffleResults : struct with the following fields
%   .trialProp_obs     - [numChannels x 1] observed trial proportion for each electrode
%   .trialProp_null    - [numChannels x Nshuffles] null trial proportion distributions
%   .pctile_lo         - [numChannels x 1] lower percentile bound (5th, display only)
%   .pctile_hi         - [numChannels x 1] upper percentile bound (95th, significance threshold)
%   .isSigLo           - [numChannels x 1] logical, always false (lower tail not tested)
%   .isSigHi           - [numChannels x 1] logical, true if trialProp_obs > pctile_hi
%   .isSignificant     - [numChannels x 1] logical, true if significant (upper tail only)
%   .Nshuffles         - scalar, number of shuffles performed
%   .alpha             - scalar, significance level used
%   .postStimWindow    - [1 x 2] the post-stimulus window used
%
% PROCEDURE
% ---------
% 1. Compute observed trial proportion for each electrode.
% 2. For each shuffle iteration:
%      a. For each electrode, circularly shift its spike train by a random
%         offset uniformly drawn from (0, recordingDuration) with wrap-around.
%      b. Recompute the trial proportion for every electrode using the
%         shifted spike times aligned to the *original* stim times.
% 3. For each electrode, determine the 95th percentile of its null trial
%    proportion distribution (the 5th percentile is also stored for plotting).
% 4. Mark an electrode as significant if observed trial proportion exceeds
%    the 95th percentile of the null (top 5%, upper tail only).
%
% REFERENCE
% ---------
% Circular-shift approach inspired by adjM_thr_parallel.m (STTC thresholding).
%
% Authors: GitHub Copilot & MEA-NAP team
% Date:    March 2026

%% Parse optional parameters
if ~isfield(Params, 'Nshuffles') || isempty(Params.Nshuffles)
    Nshuffles = 500;
else
    Nshuffles = Params.Nshuffles;
end

if ~isfield(Params, 'shuffleAlpha') || isempty(Params.shuffleAlpha)
    alpha = 0.05;
else
    alpha = Params.shuffleAlpha;
end

%% Setup
numChannels = length(spikeData.stimInfo);
duration_s = Info.duration_s;

% Analysis windows (matching stimActivityAnalysis.m)
psth_window_s = Params.stimAnalysisWindow;  % Full analysis window
poststim_duration_s = psth_window_s(2) - 0;  % Duration from stimulus to end of post-stim window
baseline_window_s = [-poststim_duration_s, 0];  % Baseline window (same duration as post-stim)

%% 1. Compute observed trial proportion
spikeMethod = Params.SpikesMethod;
trialProp_obs = computeTrialProportionForEachChannel(spikeData.spikeTimes, allStimTimes, ...
    psth_window_s, baseline_window_s, numChannels, spikeMethod);

%% 2. Build null distribution via circular shift
trialProp_null = zeros(numChannels, Nshuffles);

% Check for Parallel Computing Toolbox
matlabInstallation = ver;
toolboxNames = {matlabInstallation.Name};
parallelToolboxInstalled = any(strcmp(toolboxNames, 'Parallel Computing Toolbox'));

if parallelToolboxInstalled
    parfor shuffleIdx = 1:Nshuffles
        % Create shifted copy of spike times
        shuffledSpikeTimes = spikeData.spikeTimes;  %#ok<PFBNS>
        for chIdx = 1:numChannels
            chSpikes = shuffledSpikeTimes{chIdx}.(spikeMethod);  %#ok<PFBNS>
            % Random circular shift: uniform in (0, duration_s)
            delta = rand() * duration_s;  %#ok<PFBNS>
            shiftedSpikes = chSpikes + delta;
            % Wrap around
            shiftedSpikes(shiftedSpikes > duration_s) = shiftedSpikes(shiftedSpikes > duration_s) - duration_s;
            shiftedSpikes = sort(shiftedSpikes);
            shuffledSpikeTimes{chIdx}.(spikeMethod) = shiftedSpikes;
        end
        trialProp_null(:, shuffleIdx) = computeTrialProportionForEachChannel(shuffledSpikeTimes, ...
            allStimTimes, psth_window_s, baseline_window_s, ...
            numChannels, spikeMethod);  %#ok<PFBNS>
    end
else
    for shuffleIdx = 1:Nshuffles
        shuffledSpikeTimes = spikeData.spikeTimes;
        for chIdx = 1:numChannels
            chSpikes = shuffledSpikeTimes{chIdx}.(spikeMethod);
            delta = rand() * duration_s;
            shiftedSpikes = chSpikes + delta;
            shiftedSpikes(shiftedSpikes > duration_s) = shiftedSpikes(shiftedSpikes > duration_s) - duration_s;
            shiftedSpikes = sort(shiftedSpikes);
            shuffledSpikeTimes{chIdx}.(spikeMethod) = shiftedSpikes;
        end
        trialProp_null(:, shuffleIdx) = computeTrialProportionForEachChannel(shuffledSpikeTimes, ...
            allStimTimes, psth_window_s, baseline_window_s, ...
            numChannels, spikeMethod);
    end
end

%% 3. Determine significance per electrode (one-tailed, upper)
% An electrode is significant if its observed proportion falls in the top
% alpha (5%) of the null distribution, i.e. above the (1 - alpha) percentile.
% The lower percentile is computed for visualising the null spread only.
hi_pctile = (1 - alpha) * 100;          % 95
lo_pctile = alpha * 100;                % 5 (display only)

pctile_lo = prctile(trialProp_null, lo_pctile, 2);  % [numChannels x 1], display only
pctile_hi = prctile(trialProp_null, hi_pctile, 2);

isSigHi = trialProp_obs > pctile_hi;
isSigLo = false(numChannels, 1);        % lower tail not tested
isSignificant = isSigHi;

%% 4. Package output
shuffleResults.trialProp_obs    = trialProp_obs;
shuffleResults.trialProp_null   = trialProp_null;
shuffleResults.pctile_lo        = pctile_lo;
shuffleResults.pctile_hi        = pctile_hi;
shuffleResults.isSigLo          = isSigLo;
shuffleResults.isSigHi          = isSigHi;
shuffleResults.isSignificant    = isSignificant;
shuffleResults.Nshuffles        = Nshuffles;
shuffleResults.alpha            = alpha;
shuffleResults.postStimWindow   = [0, psth_window_s(2)];

end
