function [z,z2] = findNodeDegEdgeWeight(adjM, edge_thresh, exclude_zeros)
% Calculates mean node degree and mean edge weight from adjacency matrix
% Parameters 
% ----------
% adjM : (matrix)
%     adjacency matrix of the network 
% edge_thresh : (float or vector)
%     this is a vector (list) of thresholds (between 0 and 1) to be
%     used for thresholding the edges of the network. Values below (including
%     negative values) this threshold will be set to zero
% exclude_zeros : bool 
%     whether to exclude zeros when calculating the mean edge weight 
%     defaults to True
% Returns 
% -------
% z : mean node degree (often referred to as ND), this is the degree of each node 
%     this is the mean degree of each node, rounded to the nearest integer.
% z2 : mean edge weight (often referred to as MEW), this is the edge weight of each
%     this is not rounded, note that negative weights are thresholded to zero
%   

if nargin == 2
    exclude_zeros = 1;
end 

%% get node degree for each channel

count = 1; %to track threshold iterations

for cutoff = edge_thresh
    threshold = cutoff;
    edges=adjM;
    edges = edges - eye(size(edges));
    edges(find(isnan(edges))) = 0;
    edges(find(edges < threshold)) = 0;
    edges(find(edges >= threshold))= 1;
    
    DegreeVec(:,count) = sum(edges);
    
    count = count + 1;
end

z = round(mean(DegreeVec,2));

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