%% Finding the best cost parameter L for each recording 
%{
Parameters 
------------
wavelet_spike_folder : (str)
    directory containing wavelet spike detection results.
    If you are not using wavelet spike detection, then leave it as an empty
    string ''
threshold_spike_folder : (str)
    directory containing threshold spike detection results.
    If you are not using wavelet spike detection, then leave it as an empty
    string ''
summary_plot_folder : (str)
    directory which you want save the summary plot for each recording, and
    the csv table that summarises properties of each file (best param file,
    number of active electrodes etc.)
max_tolerable_spikes_in_TTX_abs : (int)
    maximum tolerable spikes in all TTX recording electrode (summed) to
    allow during the selection of the cost parameter.
    If duration is not specified, then this is absolute number (meaning
    100/ 600 sec). This parameter is ignored if duration of the recording
    is provided, as the code will use `max_tolerable_spikes_in_TTX_per_s` 
    instead. 
max_tolerable_spikes_in_grounded_abs : (int)
    maximum tolerable number of spikes in grounded electrode(s).
regularisation_param : (float)
    regurlaisation parameter for calculating spike ratio between actual 
    recording and control (either TTX recording or grounded electrode or 
    WIP: electrode with no spikes but similar noise statsitics)
    this is currently in terms of absolute number of spikes in the 
    entire erecording
spike_time_unit : (str)
    option 1: 'frame', spike time are in frame numbers (int)
    option 2: 'sec', spike time are in seconds (float)
start_time : (float)
    starting time of the recording
    should be 0 in most cases unless you only want to look at a subset
    of the recording. 
default_end_time : (float)
    the default end time of the recording of 'duration' parameter 
    is not found in the spike detection result file.
wavelet_to_search : (cell containing str)
    set of wavelets to look at, currently only supports single 
    wavelets, and 'mea' is probably your best bet. 
threshold_ground_electrode_name : (int)
    name (electrode number) of the grounded electrode, if you are using 
    the threshold spike detection method. (2021-04-15: defunct, TODO: clean up)
default_grounded_electrode_name : (int)
    name (electrode number) of the grounded electrode(s), if you are using
    the wavelet spike detection method.
sampling_rate : (int)
    sampling rate to reduce the spike times to to look at overall variation
    in spike activity over time. In samples / second, usually `1` will do
    (ie. you look at how many spikes per 1 second time bin)
    (NOT to be confused with the  recording sampling rate `recording_fs`,
    which is extracted from the parameter)
Outputs 
---------------
figures : (.png)
    this script saves a set of .png figure files summarising the spike 
    statistics for each recording (across cost parameters)
.csv file


Usage instructions 
---------------------
Parameters to modify: 

(1) wavelet_spike_folder : where the spike detection results are held
(2) summary_plot_folder : where you want the code to save the summary plots
(3) wavelet_to_search : which wavelet spike detection method(s) you want to find the best L
parameters 
(4) spike_time_unit : whether spike times are specified in frames or
seconds

raw_data_folder can be kept empty for current purposes.

2021-04-15: Please don't close the figure(s) whilst the code is running,
currently the code works by saving the current figure through a loop.


Known issues / TODOs
--------------------
** The script currently only searches through the mea method
** The script assumes a specific file name structure (so it can tell which 
files are from the same recording but using the same paraemters), and 
currently does not work with 190830_slice1stim..., should be an easy fix
** Future versions of this code will find the best L per electrode.

Last update: Tim Sit 2021-04-15
%}

%% Define file to find best params, and parameters 
raw_data_folder = '';
wavelet_spike_folder = '/media/timsit/Seagate Expansion Drive/The_Organoid_Project/data/all_mat_files/test-detection/results/';
summary_plot_folder = '/media/timsit/Seagate Expansion Drive/The_Organoid_Project/data/all_mat_files/test-detection/results/plots/';

if not(isfolder(wavelet_spike_folder))
    fprintf('Spike detection result folder is not a folder, please doubel check your entry \n')
end 

if not(isfolder(summary_plot_folder))
    fprintf('Specified summary plot folder does not exist, I will create it \n')
    mkdir(summary_plot_folder)
end 

