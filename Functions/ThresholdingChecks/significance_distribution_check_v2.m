function significance_distribution_check_v2(events,adjM,repNum,tail,method,downSample,lag,fs,genotype,bins)
% H Smith, Cambridge, 2021
% Show changes in thresholding as number of repeats increases
% Produces figure as described in significance_distribution_plots

% INPUTS:
%   events = binary matrix of spikes/neuronal events, columns are nodes/cells,
%            rows correspond to time points
%   adjM = adjacency matrix of real data
%   repNum = number of repetitions for the generation of synthetic datasets
%   tail = confidence interval. Eg input 0.05 for p = 0.05 thresholding and
%          0.025 for p = 0.025 thresholding. No default set
%   method = correlation method for adjacency matrix generation: 
%            'tileCoef' = STTC, 'correlation','partialcorr','xcorr'
%   downSample = downsampling
%   lag = lag for the correlation or STTC
%   fs = sampling frequency
%   genotype: (currently no code for het)
%       = 0 knockout
%       = 1 wildtype
%   bins = number of iterations between each save of thresholding data.
%       Recommend ~10 for repNum = 3000

% REQUIRED FUNCTIONS:
%   getAdjM_CaPop
%   significance_distribution_plots

%% Load variables
% adjMi is specifically NOT preallocated as this creates errors during 
% the later sorting process
num_frames = size(events,1);
num_nodes = size(events,2);
a = 1:bins:repNum; % Save points
dist1 = cell(size(a));

%% Run circular data shuffling
for n = 1:repNum
    
    % Create a matrix the same size as the real data matrix ('events')
    SynthDatBin = zeros(size(events));
    % Select points along timeseries
    locs = randi(num_frames,1,num_nodes);
    
    % Shuffle data
    for i = 1:num_nodes
        SynthDatBin(1 : end - locs(i) +1 , i) = events(locs(i) : end , i);
        SynthDatBin(end - locs(i) +2 : end , i) = events(1 : locs(i) -1 , i);
    end
        
    % Generate adjacency matrix from synthetic data
    adjMs = getAdjM_CaPop(SynthDatBin, method, downSample, lag, fs);
    adjMs(adjMs<0) = 0; % Remove negatives
    adjMs(isnan(adjMs)) = 0; % Remove NaNs
    adjMs = adjMs .* ~eye(num_nodes); % Remove self-connections

    % Add to stack of synthetic adjacency matrices
    adjMi(:,:,n) = adjMs; 
    
    % Find threshold values at save point intervals specified by 'a'
    if ismember(n,a) 
        cellno = find(a == n); % Find location within 'a'
        cutoff_point = ceil((1 - tail) * n); % Find column no. corresponding to cutoff point
        mat = zeros(num_nodes,num_nodes);
        for cell_row = 1:num_nodes % Run for each element of adjacency matrix
            for cell_column = 1:num_nodes
                Eu = sort(adjMi(cell_row,cell_column,:),'ascend'); % Current list of values for that element
                threshold = Eu(cutoff_point); % Threshold value
                mat(cell_row,cell_column) = threshold; % Store value
            end
        end
        dist1{cellno} = mat; % Allocate to dist1
    end
end

%% Plot
repVal = a;
F1 = significance_distribution_plots(dist1,repVal,adjM,genotype);

end