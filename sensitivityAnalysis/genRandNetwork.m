function G = genRandNetwork(numNodes, p)
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
end