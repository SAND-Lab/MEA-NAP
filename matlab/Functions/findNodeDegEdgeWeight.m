function [z,z2] = findNodeDegEdgeWeight(adjM, exclude_zeros)
% Calculates node degree and mean edge weight from adjacency matrix
% An edge is any off-diagonal weight above zero, however small: deciding which
% edges are real is the job of the thresholding that built adjM
% Parameters 
% ----------
% adjM : (matrix)
%     adjacency matrix of the network 
% exclude_zeros : bool 
%     whether to exclude zeros when calculating the mean edge weight 
%     defaults to True
% Returns 
% -------
% z : node degree (often referred to as ND), the number of edges of each node
% z2 : mean edge weight (often referred to as MEW), this is the edge weight of each
%     this is not rounded, note that negative weights are thresholded to zero
%   

if nargin == 1
    exclude_zeros = 1;
end 

%% get node degree for each channel

edges = adjM - eye(size(adjM));
edges(isnan(edges)) = 0;

z = sum(edges > 0, 1)';

%% acquire edge weights

weights = adjM;
weights = weights - eye(size(weights));
weights(find(isnan(weights))) = 0;
weights(find(weights < 0)) = 0;

if exclude_zeros
    weights(weights == 0) = nan;
end 

z2 = nanmean(weights)';

end