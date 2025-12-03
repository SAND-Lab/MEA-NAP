function [psth_data, metrics] = calculate_psth_metrics(all_spike_times_s, stim_times_s, window_s, bin_width_s, varargin)
% CALCULATE_PSTH_METRICS Extracts spikes in a given window relative to
% stimulus times, computes a histogram, generates a smoothed PSTH using
% ssvkernel or Gaussian smoothing, and calculates key metrics.
%
% INPUTS:
%   all_spike_times_s - Vector of all spike times in seconds.
%   stim_times_s      - Vector of stimulus event times in seconds.
%   window_s          - A 1x2 vector defining the time window relative to
%                       each stimulus [start, end] in seconds.
%   bin_width_s       - The bin width for the raw PSTH histogram in seconds.
%   varargin          - Optional name-value pairs:
%                       'smoothing_method': 'ssvkernel' (default) or 'gaussian'
%                       'gaussian_width_ms': Width of Gaussian kernel in ms (default: 2ms)
%                       'artifact_exclusion_duration_s': Duration of artifact exclusion from window start (default: 0)
%
% OUTPUTS:
%   psth_data         - A struct containing intermediate data:
%     .spikeTimes_byEvent - Cell array of spike times per trial.
%     .psth_samples       - Pooled vector of all spike times relative to stim.
%     .psth_histogram     - The raw histogram of firing rates.
%
%   metrics           - A struct containing the final calculated metrics:
%     .time_vector_s      - Time vector for the smoothed PSTH.
%     .psth_smooth        - The smoothed PSTH (firing rate in spikes/s).
%     .kernel_bandwidth_s - The adaptive kernel bandwidth from ssvkernel.
%     .auc                - Area under the curve of the smoothed PSTH.
%     .peak_firing_rate   - Peak firing rate of the smoothed PSTH.
%     .peak_time_s        - Time of the peak firing rate.

    % Parse optional inputs
    p = inputParser;
    addParameter(p, 'smoothing_method', 'ssvkernel', @(x) ismember(x, {'ssvkernel', 'gaussian'}));
    addParameter(p, 'gaussian_width_ms', 2, @(x) isscalar(x) && x > 0);
    addParameter(p, 'artifact_exclusion_duration_s', 0, @(x) isscalar(x) && x >= 0);
    parse(p, varargin{:});
    
    smoothing_method = p.Results.smoothing_method;
    gaussian_width_ms = p.Results.gaussian_width_ms;
    gaussian_width_s = gaussian_width_ms / 1000; % Convert to seconds
    artifact_exclusion_duration_s = p.Results.artifact_exclusion_duration_s;

    num_trials = length(stim_times_s);
    MIN_SPIKES_FOR_KDE = 5; % Set a threshold for minimum number of spikes to run ssvkernel

    % Extract spikes within the specified window for each trial
    out = WithinRanges(all_spike_times_s, stim_times_s + window_s, (1:num_trials)', 'matrix');
    spikeTimes_byEvent = arrayfun(@(n) all_spike_times_s(logical(out(:,n))) - stim_times_s(n), 1:num_trials, 'uni', 0)';
    
    % Apply artifact exclusion if specified
    if artifact_exclusion_duration_s > 0
        % Remove spikes within artifact exclusion period at start of window
        artifact_exclusion_start = window_s(1);
        artifact_exclusion_end = window_s(1) + artifact_exclusion_duration_s;
        
        for trial_idx = 1:length(spikeTimes_byEvent)
            trial_spikes = spikeTimes_byEvent{trial_idx};
            % Keep only spikes outside the artifact exclusion period
            valid_spikes = trial_spikes(trial_spikes < artifact_exclusion_start | trial_spikes > artifact_exclusion_end);
            spikeTimes_byEvent{trial_idx} = valid_spikes;
        end
    end
    
    psth_samples = cell2mat(spikeTimes_byEvent);

    % Create raw histogram
    edges_s = window_s(1):bin_width_s:window_s(2);
    if ~isempty(psth_samples)
        b = histc(psth_samples, edges_s);
        psth_histogram = b / (num_trials * bin_width_s);
    else
        psth_histogram = zeros(size(edges_s));
    end

    % Prepare outputs
    psth_data.spikeTimes_byEvent = spikeTimes_byEvent;
    psth_data.psth_samples = psth_samples;
    psth_data.psth_histogram = psth_histogram;

    % Smooth PSTH and calculate metrics
    L = 1000; % Number of points for smoothing
    t_s = linspace(window_s(1), window_s(2), L);
    
    if strcmp(smoothing_method, 'ssvkernel')
        % Use ssvkernel smoothing (adaptive bandwidth)
        if numel(psth_samples) >= MIN_SPIKES_FOR_KDE
            [yv_pdf, tv_s, optw_variable_s] = ssvkernel(psth_samples, t_s);
            
            avg_spikes_per_trial = length(psth_samples) / num_trials;
            yv = yv_pdf * avg_spikes_per_trial; % Convert density to rate
            
            metrics.time_vector_s = tv_s;
            metrics.psth_smooth = yv;
            metrics.kernel_bandwidth_s = optw_variable_s;
            metrics.auc = trapz(tv_s, yv);
            [metrics.peak_firing_rate, max_idx] = max(yv);
            metrics.peak_time_s = tv_s(max_idx);
        else
            % Handle case with too few spikes for reliable KDE
            metrics.time_vector_s = t_s;
            metrics.psth_smooth = zeros(1, L);
            metrics.kernel_bandwidth_s = zeros(1, L);
            metrics.auc = 0;
            metrics.peak_firing_rate = 0;
            metrics.peak_time_s = NaN;
        end
        
    elseif strcmp(smoothing_method, 'gaussian')
        % Use Gaussian kernel smoothing (fixed bandwidth)
        if ~isempty(psth_samples)
            % Create Gaussian kernel
            sigma_s = gaussian_width_s / (2 * sqrt(2 * log(2))); % Convert FWHM to sigma
            kernel_points = 5 * sigma_s / (t_s(2) - t_s(1)); % Kernel extends 5 sigma
            n_points = round(2*kernel_points)+1;
            % Ensure odd number of points to avoid indexing issues
            if mod(n_points, 2) == 0
                n_points = n_points + 1;
            end
            kernel_t = linspace(-5*sigma_s, 5*sigma_s, n_points);
            gaussian_kernel = exp(-0.5 * (kernel_t / sigma_s).^2) / (sigma_s * sqrt(2*pi));
            
            % Calculate spike density at each time point
            yv = zeros(size(t_s));
            for i = 1:length(psth_samples)
                spike_time = psth_samples(i);
                % Find closest time points and add Gaussian contribution
                [~, center_idx] = min(abs(t_s - spike_time));
                start_idx = max(1, center_idx - floor(length(kernel_t)/2));
                end_idx = min(length(t_s), center_idx + floor(length(kernel_t)/2));
                
                kernel_start = max(1, floor(length(kernel_t)/2) + 1 - (center_idx - start_idx));
                kernel_end = min(length(kernel_t), floor(length(kernel_t)/2) + 1 + (end_idx - center_idx));
                
                yv(start_idx:end_idx) = yv(start_idx:end_idx) + gaussian_kernel(kernel_start:kernel_end);
            end
            
            % Convert to firing rate (spikes/s)
            yv = yv / num_trials;
            
            metrics.time_vector_s = t_s;
            metrics.psth_smooth = yv;
            metrics.kernel_bandwidth_s = repmat(gaussian_width_s, 1, L); % Fixed bandwidth
            metrics.auc = trapz(t_s, yv);
            [metrics.peak_firing_rate, max_idx] = max(yv);
            metrics.peak_time_s = t_s(max_idx);
        else
            % Handle case with no spikes
            metrics.time_vector_s = t_s;
            metrics.psth_smooth = zeros(1, L);
            metrics.kernel_bandwidth_s = repmat(gaussian_width_s, 1, L);
            metrics.auc = 0;
            metrics.peak_firing_rate = 0;
            metrics.peak_time_s = NaN;
        end
    end
end
