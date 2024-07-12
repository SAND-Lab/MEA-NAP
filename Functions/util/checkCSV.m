function [groupNameBeginsWnumber, groupNameContainsSpecial] = checkCSV(csv_data)
%CHECKCSV Summary of this function goes here
%   Detailed explanation goes here
    groupNames = csv_data(:, 3); 
    groupNames = groupNames.(1);

    groupNameBeginsWnumber = 0;
    groupNameContainsSpecial = 0;
    
    charsToCheck = '+?-!';
    
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
    

end

