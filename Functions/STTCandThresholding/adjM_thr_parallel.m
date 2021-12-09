function [adjM, adjMci] = adjM_thr_parallel(spikeTimes, method, lag_ms, tail, fs,...
    duration_s, rep_num)

% Description: This function generates synthetic spike times from original
% events and randomizes them using circular shift. All synthetic data is
% created from existing events.
%
% It then averages the functional connectivity based on statistical significance
% established from synthetic matrices

% NOTE: This is the fast version of the script and does not generate plots
%       For troubleshooting/visuals use adjM_thr_JC.m

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

% Terminate previous and start new parallel computing pool 
poolobj = gcp('nocreate');
delete(poolobj);
parpool(4); % change 4 to the number of cores
% Note: If this function is run in a loop, start one parpool before the
%       loop to avoid restarting at each iteration

num_frames = duration_s*fs;
num_nodes = length(spikeTimes);

adjM = get_sttc(spikeTimes, lag_ms, duration_s, method);


parfor i = 1:rep_num
    
    synth_spk = spikeTimes;
    
    for n = 1:num_nodes
        
        k = randi(round(num_frames),1); % padding used in circshift
        
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
end

adjMci = adjM;
cutoff_point = ceil((1 - tail) * rep_num);
parfor i = 1:num_nodes
    for j = 1:num_nodes
        Eu = sort(adjMi(i,j,:),'ascend');
        if Eu(cutoff_point) > adjM(i,j)
            adjMci(i,j) = 0;
        end
    end
end
end