function [all_spikes, unique_idx, intersect_matrix] = mergeSpikes(spike_times, option)
% Merges spike times across detection methods.
% TIP: to get spike waveforms corresponding to the merged spike times call e.g.:
%      [~, spikes] = alignPeaks(spike_times.all, filtered_trace, 25, 0, 1, 10, 10);
% Parameters
% ----------
% spike_times - [1 x numElectrode] 
%        each cell contain a structure corresponding to an electrode
%        within each cell, eg. spikeTimes{1} is a structure that contains 
%        a field for each spike detection method, which contains 
%        a vector denoting the spike times in seconds 
%        eg.    bior1p5: [5611×1 double]
%               thr4: [5356×1 double]
%               thr5: [3380×1 double]
%        
% option      - [string] specifies merging option: 'all' or 'wavelets'; if
%                        not specified, defaults to 'all'
% Returns 
% -------
% all_spikes  - [struct] with merged spike times appended to spike_times{channel}.('all')
% unique_idx - [vector] containing the indexes of spikes detected uniquely by a given method
% 
% NOTE: the number in unique_idx corresponds to the position in fieldnames
%       of spike_times, e.g. if field no. 1 is 'mea', then 1 in unique_idx
%       will represent a spike detected uniquely by 'mea' method
%       Zero represents spikes picked up by at least 2 methods
% TODO: I think this merging method does not currently merge within a
% certain time bin (eg. combine spikes if they are in the same 5 ms time
% bin?)
% @author JJChabros (jjc80@cam.ac.uk), January 2021
% Updates by Tim Sit
% 2022-09 : 'wavelets' merge takes in availble wavelets rather than having
% the user to use all the wavelets

switch option
    case 'all'
        methods = fieldnames(spike_times);
    case 'wavelets'
        methods_to_search = {'mea','bior1p5','bior1p3','db2'};
        methods = intersect(methods_to_search, fieldnames(spike_times));
end

all_spikes = [];

for method = 1:numel(methods)
%     all_spikes = union(all_spikes, round(spike_times.(methods{method})*25000));
    all_spikes = union(all_spikes, spike_times.(methods{method}));
end

% all_spikes = all_spikes';
% Vectorized operations + Logical indexing = Fast but hard to follow

unique_idx = [];
intersect_matrix = [];

% % Pre-allocate
% all_spikes_bin = zeros(1, max(all_spikes));
% all_spikes_bin(all_spikes) = 1;
% intersect_matrix = zeros(length(all_spikes_bin),length(methods));
% 
% for method = 1:length(methods)
%     spk_vec = zeros(size(all_spikes_bin));
%     intersect_vec = zeros(size(all_spikes_bin));
% %     spk_vec(round(spike_times.(methods{method})*25000)) = 1;
%     spk_vec(spike_times.(methods{method})) = 1;
%     intersect_vec = spk_vec .* all_spikes_bin;
%     intersect_matrix(:,method) = intersect_vec';
% end
% 
% intersect_matrix = intersect_matrix(any(intersect_matrix,2),:);
% 
% unique_idx = zeros(length(intersect_matrix),1);
% uqpos = find(sum(intersect_matrix,2)==1);
% [~,unique_vec] = max(intersect_matrix(uqpos,:)');
% unique_idx(uqpos) = unique_vec; 
end
