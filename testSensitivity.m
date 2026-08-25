%% MEANAP Sensitivity Analysis 
% This script asks what is the smallest difference in network
% metrics that can be detected by MEA-NAP 

numNodes = 60;
numRandomNetworks = 100;

p = 0.1; 
G = rand(numNodes,numNodes) < p;
G = triu(G,1);
% Make the graph symmetric
G = G + G';


% sample weights from a distribution and assign them to 
numEdges = sum(sum(G == 1));
edgeWeights = rand(numEdges, 1);
G(G == 1) = edgeWeights;

G = (G + G') / 2;

% remove diagonal elements 
G(logical(eye(size(G)))) = 0; 



%% Betweeness centrality 
numRandomNetworks = 100;
numNodes = 60;
p = 0.2;
addpath(genpath('/Users/timothysit/AnalysisPipeline_2024-04-05/Functions'));

BC_store = size(numRandomNetworks, 1) + nan;
num_modules_store = size(numRandomNetworks, 1) + nan;

for rand_idx = 1:numRandomNetworks
    G_random = genRandNetwork(numNodes, p);
    smallFactor = 0.01; % prevent division by zero
    pathLengthNetwork = 1 ./ (G_random + smallFactor);

    % Betweeness centrality 
    BC = betweenness_wei(pathLengthNetwork);
    BC_norm = BC/((length(G_random)-1)*(length(G_random)-2));
    BC_store(rand_idx) = mean(BC_norm);

    % Calculate number of modules 
    [Ci,Q,~] = mod_consensus_cluster_iterate(G_random,0.4,50);
    nMod = max(Ci);
    num_modules_store(rand_idx) = nMod;

end

figure;
hist(BC_store)