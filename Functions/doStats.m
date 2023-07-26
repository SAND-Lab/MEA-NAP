function statsTable = doStats(nodeLevelData, recordingLevelData, Params, lag_val, plotSaveFolder);
%DOSTATS Summary of this function goes here
%   Detailed explanation goes here

recordingLevelData = readtable('/media/timothysit/Elements/HPC_analysisPIpelineOutputs/OutputData09Jul2023/NetworkActivity_RecordingLevel.csv');

uniqueLags = unique(recordingLevelData.Lag);


% Look at how the example logitudinal data from matlab looks like 
% this = load('longitudinalData.mat');
% Maybe just use this: https://uk.mathworks.com/matlabcentral/fileexchange/5576-rmaov1

for lag = uniqueLags 
    subsetIndex = recordingLevelData.Lag == lag;
    recordingLevelDataSubset = recordingLevelData(subsetIndex, :);

    % do stats on recording level data 
    numUniqueDiv = length(unique(recordingLevelDataSubset.AgeDiv));
    numUniqueGrp = length(unique(recordingLevelDataSubset.eGrp));

    if (numUniqueDiv > 1) && (numUniqueGrp > 1)
        % two way ANOVA
    elseif (numUniqueGrp == 1) && (numUniqueDiv == 1)
        % no stats avaiable
        statsTable = nan;
    else 
        % one way repeated measures ANOVA
        if numUniqueDiv > 1
            within = table(recordingLevelData.eGrp, 'VariableNames', {'eGrp'});
            rm = fitrm(recordingLevelData, 'Dens ~ AgeDiv', 'WithinDesign', within);
            ranovatbl = ranova(rm);
        else

        end 
    end 
end 


statsTable = 1;

end

