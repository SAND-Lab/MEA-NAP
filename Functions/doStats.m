function statsTable = doStats(nodeLevelData, recordingLevelData, Params, lag_val, plotSaveFolder);
%DOSTATS Summary of this function goes here
%   Detailed explanation goes here

% do stats on recording level data 
numUniqueDiv = length(unique(recordingLevelData.AgeDiv));
numUniqueGrp = length(unique(recordingLevelData.eGrp));

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


statsTable = 1;

end

