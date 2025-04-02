function [groupNameBeginsWnumber, groupNameContainsSpecial, allDIVisValid, groupNameIllegal] = checkCSV(csv_data)
%CHECKCSV Summary of this function goes here
%   Detailed explanation goes here
    groupNames = csv_data(:, 3); 
    groupNames = groupNames.(1);

    groupNameBeginsWnumber = 0;
    groupNameContainsSpecial = 0;
    groupNameIllegal = 0;
    
    charsToCheck = '+?-!()';
    
    for groupIdx = 1:length(groupNames)
        groupStr = groupNames{groupIdx}; 
        startStr = groupStr(1);
        if ~isnan(str2double(startStr))
            groupNameBeginsWnumber = 1;
        end 
        
        if any(ismember(groupStr, charsToCheck))
            groupNameContainsSpecial = 1;
        end 
        
    end 
    
    eachDIVisValid = 1 - cellfun(@isnan,table2cell(csv_data(:,2)));
    allDIVisValid = (length(eachDIVisValid) == sum(eachDIVisValid));
    
    % Check ground electrode column
    groundContainLetter = zeros(size(csv_data, 1), 1);
    if size(csv_data, 2) >= 4
        groundValues = csv_data{:, 4};
        for rowIdx = 1:size(csv_data, 1)
            groundContainLetter(rowIdx) = any(isletter(groundValues{rowIdx}));
        end
    end 
    
    anyGroundContainLetter = (sum(groundContainLetter) > 0);
    
    illegalGroupNames = {'CON', 'PRN', 'AUX', 'NUL', 'COM', 'LPT'};  % On Windows devices, adding COM and LPT just to be safe
    for groupIdx = 1:length(groupNames)
        groupStr = groupNames{groupIdx};
        if ismember(lower(groupStr), lower(illegalGroupNames))
            groupNameIllegal = 1;
        end 
            
    end 
    
    
end

