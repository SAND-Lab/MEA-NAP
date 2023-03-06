function minMax = findMinMaxNetMetTable(outputDataDateFolder, Params)
% Find the min and max values of each extracted feature in all recordings
% combined

spreadsheetFname = strcat('NetworkActivity_RecordingLevel', '.csv');
spreadsheetFpath = fullfile(outputDataDateFolder, spreadsheetFname);
recordingLevelTable = readtable(spreadsheetFpath);

electrodeSpreadsheetFname = strcat('NetworkActivity_NodeLevel','.csv');
electrodeSpreadsheetFpath = fullfile(outputDataDateFolder, electrodeSpreadsheetFname);
nodeLevelTable = readtable(electrodeSpreadsheetFpath);

% Find min max of each column and return structure

for netMetIdx = 1:length(Params.networkLevelNetMetToPlot)
    
    netMetStr = Params.networkLevelNetMetToPlot{netMetIdx};
    minMax.(netMetStr) = [min(recordingLevelTable.(netMetStr)), ...
                       max(recordingLevelTable.(netMetStr))];
    
end 

for electrodeMetIdx = 1:length(Params.unitLevelNetMetToPlot)
    
    eMetStr = Params.unitLevelNetMetToPlot{electrodeMetIdx};
    minMax.(eMetStr) = [min(nodeLevelTable.(eMetStr)), ...
                       max(nodeLevelTable.(eMetStr))];
    
    
end 


end 