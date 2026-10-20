function adjM_out = limitEdgesForPlotting(adjM, Params)

%LIMITEDGESFORPLOTTING Keep only top weighted edges for visualization

    % Support either parameter name
    if isfield(Params, 'maxedgestoplot') && ~isempty(Params.maxedgestoplot)
        maxEdges = Params.maxedgestoplot;
    elseif isfield(Params, 'maxNumEdgesToPlot') && ~isempty(Params.maxNumEdgesToPlot)
        maxEdges = Params.maxNumEdgesToPlot;
    else
        adjM_out = adjM;
        adjM_out(isnan(adjM_out) | isinf(adjM_out)) = 0;
        return
    end

    % Work on a cleaned copy
    adjM_clean = adjM;
    adjM_clean(isnan(adjM_clean) | isinf(adjM_clean)) = 0;

    % Remove diagonal
    adjM_clean(1:size(adjM_clean,1)+1:end) = 0;

    % Determine whether matrix is symmetric after cleaning
    isUndirected = isequal(adjM_clean, adjM_clean.');

    if isUndirected
        mask = triu(true(size(adjM_clean)), 1);
    else
        mask = ~eye(size(adjM_clean));
    end

    edgeWeights = adjM_clean(mask);

    % Only valid nonzero edges
    validIdx = find(edgeWeights ~= 0);

    % Start from ZERO, not from original adjacency matrix
    adjM_out = zeros(size(adjM_clean));

    if isempty(validIdx)
        return
    end

    if numel(validIdx) <= maxEdges
        edgeWeightsFiltered = zeros(size(edgeWeights));
        edgeWeightsFiltered(validIdx) = edgeWeights(validIdx);
    else
        edgeVals = edgeWeights(validIdx);

        method = 'HighToLow';
        if isfield(Params, 'edgeSubsamplingMethod') && ~isempty(Params.edgeSubsamplingMethod)
            method = Params.edgeSubsamplingMethod;
        end

        switch lower(method)
            case {'hightolow', 'high_to_low', 'high to low'}
                [~, sortIdx] = sort(abs(edgeVals), 'descend');
                keepLocal = validIdx(sortIdx(1:maxEdges));

            otherwise
                error('Unknown edge subsampling method: %s', method);
        end

        edgeWeightsFiltered = zeros(size(edgeWeights));
        edgeWeightsFiltered(keepLocal) = edgeWeights(keepLocal);
    end

    % Put filtered edges into clean output matrix
    adjM_out(mask) = edgeWeightsFiltered;

    % Mirror back if undirected without doubling weights
    if isUndirected
        adjM_out = max(adjM_out, adjM_out.');
    end

    % Final safety clean
    adjM_out(isnan(adjM_out) | isinf(adjM_out)) = 0;

end