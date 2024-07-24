function adjM = genRandSmallWorldNetwork(numNodes, K_edge, beta)

G = WattsStrogatz(numNodes, K_edge, beta);  % generates symmetric (undirected) small-world network
adjM  = full(adjacency(G));
numEdges = sum(sum(adjM == 1));
edgeWeights = rand(numEdges/2, 1);
adjM_U = triu(adjM);
adjM_U(adjM_U == 1) = edgeWeights;
adjM = (adjM_U + adjM_U')/2; 
% remove diagonal elements
adjM(logical(eye(size(adjM)))) = 0;

end 