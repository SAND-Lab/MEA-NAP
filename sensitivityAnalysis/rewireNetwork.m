function G_rewired = rewireNetwork(G, p)
%REWIRENETWORK Summary of this function goes here
%   G : network adjacency matrix
%   p : re-wiring probability 

% select edges to replace 
numNodes = size(G, 1);
edgePairs = nchoosek(1:numNodes, 2);
edgePairIdx = 1:length(edgePairs);
edgePairIdxRandomised = edgePairIdx(randperm(length(edgePairIdx)));

numEdgePairsToReplace = round(length(edgePairs) * p);

edgePairIdxToReplace = edgePairIdxRandomised(1:numEdgePairsToReplace);

% uniform [0, 1] distribution of edge weights
edgePairReplacementValues = rand(numEdgePairsToReplace, 1);

G_rewired = G;

%{
node1vec = edgePairs(edgePairIdxToReplace, 1);
node2vec = edgePairs(edgePairIdxToReplace, 2);
G_rewired(node1vec, node2vec) = edgePairReplacementValues;
G_rewired(node2vec, node1vec) = edgePairReplacementValues;
%}
%
for edgeIdx = edgePairIdxToReplace
    edgeCounter = 1;
    node1 = edgePairs(edgeIdx, 1);
    node2 = edgePairs(edgeIdx, 2);
    
    G_rewired(node1, node2) = edgePairReplacementValues(edgeCounter);
    G_rewired(node2, node1) = edgePairReplacementValues(edgeCounter);
    
    edgeCounter = edgeCounter+1;
end
%


end

