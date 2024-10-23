function suite2pMode = appCheckSuite2pData(app)
%APPCHECKSUITE2PDATA Summary of this function goes here
%   Detailed explanation goes here
    files = dir(app.MEADataFolderEditField.Value); % get a list of all files and folders
    dirFlags = [files.isdir];         % find all items that are directories
    subfolders = files(dirFlags);     % extract only the directories

    % Exclude '.' and '..' which refer to the current and parent directories
    subfolderNames = {subfolders.name};  % get names of the directories
    subfolderNames = subfolderNames(~ismember(subfolderNames, {'.', '..'}));
    numSuite2pFiles = 0;
    for subFolderIdx = 1:length(subfolderNames)
        subFolderFullPath = fullfile(app.MEADataFolderEditField.Value, subfolderNames{subFolderIdx});
        if isfile(fullfile(subFolderFullPath, 'suite2p', 'stat.npy'))
            numSuite2pFiles = numSuite2pFiles + 1;
        end
    end
    
    if numSuite2pFiles > 0
        app.MEANAPStatusTextArea.Value = [app.MEANAPStatusTextArea.Value; ...
            sprintf('%.f folder found with suite2p files', numSuite2pFiles)];
        app.StartAnalysisStepEditField.Value = '3';
        suite2pMode = 1;

        % get python path 
        terminate(pyenv)
        pythonEnvHandle = pyenv('ExecutionMode','OutOfProcess');
        pythonPath = pythonEnvHandle.Executable;
        app.PythonpathEditField.Value = pythonPath;
    else 
        suite2pMode = 0;
    end 
end

