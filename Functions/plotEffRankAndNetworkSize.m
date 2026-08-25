function [] = plotEffRankAndNetworkSize(netMetCsvPath, ymetric1, ymetric2, xmetric, groupsToIterate, idColName)


% For testing 
% netMetCsvPath = ...
% '/Users/timothysit/AnalysisPipeline/OutputData16Jun2022/NetworkActivity_RecordingLevel.csv'
groupsToIterate = 'eGrp'
ymetric1 = 'effRank';
ymetric2 = 'aN';
xmetric = 'AgeDiv';
idColName = nan;  % TODO: need to add column to identify individual recordings

csvData = readtable(netMetCsvPath);




% Export plot

end 