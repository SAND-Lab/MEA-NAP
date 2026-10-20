function edge_thresh = getEdgeThreshold(adjM, Params)
%GETEDGETHRESHOLD Summary of this function goes here
%   Detailed explanation goes here
if isfield(Params, 'networkPlotEdgeThresholdMethod')
    if strcmp(Params.networkPlotEdgeThresholdMethod, 'Absolute Value')
        edge_thresh = Params.networkPlotEdgeThreshold;
    else 
        edge_thresh_percentile = Params.networkPlotEdgeThresholdPercentile;
        edge_thresh = prctile(adjM(:), edge_thresh_percentile);
    end
else
    % Pre version 1.10.0 parameters
    edge_thresh = 0.0001;    
end

end