max_tolerable_spikes_in_TTX_abs = 100; 
max_tolerable_spikes_in_grounded_abs = 100;
max_tolerable_spikes_in_TTX_per_s = 1; 
max_tolerable_spikes_in_grounded_per_s = 1;

start_time = 0;
% end_time = 600;
default_end_time = 600;  % end time to use if none is found in the param file
sampling_rate = 1;  % new sampling rate for conversion to spike matrix, to plot activity over time
threshold_ground_electrode_name = 15;
default_grounded_electrode_name = 15;
min_spike_per_electrode_to_be_active = 0.5;
wavelet_to_search = {'mea', 'bior1p5'};
use_TTX_to_tune_L_param = 0;
spike_time_unit = 'frame'; % Whether spike times are in terms of frames ('frame') or seconds ('sec')
custom_backup_param_to_use = [];  % lost param to use in case there is no TTX file
% if empty, then looks as the grounded electrode instead
regularisation_param = 10;

%% Loop through each file 

if isempty(raw_data_folder)
    if ~isempty(wavelet_spike_folder)
        fprintf('No raw data folder specified, getting recording names from wavelet spike results \n');
        recording_names = {dir([wavelet_spike_folder '*.mat']).name};
        for name_idx = 1:length(recording_names)
            recording_names{name_idx} = extractBefore(recording_names{name_idx}, '_L');
        end 
        recording_names = unique(recording_names);
    end    
else
    recording_names = {dir([raw_data_folder '*.mat']).name};
end 
recording_names_exclude_TTX = {};
selected_detection_method = {};


for r_name_idx = 1:length(recording_names)
    if ~contains(recording_names{r_name_idx}, 'TTX')
        recording_names_exclude_TTX{end+1} = recording_names{r_name_idx};

    end 
end 

TTX_used = num2cell(zeros(length(recording_names_exclude_TTX), 1));  % This can be pre-allocated
best_param_file = num2cell(zeros(length(recording_names_exclude_TTX), 1));
num_active_electrodes = num2cell(zeros(length(recording_names_exclude_TTX), 1));

f1 = figure();

