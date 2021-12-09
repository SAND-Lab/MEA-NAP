function [F1, adjM, adjMci] = adjM_thr_checkreps_capop(spikeTimes, method, lag_ms, tail, fs,...
    duration_s, rep_num)
% Description: This function generates synthetic spike times from original
% events and randomizes them using circular shift. All synthetic data is
% created from existing events.
%
% It then averages the functional connectivity based on statistical significance
% established from synthetic matrices
%----------
% INPUTS:
%   spikeTimes  - [n x 1]  cell with spike time structures; spikeTimes{}.(method)
%                          IMPORTANT: assumes spike times in seconds
%   method      - [string] spike detection method
%   lag_ms      - [scalar] time lag (in ms) used in STTC
%   tail        - [scalar] confidence interval; p < tail (e.g. p < 0.05)
%   fs          - [scalar] sampling frequency in Hz
%   duration_s  - [scalar] length of the recording in seconds
%   rep_num     - [scalar] number of iterations used to generate synthetic
%                          dataset
%----------
% OUTPUTS:
%   adjMci = real adjacency matrix thresholded at specidied confidence interval
%            of probabilistic edge weights
%----------
% Author: RCFeord
%   Updated by HSmith, Cambridge, Dec 2020
%   Re-written to use event times by JChabros, Feb 2021

a = 1:10:rep_num;
dist1 = cell(size(a));

num_frames = duration_s*fs;
num_nodes = length(spikeTimes);

% adjMi = zeros(num_nodes,num_nodes,rep_num);

adjM = get_sttc(spikeTimes, lag_ms, duration_s, method);

for i = 1:rep_num

    synth_spk = spikeTimes;
    
    for n = 1:num_nodes
        
        k = randi(num_frames,1); % padding used in circshift
        
        % Fast circshift: logical indexing and basic operations used
        spk_vec = synth_spk{n}.(method)*fs + k;
        overhang = spk_vec > num_frames;
        spk_vec(overhang) = spk_vec(overhang)-num_frames;
        spk_vec = sort(spk_vec);
        
        synth_spk{n}.(method) = spk_vec/fs;
        % NOTE: could probably rewrite it to default to times in 's'
        %       just swap 'num_frames' with 'duration_s' and remove the
        %       multiplication/division by 'fs' in lines 48 & 53
    end
    
    adjMs = get_sttc(synth_spk, lag_ms, duration_s, method);
    adjMs(1:num_nodes+1:end) = 0; % Faster than removing from adjMi
    adjMi(:,:,i) = adjMs;
    
    % Find threshold values at intervals specified by 'a'
    if ismember(i,a)
        cutoff_point = ceil((1 - tail) * i); % Find column no. corresponding to cutoff point
        mat = zeros(num_nodes,num_nodes);
        for cell_row = 1:num_nodes % Run for each element of adjacency matrix
            for cell_column = 1:num_nodes
                Eu = sort(adjMi(cell_row,cell_column,:),'ascend'); % Current list of values for that element
                threshold = Eu(cutoff_point); % Threshold value
                mat(cell_row,cell_column) = threshold; % Store value
            end
        end
        dist1{a == i} = mat; % Allocate to dist1
    end
end

adjMi(adjMi<0) = 0;
adjMi(isnan(adjMi)) = 0;

repVal = a;
genotype = 1;
F1 = significance_distribution_plots(dist1,repVal,adjM,genotype);

% STATS TEST:
% Threshold each element if >= top 'tail' % of data

adjMci = adjM;
cutoff_point = ceil((1 - tail) * rep_num);
for i = 1:size(adjMi,1)
    for j = 1:size(adjMi,2)
        Eu = sort(adjMi(i,j,:),'ascend');
        if Eu(cutoff_point) > adjM(i,j)
            adjMci(i,j) = NaN;
        end
    end
end
end




