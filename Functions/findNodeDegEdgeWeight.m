function [z,z2] = findNodeDegEdgeWeight(adjM, edge_thresh)

% find node degree and edge weight from adjacency matrix

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