for n_wavelet = 1:length(wavelet_to_search)
    
    wavelet_name = wavelet_to_search{n_wavelet};

    for r_name_idx = 1:length(recording_names_exclude_TTX)

        if contains(recording_names_exclude_TTX{r_name_idx}, '.mat')
            [pathstr, recording_name, ext] = fileparts(recording_names_exclude_TTX{r_name_idx});
        else
            recording_name = recording_names_exclude_TTX{r_name_idx};
        end 

        fprintf('Looking at recording: %s \n', recording_name)

        % Loop through wavelet spike folder 
        wavelet_spike_detection_results_names = {dir([wavelet_spike_folder, strcat(recording_name, '*')]).name};

        wavelet_spike_detection_info = zeros(length(wavelet_spike_detection_results_names), 7);

        % For each recording, check if there is a corresponding TTX file
        for file_idx = 1:length(wavelet_spike_detection_results_names)
            file_name = wavelet_spike_detection_results_names{file_idx};
            param_file = load([wavelet_spike_folder file_name]);

            % Set duration of recording and set maximum tolerable spikes in
            % grounded and TTX recording
            if isfield(param_file.spikeDetectionResult.params, 'duration')
                end_time = param_file.spikeDetectionResult.params.duration;
                duration_provided = 1;
                max_tolerable_spikes_in_TTX = max_tolerable_spikes_in_TTX_per_s;
                max_tolerable_spikes_in_grounded = max_tolerable_spikes_in_grounded_per_s;
                fprintf("Recording duration provided: using min spike in TTX in terms of spike/s \n")
            else
                max_tolerable_spikes_in_TTX = max_tolerable_spikes_in_TTX_abs; 
                max_tolerable_spikes_in_grounded = max_tolerable_spikes_in_grounded_abs;
                end_time = default_end_time;
                duration_provided = 0;
            end 

            % 2020-11-18 Jeremi output file version
            if strcmp(spike_time_unit, 'sec')
                % specify recording_fs to 0 to let function know spike
                % times are in seconds
                wavelet_spike_matrix = spikeTimeToMatrix(param_file.spikeTimes, ... 
                    start_time, end_time, sampling_rate, 0, wavelet_name);
            elseif strcmp(spike_time_unit, 'frame')
                if isfield(param_file.spikeDetectionResult.params, 'fs')
                    recording_fs = param_file.spikeDetectionResult.params.fs;
                elseif isfield(param_file.spikeDetectionResult, 'fs')
                    recording_fs = param_file.spikeDetectionResult.fs;
                end 
                wavelet_spike_matrix = spikeTimeToMatrix(param_file.spikeTimes, ...
                    start_time, end_time, sampling_rate, recording_fs, wavelet_name);
            end 
            total_spikes = sum(sum(wavelet_spike_matrix));
            L_param = param_file.spikeDetectionResult.params.L;

            % TODO: need to read this from the spike file (but that field is
            % not ready yet)
            grounded_electrode_names = [default_grounded_electrode_name];
            grounded_electrode_idx = find(ismember(param_file.channels, grounded_electrode_names));

            % TODO: handle more than one grounded electrode (eg. ground them)
            ground_electrode_spikes = length(param_file.spikeTimes{grounded_electrode_idx}.(wavelet_name));

            wavelet_spike_detection_info(file_idx, 1) = L_param;
            wavelet_spike_detection_info(file_idx, 2) = total_spikes;
            wavelet_spike_detection_info(file_idx, 3) = contains(file_name, 'TTX');

            % Ignore TTX file if user specified to not use TTX to tune L param
            if ~use_TTX_to_tune_L_param
                wavelet_spike_detection_info(file_idx, 3) = 0;
            end 

            wavelet_spike_detection_info(file_idx, 4) = file_idx;
            wavelet_spike_detection_info(file_idx, 5) = ground_electrode_spikes;

            % Total spikes / s
            wavelet_spike_detection_info(file_idx, 6) = total_spikes / end_time;
            wavelet_spike_detection_info(file_idx, 7) = ground_electrode_spikes / end_time;

        end 

        if sum(wavelet_spike_detection_info(:, 3)) == 0
            if ~isempty(custom_backup_param_to_use)
                fprintf('No TTX files found, using a pre-determined parameter file \n');
                % TODO: decide on which file to use
                wavelet_best_param_file_name = nan;
            else
                fprintf('No TTX files found, finding best param file with spike count below threshold in grounded electrode \n')
                ea_param_total_spikes = wavelet_spike_detection_info(:, 2);
                ea_param_grounded_spikes = wavelet_spike_detection_info(:, 5);
                ea_param_L_param = wavelet_spike_detection_info(:, 1);

                spike_count_to_grounded_ratio_reg = ...
                    (ea_param_total_spikes + regularisation_param) ./ ...
                    (ea_param_grounded_spikes + regularisation_param);
                spike_count_to_grounded_ratio = ea_param_total_spikes ./ ea_param_grounded_spikes;

                % select best param as the one that maximises: spike_count_to_grounded_ratio_reg
                [max_ratio_val, best_param_file_idx] = max(spike_count_to_grounded_ratio_reg);

                [ea_param_L_param_sorted, sort_idx] = sort(ea_param_L_param); 
                spike_count_to_grounded_ratio_sorted = spike_count_to_grounded_ratio(sort_idx);
                spike_count_to_grounded_ratio_reg_sorted = spike_count_to_grounded_ratio_reg(sort_idx);
                ea_param_grounded_spikes_sorted = ea_param_grounded_spikes(sort_idx);
                ea_param_total_spikes_sorted = ea_param_total_spikes(sort_idx);



                subplot(2, 3, 1)
                scatter(ea_param_L_param, ea_param_grounded_spikes, 'black')
                hold on
                line_grounded = plot(ea_param_L_param_sorted, ea_param_grounded_spikes_sorted, 'black');
                hold on
                scatter(ea_param_L_param, ea_param_total_spikes, 'green')
                hold on;
                line_all = plot(ea_param_L_param_sorted, ea_param_total_spikes_sorted, 'green');
                legend([line_grounded, line_all], 'Grounded electrode(s)', 'All electrodes')
                xlabel('Cost parameter')
                ylabel('Spike counts')


                subplot(2, 3, 2)
                scatter(ea_param_L_param, spike_count_to_grounded_ratio, 'r')
                hold on;
                line_1 = plot(ea_param_L_param_sorted, spike_count_to_grounded_ratio_sorted, 'r');
                hold on;
                scatter(ea_param_L_param, spike_count_to_grounded_ratio_reg, 'b')
                hold on;
                line_2 = plot(ea_param_L_param_sorted, spike_count_to_grounded_ratio_reg_sorted, 'b');
                legend([line_1, line_2], 'All spikes / grounded spikes', 'All spikes / grounded spikes regularised')
                xlabel('Cost parameter')
                ylabel('Spike ratio')
                set(gcf, 'color', 'white')

                wavelet_best_param_file_name = wavelet_spike_detection_results_names{best_param_file_idx};

                plot_title = sprintf('Recording: %s', recording_name);
                sgtitle(plot_title, 'interpreter', 'none')

                % Get number of active electrodes from the best param file 
                wavelet_best_param_file_data = load([wavelet_spike_folder wavelet_best_param_file_name]);

                if strcmp(spike_time_unit, 'sec')
                    best_param_wavelet_spike_matrix = spikeTimeToMatrix( ...
                    wavelet_best_param_file_data.spikeTimes, start_time, end_time, sampling_rate);
                elseif strcmp(spike_time_unit, 'frame')
                    if isfield(param_file.spikeDetectionResult.params, 'fs')
                        recording_fs = param_file.spikeDetectionResult.params.fs;
                    elseif isfield(param_file.spikeDetectionResult, 'fs')
                        recording_fs = param_file.spikeDetectionResult.fs;
                    end 
                    best_param_wavelet_spike_matrix = spikeTimeToMatrix( ...
                    wavelet_best_param_file_data.spikeTimes, start_time, end_time, ...
                    sampling_rate, recording_fs, wavelet_name);
                end 
                num_spike_per_electrode = sum(best_param_wavelet_spike_matrix, 1);
                num_active_electrodes{r_name_idx} = length(find(num_spike_per_electrode >= min_spike_per_electrode_to_be_active));

                % Look at statoinarity of spike counts 
                subplot(4, 2, 5)
                time_in_sec = start_time:sampling_rate:end_time;
                best_param_grounded_over_time = best_param_wavelet_spike_matrix(:, grounded_electrode_idx);
                plot(time_in_sec(2:end), best_param_grounded_over_time, 'black')
                xlabel('Time(seconds)')
                ylabel('Spikes')
                subplot(4, 2, 7)
                all_spike_over_time = sum(best_param_wavelet_spike_matrix, 2);
                plot(time_in_sec(2:end), all_spike_over_time, 'green')
                xlabel('Time(seconds)')
                ylabel('Spikes')

                % Look at simultaneous spikes 
                all_spike_times = [];
                for channel_idx = 1:length(wavelet_best_param_file_data.spikeTimes)
                    channel_spike_times = wavelet_best_param_file_data.spikeTimes{channel_idx}.(wavelet_name);
                    all_spike_times = [all_spike_times; channel_spike_times];
                end 

                [unique_spike_counts, unique_spike_time] = groupcounts(all_spike_times);
                [num_bin_w_spike_count, spike_count] = groupcounts(unique_spike_counts);


                subplot(2, 3, 3)
                histogram(unique_spike_counts)
                ylabel('Number of time bins')
                xlabel('Number of spikes in time bin')
                reg_term = 0;
                simultaneous_spike_count_ratio = ... 
                    (length(find(unique_spike_counts > 1)) + reg_term) / ...
                    (length(unique_spike_counts) + reg_term) * 100;
                title_text = sprintf('Simultaneous spikes ratio: %.1f%%', simultaneous_spike_count_ratio);
                title(title_text)

                subplot(2, 2, 4);

                % Look at peaks of simultaneous and non-simultaneous spikes 
                all_peaks = [];
                for channel_idx = 1:length(wavelet_best_param_file_data.spikeTimes)
                    channel_spike_waveforms = wavelet_best_param_file_data.spikeWaveforms{channel_idx}.(wavelet_name);
                    channel_wave_peaks = min(channel_spike_waveforms,  [], 2);
                    all_peaks = [all_peaks; channel_wave_peaks];
                end 

                % Group peaks to simultaneous vs. non-simultaneous spikes
                individual_spike_times = unique_spike_time(find(unique_spike_counts == 1));
                sim_spike_times = unique_spike_time(find(unique_spike_counts > 1));
                [~, individual_spike_time_idx] = ismember(individual_spike_times, all_spike_times);
                individual_spike_peaks = all_peaks(individual_spike_time_idx);

                sim_spike_time_idx = [];
                for sim_spk_idx = 1:length(sim_spike_times)
                    sim_spike_time_idx = [sim_spike_time_idx; ... 
                        find(all_spike_times == sim_spike_times(sim_spk_idx))];
                end 
                sim_spike_peaks = all_peaks(sim_spike_time_idx);
                histogram(individual_spike_peaks)
                hold on 
                histogram(sim_spike_peaks)
                legend('Individual spikes', 'Simultaneous spikes')
                xlabel('Spike min peak')
                ylabel('Spike count')

                % Save results
                f = gcf;
                if ~isempty(summary_plot_folder)
                    if ~exist(summary_plot_folder, 'dir')
                        fprintf('Warning: summary plot folder specified does not exist, will attempt to create it')
                        mkdir(summary_plot_folder)
                    end 

                    fig_save_name = [recording_name '_detected_w_' wavelet_name];
                    % print([summary_plot_folder fig_save_name], '-bestfit','-dpng')
                    f1.PaperUnits = 'inches';
                    f1.PaperPosition = [0 0 8 6]; 
                    print([summary_plot_folder fig_save_name], '-dpng', '-r300')
                end 


                % Check if figure still exists, if so, clear it
                if ishandle(f1)
                    clf(f1)
                end 


            end 
        else
            fprintf('TTX file found \n')
            TTX_used{r_name_idx} = 1;
            ttx_info_idx = find(wavelet_spike_detection_info(:, 3) == 1);
            ttx_info = wavelet_spike_detection_info(ttx_info_idx, :);

            if duration_provided == 0
                ttx_info_spike_okay_idx = find(ttx_info(:, 2) < max_tolerable_spikes_in_TTX);
                ttx_info_spike_okay_param = ttx_info(ttx_info_spike_okay_idx, 1);
            elseif duration_provided == 1
                ttx_info_spike_okay_idx = find(ttx_info(:, 6) < max_tolerable_spikes_in_TTX);
                ttx_info_spike_okay_param = ttx_info(ttx_info_spike_okay_idx, 1);
            end 

            if isempty(ttx_info_spike_okay_param)
                fprintf('None of the wavelet parameters has false positive rate below threshold \n')
                fprintf('Skipping wavelet step and flagging this recording \n')
                wavelet_best_param_file_name = nan;
                % TODO: flag this recording
            elseif length(ttx_info_spike_okay_param) == 1
                 % just one param meet the criteria
                 fprintf('Only one CWT parameter meet the false positive rate criteria \n')
                 best_param_file_idx = find( ...
                        (wavelet_spike_detection_info(:, 1) == ttx_info_spike_okay_param) & ...
                        (wavelet_spike_detection_info(:, 3) == 0));
                 % use that index to copy somewhere
                 wavelet_best_param_file_name = wavelet_spike_detection_results_names{best_param_file_idx};
            else
                 % find the param that maximises spikes detected
                 okay_param_info_idx = find( ...
                        ismember(wavelet_spike_detection_info(:, 1), ttx_info_spike_okay_param) & ...
                        wavelet_spike_detection_info(:, 3) == 0);
                 okay_param_info = wavelet_spike_detection_info(okay_param_info_idx, :);
                 best_param_idx = find(okay_param_info(:, 2) == max(okay_param_info(:, 2)));

                 if length(best_param_idx) > 1
                     fprintf('Warning: multiple best parm found for this file, using this first one, TODO: flag file\n')
                     best_param_idx = best_param_idx(1);
                 end 

                 best_param = okay_param_info(best_param_idx, 1);
                 best_param_file_idx = find(wavelet_spike_detection_info(:, 1) == best_param & ... 
                 wavelet_spike_detection_info(:, 3) == 0);
                 wavelet_best_param_file_name = wavelet_spike_detection_results_names{best_param_file_idx};
                 fprintf('Wavelet best param value found \n')
            end 

        end 

        %% Check if there is separate threshold result for each recording (outdated)
        if exist('threshold_spike_folder', 'var')
        % Loop through threshold spike folder 
            threshold_spike_detection_results_names= {dir([threshold_spike_folder, strcat(recording_name, '*')]).name};
            threshold_spike_detection_info = zeros(length(threshold_spike_detection_results_names), 7);

            for file_idx = 1:length(threshold_spike_detection_results_names)
                threshold_file_name = threshold_spike_detection_results_names{file_idx};
                threshold_param_file = load([threshold_spike_folder threshold_file_name]);
                threshold_spike_matrix = spikeTimeToMatrix(...
                    threshold_param_file.spikeDetectionResult.spikeTimes, ...
                    start_time, end_time, sampling_rate);
                total_spikes = sum(sum(threshold_spike_matrix));
                multiplier_param = threshold_param_file.spikeDetectionResult.params.multiplier;

                ground_electrode_spikes = length( ...
                threshold_param_file.spikeDetectionResult.spikeTimes.( ... 
                strcat('channel', num2str(threshold_ground_electrode_name))));

                threshold_spike_detection_info(file_idx, 1) = multiplier_param;
                threshold_spike_detection_info(file_idx, 2) = total_spikes;
                threshold_spike_detection_info(file_idx, 3) = contains(threshold_file_name, 'TTX');
                threshold_spike_detection_info(file_idx, 4) = file_idx;
                threshold_spike_detection_info(file_idx, 5) = ground_electrode_spikes;

                % Total spikes / s
                threshold_spike_detection_info(file_idx, 6) = total_spikes / end_time;
                threshold_spike_detection_info(file_idx, 7) = ground_electrode_spikes / end_time;
            end 

            % Subset to parameters where grounded electrode have fewer than
            % maximum allowable spikes 
            if duration_provided == 0
                subset_threshold_spike_detection_info_idx = find( ...
                    threshold_spike_detection_info(:, 5) < max_tolerable_spikes_in_grounded);
            elseif duration_provided == 1
                % Using spike/s instead 
                subset_threshold_spike_detection_info_idx = find( ...
                    threshold_spike_detection_info(:, 7) < max_tolerable_spikes_in_grounded);
            end 

            subset_threshold_spike_detection_info = threshold_spike_detection_info(... 
                subset_threshold_spike_detection_info_idx, :);

            if isempty(subset_threshold_spike_detection_info)
                fprintf('None of the threshold param meet the grounded electrode criteria, flagging recording \n')
                threshold_best_param_file_name = nan;
            elseif sum(subset_threshold_spike_detection_info(:, 3)) == 0
                TTX_used{r_name_idx} = 1;
                fprintf('No TTX files found, using grounded electrode to set find best param \n');
                % TODO: decide on which file to use
                best_param_idx = find(subset_threshold_spike_detection_info(:, 2)...
                    == max(subset_threshold_spike_detection_info(:, 2)));
                best_param = subset_threshold_spike_detection_info(best_param_idx, 1);
                best_param_file_idx = find(threshold_spike_detection_info(:, 1) == best_param & ... 
                     threshold_spike_detection_info(:, 3) == 0);
                threshold_best_param_file_name = threshold_spike_detection_results_names{best_param_file_idx};

            else
                ttx_criteria_meet_idx = find(...
                    (subset_threshold_spike_detection_info(:, 3) == 1) & ...
                    (subset_threshold_spike_detection_info(:, 2) < max_tolerable_spikes_in_TTX));
                ttx_criteria_meet_params = subset_threshold_spike_detection_info(ttx_criteria_meet_idx, 1);
                % ttx_criteria_meet_subset_threshold_spike_detection_info_idx = find( ...
                % ismember(subset_threshold_spike_detection_info(:, 1), ttx_criteria_meet_idx));
                % ttx_criteria_meet_subset_threshold_spike_detection_info = ...
                %     ttx_criteria_meet_subset_threshold_spike_detection_info(subset_threshold_spike_detection_info, :);
                not_ttx_and_criteria_meet_idx = find(...
                    (subset_threshold_spike_detection_info(:, 3) == 0) & ...
                    ismember(subset_threshold_spike_detection_info(:, 1), ttx_criteria_meet_params));
                not_ttx_max_spikes = max(subset_threshold_spike_detection_info(not_ttx_and_criteria_meet_idx, 2));
                best_param_idx = find(...
                    (subset_threshold_spike_detection_info(:, 3) == 0) & ... % Not TTX
                    (subset_threshold_spike_detection_info(:, 2) == not_ttx_max_spikes) & ... % Max spikes 
                    ismember(subset_threshold_spike_detection_info(:, 1), ttx_criteria_meet_params)); % TTX criteria met
                best_param = subset_threshold_spike_detection_info(best_param_idx, 1);
                best_param_file_idx = find(threshold_spike_detection_info(:, 1) == best_param & ... 
                     threshold_spike_detection_info(:, 3) == 0);
                threshold_best_param_file_name = threshold_spike_detection_results_names{best_param_file_idx};
            end 
        else 
            threshold_best_param_file_name = nan;
            threshold_spike_detection_results_names = [];
        end 

        if (length(wavelet_spike_detection_results_names) == 0) && (length(threshold_spike_detection_results_names) == 0)
            fprintf('No spike detection files found, skipping. \n')
            selected_detection_method{end+1} = nan;
            best_param_file{r_name_idx} = nan;
        elseif (length(wavelet_spike_detection_results_names) == 0)
            fprintf('Only threshold spike found, using that by default \n')
            selected_detection_method{end+1} = 'Threshold';
            best_param_file{r_name_idx} = threshold_best_param_file_name;
        elseif (length(threshold_spike_detection_results_names) == 0)
            fprintf('Only wavelet spike found, using that by default \n')
            selected_detection_method{end+1} = 'Wavelet';
            best_param_file{r_name_idx} = wavelet_best_param_file_name;
        elseif sum(~isnan(wavelet_best_param_file_name)) & sum(~isnan(threshold_best_param_file_name))
            fprintf('Both wavelet and threshold files found, comparing the two \n')
            selected_detection_method{end+1} = 'Wavelet';

            wavelet_best_param_file_data = load([wavelet_spike_folder wavelet_best_param_file_name]);
            threshold_best_param_file_data = load([threshold_spike_folder threshold_best_param_file_name]);
            wavelet_spike_matrix = spikeTimeToMatrix(wavelet_best_param_file_data.spikeDetectionResult.spikeTimes, start_time, end_time, sampling_rate);
            threshold_spike_matrix = spikeTimeToMatrix(threshold_best_param_file_data.spikeDetectionResult.spikeTimes, start_time, end_time, sampling_rate);

            % Total spikes over time (all electrodes)
            subplot(1, 2, 1)
            threshold_spike_over_t = sum(threshold_spike_matrix, 2);
            wavelet_spike_over_t = sum(wavelet_spike_matrix, 2);
            plot(threshold_spike_over_t)
            hold on
            plot(wavelet_spike_over_t)
            xlabel('Time')
            ylabel('Spikes over all electrodes')
            legend('Threshold', 'Wavelet')
            hold on 

            % Correlation
            subplot(1, 2, 2)
            [corr_r, corr_pval] = corr(wavelet_spike_matrix, threshold_spike_matrix);
            corr_diagonal = diag(corr_r);
            scatter(1:length(corr_diagonal), corr_diagonal);
            yline(nanmean(corr_diagonal)); 
            xlabel('Channel index')
            ylabel('Correlation between wavelet and threshold detection method') 
            % Common title
            sgtitle(recording_name,  'Interpreter', 'none');
            set(gcf,'color','w');
            fprintf('Press any key to continue ... \n')
            pause;
            clf('reset')

            % TODO: determine condition where threshold method is preferred
            % Use wavelet detection by default 
            best_param_file{r_name_idx} = wavelet_best_param_file_name;

            % Calculate number of active electrodes 
            num_spike_per_electrode = sum(wavelet_spike_matrix, 1);
            num_active_electrodes{r_name_idx} = length(find(num_spike_per_electrode >= min_spike_per_electrode_to_be_active));

        elseif sum(~isnan(wavelet_best_param_file_name))
            fprintf('Only wavelet method has parameters meeting criteria')
            selected_detection_method{end+1} = 'Wavelet';
            best_param_file{r_name_idx} = wavelet_best_param_file_name;
            wavelet_best_param_file_data = load([wavelet_spike_folder wavelet_best_param_file_name]);
            wavelet_spike_matrix = spikeTimeToMatrix(wavelet_best_param_file_data.spikeDetectionResult.spikeTimes, start_time, end_time, sampling_rate);
            num_spike_per_electrode = sum(wavelet_spike_matrix, 1);
            num_active_electrodes{r_name_idx} = length(find(num_spike_per_electrode >= min_spike_per_electrode_to_be_active));

        elseif sum(~isnan(threshold_best_param_file_name))
            fprintf('Only threshold method has parameters meeting criteria')
            selected_detection_method{end+1} = 'Threshold';
            best_param_file{r_name_idx} = threshold_best_param_file_name;
            threshold_best_param_file_data = load([threshold_spike_folder threshold_best_param_file_name]);
            threshold_spike_matrix = spikeTimeToMatrix(threshold_best_param_file_data.spikeDetectionResult.spikeTimes, start_time, end_time, sampling_rate);
            num_spike_per_electrode = sum(threshold_spike_matrix, 1);
            num_active_electrodes{r_name_idx} = length(find(num_spike_per_electrode >= min_spike_per_electrode_to_be_active));
        else
            selected_detection_method{end+1} = 'Flagged';
            best_param_file{r_name_idx} = 'NaN';
            num_active_electrodes{r_name_idx} = 'NaN';
        end 
    end 

