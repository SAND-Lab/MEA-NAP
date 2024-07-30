function G = genRandNetwork(numNodes, p, mew)
% Generates a random network 
% Parameters
% ----------
% numNodes : int 
%            number of nodes to include in the network 
% p        : float 
%            connection probability 
% mew      : float 
%            mean edge weight, if not specified, then sample 
%            weight from a uniform distribution 

G = rand(numNodes,numNodes) < p;
G = triu(G,1);
% Make the graph symmetric
G = G + G';
% sample weights from a distribution and assign them to
numEdges = sum(sum(G == 1));

if exist('mew', 'var')
    sigma = 0.1;
    edgeWeights = normrnd(mew,sigma, numEdges, 1);
    edgeWeights(edgeWeights > 1) = 1;
    edgeWeights(edgeWeights < 0) = 0;
else 
    edgeWeights = rand(numEdges, 1);
end



G(G == 1) = edgeWeights;
G = (G + G') / 2;
% remove diagonal elements
G(logical(eye(size(G)))) = 0;
end