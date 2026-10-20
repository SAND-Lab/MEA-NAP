  
function [Mout,Qout,num_repeats] = mod_consensus_cluster_iterate(adjM,threshold,repNum)
% Written by H Smith, Cambridge, 2020

% Consensus clustering method from Lancichinetti & Fortunato, 2012, to
% produce modularity groups from methods of community detection that can
% produce different groups for each classifiction method.
% https://www.nature.com/articles/srep00336

% INPUTS:
%   adjM = adjacency matrix
%   threshold = minimum value for consensus coclassification matrix.
%       Recommend values of < 0.4
%   repNum = number of repetitions for community detection algorithm
%       Recommend values of ~50 

% OUTPUT:
%   Mout = community affiliation vector
%   Qout = optimized community-structure statistic for consensus
%       coclassification matrix
%   num_repeats = number of iterations required to complete 

% REQUIRED FUNCTIONS:
%   consensus_coclassify (H Smith)
%   consensuscheck (H Smith)

% Run community detection repNum times 
M = cell(repNum,1);
M{repNum,1} = [];
for i = 1:repNum
    [M{i}] = community_louvain(adjM);
end

% Compute consensus coclassification matrix for M
[D] = consensus_coclassify(M);
D(D < threshold) = 0; % Apply threshold

num_repeats = 0;
blockdiag = 0;

while blockdiag ~= 1 % Stop when D is block diagonal
    % Run community detection on thresholded matrix
    B = cell(repNum,1); % Overwrite
    B{repNum,1} = [];
    Q = B;
    for i = 1:repNum
        [B{i},Q{i}] = community_louvain(D);
    end
    
    % Calculate consensus coclassification matrix on new community
    [D] = consensus_coclassify(B);
    D(D < threshold) = 0;
    
    num_repeats = num_repeats + 1;
    blockdiag = consensuscheck(D);
end

Mout = B{1};
Qout = Q{1};

end