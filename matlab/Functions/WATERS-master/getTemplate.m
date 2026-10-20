function [aveWaveform, spikeTimes] = getTemplate(trace, multiplier, refPeriod, fs, nSpikes, multiple_templates, multi_template_method, channelInfo, plot_folder)

% Description:
%   Obtain median waveform from spikes detected with threshold method

% INPUT:
%   trace: [n x 1] filtered voltage trace
%   multiplier: [scalar] threshold multiplier used for spike detection
%   refPeriod: [scalar] refractory period [ms] after a spike in which
%                       no spikes will be detected
%   fs: [scalar] sampling freqency in [Hz]
%   nSpikes: [scalar] the number of spikes used to obtain average waveform
%   multiple_templates : [bool] whether to extract multiple templates from
%   the data, if True, then aveWaveform will be a matrix of waveforms
%   instead of a vector 
%   multi_template_method : [str] how to cluster different templates
%   
%

% OUTPUT:
%   aveWaveform: [51 x 1] average spike waveform
%   spikeTimes: [#spikes x 1] vector containing detected spike times

% Author:
%   Jeremy Chabros, University of Cambridge, 2020
%   email: jjc80@cam.ac.uk
%   github.com/jeremi-chabros
% Mod logs
% 2021-05-02: TS: clarifying some param names
% 2021-05-12: TS: adding spike width and amplitude as clustering method

spike_window = 10;  % window around spike in frames, so 10/25000 = 0.4 ms
remove_artifact = 0;

if ~exist('multiple_templates', 'var')
    multiple_templates = 0;
end 

if ~exist('multi_template_method', 'var')
    multi_template_method = 'PCA';
end 

if ~exist('plot_folder', 'var')
    plot_folder = '';
end 

if ~exist('channelInfo', 'var')
    channelInfo = struct();
end 
    

[spikeTrain, ~, ~] = detectSpikesThreshold(trace, multiplier, refPeriod, fs, 0);
spikeTimes = find(spikeTrain == 1);
[spikeTimes, spikeWaveforms] = alignPeaks(spikeTimes, trace, spike_window, remove_artifact);

if length(spikeTimes) == 0
    fprintf('No spikes found for this electrode, getTemplate will fail');
end 


%  If fewer spikes than specified - use the maximum number possible
if  numel(spikeTimes) < nSpikes
    nSpikes = sum(spikeTrain);
    disp(['Not enough spikes detected with specified threshold, using ', num2str(nSpikes),'instead']);
end

% Uniformly sample n_spikes
% TS: this will fail if there are fewer then 3 spikes, but I think that's
% okay
% This also misses the first and last spike, eg. if nSpikes ==
% sum(spikeTrain), then spikes2use will have duplicate values, but that's 
% not critical as well, won't fix for now.
if ~multiple_templates
    spikes2use = round(linspace(2, length(spikeTimes)-2, nSpikes));

    % TS: Take the median to avoid outliers (?)
    aveWaveform = median(spikeWaveforms(spikes2use,:));
else
    
    if strcmp(multi_template_method, 'PCA')
        % extract mulitple templates by first performing PCA, then 
        % doing clustering and finding the optimal number of clusters

        % do PCA all detected spikes 
        [coeff, score, latent, tsquared, explained, mu] = pca(spikeWaveforms');
        num_PC = 2;
        reduced_X = coeff(:, 1:num_PC);

    elseif strcmp(multi_template_method, 'amplitudeAndWidth')
        
        % spike_amplitude = min(spikeWaveforms, [], 2);
        num_spikes = size(spikeWaveforms, 1);
        peak_x = 25; % hard-coded for now, due to alignPeaks
        spike_amplitude = spikeWaveforms(:, peak_x);
        spike_widths = zeros(num_spikes, 1);
        
        for spike_idx = 1:size(spikeWaveforms)
            spike_wave = spikeWaveforms(spike_idx, :);
            
            half_peak_y = spike_amplitude(spike_idx) / 2;
            cross_half_peak_x = find(spike_wave > half_peak_y);
            
            % Find latest time of crossing half_peak_y before peak 
            % And find earliest time of crossing half_peak_y after peak
            half_peak_x1 = max(cross_half_peak_x(cross_half_peak_x < peak_x));
            half_peak_x2 = min(cross_half_peak_x(cross_half_peak_x > peak_x));
            spike_widths(spike_idx) = (half_peak_x2 - half_peak_x1) / fs;
        end 
        
        reduced_X = [spike_amplitude spike_widths];
    
    elseif strcmp(multi_template_method, 'amplitudeAndWidthAndSymmetry')
        
        % spike_amplitude = min(spikeWaveforms, [], 2);
        num_spikes = size(spikeWaveforms, 1);
        peak_x = 25; % hard-coded for now, due to alignPeaks
        spike_amplitude = spikeWaveforms(:, peak_x);
        spike_widths = zeros(num_spikes, 1);
        spike_symmetry = zeros(num_spikes, 1);
        
        for spike_idx = 1:size(spikeWaveforms)
            spike_wave = spikeWaveforms(spike_idx, :);
            
            half_peak_y = spike_amplitude(spike_idx) / 2;
            cross_half_peak_x = find(spike_wave > half_peak_y);
            
            % Find latest time of crossing half_peak_y before peak 
            % And find earliest time of crossing half_peak_y after peak
            half_peak_x1 = max(cross_half_peak_x(cross_half_peak_x < peak_x));
            half_peak_x2 = min(cross_half_peak_x(cross_half_peak_x > peak_x));
            spike_widths(spike_idx) = (half_peak_x2 - half_peak_x1) / fs;
            
            spike_first_half = spike_wave(1:peak_x-1);
            spike_second_half_flipped = fliplr(spike_wave(peak_x+1:end-2));
            % higher value means less symmetric, 0 means perfectly
            % symmetric (no difference between first half and second half
            % reversed
            spike_symmetry(spike_idx) = sum(abs(spike_first_half - spike_second_half_flipped));
            
        end 
        
        reduced_X = [spike_amplitude spike_widths spike_symmetry];
        
        
    else
        
        fprintf('Warning: invalid multi_template method specified! \n');
        
    end 
    
    %% Do clustering   
    minClustNum = 1;
    clusterer = HDBSCAN(reduced_X); 
    clusterer.minClustNum = minClustNum;
    clusterer.fit_model(); 			% trains a cluster hierarchy
    clusterer.get_best_clusters(); 	% finds the optimal "flat" clustering scheme
    clusterer.get_membership();		% assigns cluster labels to the points in X

    clustering_labels = clusterer.labels;
    unique_clusters = unique(clustering_labels);
    num_cluster = length(unique_clusters);

    fprintf('Doing clustering of spikes in reduced space \n')
    fprintf( 'Number of points: %i \n',clusterer.nPoints );
    fprintf( 'Number of dimensions: %i \n',clusterer.nDims );

    num_spike_time_frames = size(spikeWaveforms, 2);
    aveWaveform = zeros(num_spike_time_frames, num_cluster);

    % Make average waveform for each cluster 
    for cluster_label_idx = 1:num_cluster
        cluster_label = unique_clusters(cluster_label_idx);
        label_idx = find(clustering_labels == cluster_label);
        cluster_ave_waveform = median(spikeWaveforms(label_idx, :));
        aveWaveform(:, cluster_label_idx) = cluster_ave_waveform;
    end 
    
    
    % Plot to look at spike features / PCA components

    if length(plot_folder) > 0
        figure;
        for cluster_label_idx = 1:num_cluster
            cluster_label = unique_clusters(cluster_label_idx);
            label_idx = find(clustering_labels == cluster_label);
            subplot(1, 2, 1)
            scatter(reduced_X(label_idx, 1), reduced_X(label_idx, 2));
            hold on
            xlabel('Feature 1')
            ylabel('Feature 2')
           
        end 
        title_txt = sprintf('Clusters: %.f', num_cluster); 
        title(title_txt);

        subplot(1, 2, 2)
        for cluster_label_idx = 1:num_cluster
            plot(aveWaveform(:, cluster_label_idx), 'linewidth', 2)
            hold on
        end 
        xlabel('Time bins')
        ylabel('Voltage')
        set(gcf, 'color', 'w')
        set(gcf, 'PaperPosition', [0 0 20 10]);
        [~, recording_name, ~] = fileparts(channelInfo.fileName);
        fig_name = strcat([recording_name, '_channel_' num2str(channelInfo.channel)]);
        print(fullfile(plot_folder, fig_name), '-dpng', '-r300');
        close(gcf)
    end 
    
end 

end