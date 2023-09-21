function app = setAppParams(app, Params)
%SETAPPPARAMS Summary of this function goes here
%   Detailed explanation goes here


app.HomeDirectoryEditField.Value = Params.HomeDir;
app.OutputDataFolderEditField.Value = Params.outputDataFolder;
app.RawDataFolderEditField.Value = Params.rawData;

app.PreviousAnalysisFolderEditField.Value = Params.priorAnalysisPath;
app.UsePreviousAnalysisCheckBox.Value = Params.priorAnalysis;
app.PreviousAnalysisDateEditField.Value = Params.priorAnalysisDate;

app.SpikeDataFolderEditField.Value = Params.spikeDetectedData;
app.SpreadsheetfilenameEditField.Value = Params.spreadSheetFileName;


%%%%%%%%%%%%%%%%%%%%%%%%%% GUI SPECIFIC SETTINGS %%%%%%%%%%%%%%%%%%%%%%%
app.ShowAdvancedSettingsCheckBox.Value = Params.showAdvancedSetting;


end

