%% Script to run pipeline app and propagate settings back to Params
app = AnalysisPipelineApp;
app.PipelineStatusTextArea.Value = {'Welcome!, Analysis Pipeline GUI is launched'};
app.UITable.Data = [ ...
   1, 0.996, 0.670, 0.318; ...
   2, 0.780, 0.114, 0.114; ... 
   3, 0.459, 0.000, 0.376; ...  
   4, 0.027, 0.306, 0.659; ...
   5, 0.5, 0.5, 0.5; ...
   6, 0, 0, 0; ...
   7, 0, 0, 0; ...
   8, 0, 0, 0; ...
   9, 0, 0, 0; ...
   10, 0, 0, 0; ...
];
app.UITable.ColumnEditable = [true, true, true, true];
while app.RunPipelineButton.Value == 0

    % previous analysis fields
    if app.UsePreviousAnalysisCheckBox.Value == 0
        app.PreviousAnalysisDateEditField.Enable = 'Off';
        app.PreviousAnalysisDateEditFieldLabel.Enable = 'Off';
        app.PreviousAnalysisFolderEditField.Enable = 'Off';
        app.PreviousAnalysisFolderEditFieldLabel.Enable = 'Off';
        app.SpikeDataFolderEditField.Enable = 'Off';
        app.SpikeDataFolderEditFieldLabel.Enable = 'Off';
    else
        app.PreviousAnalysisDateEditField.Enable = 'On';
        app.PreviousAnalysisDateEditFieldLabel.Enable = 'On';
        app.PreviousAnalysisFolderEditField.Enable = 'On';
        app.PreviousAnalysisFolderEditFieldLabel.Enable = 'On';
        app.SpikeDataFolderEditField.Enable = 'On';
        app.SpikeDataFolderEditFieldLabel.Enable = 'On';
    end 

    % check if all required parameters are set
    homeDirSet = 1 - isempty(app.HomeDirectoryEditField.Value);
    if homeDirSet
        app.AllrequiredparameterssetLamp.Color = [0 1 0];
    else
        app.AllrequiredparameterssetLamp.Color = [1 0 0];
    end

    pause(0.1)
end 
app.PipelineStatusTextArea.Value = [app.PipelineStatusTextArea.Value; 'Starting analysis!'];
