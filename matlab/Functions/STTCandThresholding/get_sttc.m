function adjM = get_sttc(spikeTimes, lag_ms, duration_s, method, use_c_code)
% Description: calculates pairwise correlation between pairs of neurons
%              using spike time tiling coefficient
%
% See the original paper:
% https://www.ncbi.nlm.nih.gov/pubmed/25339742
%----------
% Parameters
% spikeTimes  - [n x 1]  cell with spike time structures; spikeTimes{}.(method)
%                        NOTE: spike times MUST be in seconds!
% lag_ms      - [scalar] time lag (in ms) used in STTC
% duration_s  - [scalar] length of the recording in seconds
% method      - [string] spike detection method
% fs          - [scalar] sampling frequency in Hz
% Returns
% ----------
% adjM        - [n x n] adjacency matrix representing functional
%                       connectivity
%----------
% @author JJChabros (jjc80@cam.ac.uk), February 2021

%  Originally written in C by Catherine S Cutts (2014):
%  https://github.com/CCutts/Detecting_pairwise_correlations_in_spike_trains/blob/master/spike_time_tiling_coefficient.c
%----------

num_chan = length(spikeTimes);
combins = nchoosek(1:num_chan, 2);
A = zeros(1, length(combins));
adjM = NaN(num_chan, num_chan);

for i = 1:size(combins, 1)
    spike_times_1 = double(spikeTimes{combins(i,1)}.(method));
    spike_times_2 = double(spikeTimes{combins(i,2)}.(method));
    N1v = uint32(length(spike_times_1));
    N2v = uint32(length(spike_times_2));
%     N1v = length(spike_times_1);
%     N2v = length(spike_times_2);
    dtv = lag_ms/1000; % [s]
    dtv = double(dtv);
    Time = double([0 duration_s]);
    
    if use_c_code
        tileCoef = sttc(N1v, N2v, dtv, Time, spike_times_1, spike_times_2);
    else 
        tileCoef = sttc_m(double(N1v), double(N2v), dtv, Time, spike_times_1, spike_times_2);
    end
    A(i) = tileCoef; % Faster to only get upper triangle so might as well store as vector
end

% Vector -> matrix
for i = 1:size(combins, 1)
    row = combins(i,1);
    col = combins(i,2);
    adjM(row, col) = A(i);
    adjM(col, row) = A(i);
end

% Remove negatives, NaNs, and nonzero diagonals
adjM(adjM<0) = 0;
adjM(isnan(adjM)) = 0;

end