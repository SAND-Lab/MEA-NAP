function [NetMetMinMax] = findMinMaxAllNetMetStruct(NetMetAllDat)

% find min and max for NetMet values and edges (adjM
% values) across the batch dataset

NetMetPlots = {'ND','MEW','NS','Eloc','BC','PC','Z'};

for i = 1:length(NetMetPlots)
    NetMetMinMax.(sprintf(NetMetPlots{i})) = [min(NetMetAllDat.(sprintf(NetMetPlots{i}))) max(NetMetAllDat.(sprintf(NetMetPlots{i})))];
    NetMetMinMax.adjM = [min(NetMetAllDat.adjM) max(NetMetAllDat.adjM)];
end