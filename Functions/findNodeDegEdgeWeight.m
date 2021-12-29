function [z,z2] = findNodeDegEdgeWeight(adjM, edge_thresh)
%{ 
find node degree and edge weight from adjacency matrix
INPUT 
------------------
adjM : (matrix)
    adjacency matrix of the network 
edge_thresh : (float or vector)
    this is a vector (list) of thresholds (between 0 and 1) to be
    used for thresholding the edges of the network.
    

OUTPUT 
------------------
z : mean node degree (often referred to as ND), this is the degree of each node 
    this is the mean degree of each node, rounded to the nearest integer.
z2 : mean edge weight (often referred to as EW), this is the edge weight of each
    this is not rounded, note that negative weights are thresholded to zero
   
node


%}
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
z2 = mean(weights)';

end