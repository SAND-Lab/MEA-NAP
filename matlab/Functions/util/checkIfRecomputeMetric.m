function pleaseComputeMetric = checkIfRecomputeMetric(Params, prevNetMet, lagValFieldName, netMetName)
%CHECKIFRECOMPUTEMETRIC Check whether to recompute metric
%   Detailed explanation goes here
% TODO: write function to also check the Parameters related to metric
% calculation matches

% Check if user ask to recompute metrics
if Params.recomputeMetrics == 1
   if contains(Params.metricsToRecompute, 'all')
       pleaseComputeMetric = 1;
   % check if the metric in question is one user specifically asked to
   % recompute
   elseif contains(Params.metricsToRecompute, netMetName)
       pleaseComputeMetric = 1;
   else 
       % various checks to see if the metric already existed before
       prevComputed = checkMetricPrevComputed(prevNetMet, lagValFieldName, netMetName);
       pleaseComputeMetric = (1 - prevComputed);
   end 
else 
     % if metric is alredy previously computed, then do not recompute it
     prevComputed = checkMetricPrevComputed(prevNetMet, lagValFieldName, netMetName);
     pleaseComputeMetric = (1 - prevComputed);
end


end

