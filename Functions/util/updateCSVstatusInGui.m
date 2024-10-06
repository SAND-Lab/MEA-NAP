function updateCSVstatusInGui(app, groupNameBeginsWnumber, groupNameContainsSpecial, allDIVisValid)
%UPDATECSVSTATUSINGU Update the text field in GUI based on whether the CSV
%pass all the checks

    if groupNameBeginsWnumber
        app.MEANAPStatusTextArea.Value = [app.MEANAPStatusTextArea.Value; ...
            'WARNING: at least one of the group names in your csv file start with a number, MEANAP may not run properly', ...
            'Please ensure all group names start with a letter'];
        app.MEANAPStatusTextArea.FontColor = [1, 0, 0];
        app.RunPipelineButton.Enable = 'off';
    end 
    if groupNameContainsSpecial
        app.MEANAPStatusTextArea.Value = [app.MEANAPStatusTextArea.Value; ...
            'WARNING: at least one of the group names in your csv file contain a special character, MEANAP may not run properly', ...
            'Please ensure group names only contain letters, numbers and/or underscores'];
        app.MEANAPStatusTextArea.FontColor = [1, 0, 0];
        app.RunPipelineButton.Enable = 'off';
    end 

    if ~allDIVisValid 
        app.MEANAPStatusTextArea.Value = [app.MEANAPStatusTextArea.Value; ...
            'WARNING: at least one of the DIV values is not a number and/or empty, MEANAP may not run properly.', ...
            'Please ensure DIV values are all numbers and do not include letters or special characters.'];
        app.MEANAPStatusTextArea.FontColor = [1, 0, 0];
        app.RunPipelineButton.Enable = 'off'; 
    end 
    
    % CSV checks out!
    if (~groupNameBeginsWnumber) && (~groupNameContainsSpecial) && (allDIVisValid)
        app.RunPipelineButton.Enable = 'on'; 
        app.MEANAPStatusTextArea.FontColor = [0, 0, 0];
    end
    
end

