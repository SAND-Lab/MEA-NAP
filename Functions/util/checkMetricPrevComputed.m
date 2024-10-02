function prevComputed = checkMetricPrevComputed(prevNetMet, lagValFieldName, netMetName)
    % Check if the lag has previously been done before
    if isfield(prevNetMet, lagValFieldName)
        if isfield(prevNetMet.(lagValFieldName), netMetName)
            prevComputed = 1;
        else 
            prevComputed = 0;
        end
    else 
        prevComputed = 0;
    end

end