end 


close(f1)

%% Print summary table for all files 
figure()
method = selected_detection_method';
T = table(method, TTX_used, best_param_file, num_active_electrodes, 'RowNames', recording_names_exclude_TTX');
uitable('Data',T{:,:},'ColumnName',T.Properties.VariableNames,...
    'RowName',T.Properties.RowNames,'Units', 'Normalized', 'Position',[0, 0, 1, 1]);

writetable(T, [summary_plot_folder 'summary_table.csv']);


%% Helper functions 
function spike_matrix = spikeTimeToMatrix(spikeTimesStruct, start_time, ...
    end_time, sampling_rate, recording_fs, wavelet_name)

    % recording_fs (optional) : (int)
    % If this argument is provided, then spikeTimes are in frames rather than
    % in seconds, and the spike time in second is obtained by dividing
    % spikeFrames by recording_fs
    % (ie. this parameter therefore also defines whether spikeTimesStruct is 
    % in frames or seconds)

    if ~exist('recording_fs', 'var')
        recording_fs = 0;
    end 

    bin_edges = start_time:1/sampling_rate:end_time;
    num_bins = length(bin_edges) - 1; 


    if isstruct(spikeTimesStruct)
        channel_names = fieldnames(spikeTimesStruct);
        num_channels = length(channel_names);
        spike_matrix = zeros(num_bins, num_channels);
        for channel_idx = 1:numel(channel_names)
            channel_spike_times = spikeTimesStruct.(channel_names{channel_idx});

            if recording_fs ~= 0
                channel_spike_times = channel_spike_times / recording_fs;
            end 

            spike_vector = histcounts(channel_spike_times, bin_edges);
            spike_matrix(:, channel_idx) = spike_vector;
        end 

    elseif iscell(spikeTimesStruct)
        % 2020-11-18 New Jeremi file format: cell of structures
        spikeTimesCell = spikeTimesStruct;
        num_channels = length(spikeTimesCell);
        spike_matrix = zeros(num_bins, num_channels);
        for channel_num = 1:length(spikeTimesCell)
            channel_spike_times = spikeTimesCell{channel_num}.(wavelet_name);

            if recording_fs ~= 0
                channel_spike_times = channel_spike_times / recording_fs;
            end 

            spike_vector = histcounts(channel_spike_times, bin_edges);
            spike_matrix(:, channel_num) = spike_vector;
        end 


end 

end 

