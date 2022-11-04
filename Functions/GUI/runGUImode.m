function runGUImode()
% Runs GUI mode for MEA-NAP 
    % CreateStruct.Interpreter = 'tex';
    % CreateStruct.WindowStyle = 'modal';
    opts = struct(); 
    opts.Default = 'Okay';
    opts.Interpreter = 'tex';
    helloBox = questdlg("\fontsize{20} Hello! Welcome to the MEA network analysis pipeline (MEA-NAP)!", ...
     'Welcome!', 'Okay', opts);
    clear helloBox
    
    opts = struct(); 
    opts.Default = 'Okay';
    opts.Interpreter = 'tex';
    selectHomeDir = questdlg("\fontsize{20} First, please select the folder where your MEApipeline.m script is located", ...
        'Home directory selection', 'Okay', opts);
    % uiwait(selectHomeDir);
    clear selectHomeDir

    homeDirUiGet = uigetdir(pwd, 'Please select the folder where the MEApipeline.m script is located');
    % uiwait(homeDirUiGet)
    Params.HomeDir = homeDirUiGet;

    % Ask user for raw data directory 

    rawDataAnswer = questdlg("\fontsize{20} Please select the folder containing your raw data", ...
        'Raw data folder', 'Okay', opts);
    clear rawDataAnswer
    
    rawDataUIGet = uigetdir(pwd, 'Please select the folder containing your raw data');
    rawData = rawDataUIGet;
    clear rawDataUIGet

    % Please select the spreadsheet containing the set of recordings 
    spreadSheetAnswer = questdlg("\fontsize{20} Please select the spreadsheet containing the list of files you want to run the pipeline", ...
        'Spreadsheet file', 'Okay', opts);
    spreadsheet_filename = uigetfile(pwd, 'Please select the spreadsheet');

    % Asking user if they are running pipeline the first time on raw data
    firstTimeOrNo = {'Yes', 'No'};
    [indx,tf] = listdlg('PromptString',{'Are you running this pipeline for' ...
        'the first time on this raw data?'}, ...
             'ListString',firstTimeOrNo);

    runningPipelineFirstTime = firstTimeOrNo{indx};

    if strcmp(runningPipelineFirstTime, 'Yes')
        Params.priorAnalysis = 0; 
        Params.startAnalysisStep = 1;
        detectSpikes = 1;

    elseif strcmp(runningPipelineFirstTime, 'No')
         Params.priorAnalysis = 1;
         % ask user which step they want to start the pipeline on 
         availStartAnalysisSteps = {'1 : Spike detection', '2 : Neuronal activity', ...
             '3 : Functional connectivity', '4 : Network activity', '5 : Stats and classification'};
         [indx, tf] = listdlg('PromptString',{'Please select which step you want' ...
             'to start the pipeline'}, ...
             'ListString',availStartAnalysisSteps);
         Params.startAnalysisStep = str2num(availStartAnalysisSteps{indx}(1));

    end 
    
    % Channel layout 
    drawnow; pause(0.1);
    availChanellLayout = {'MCS60', 'Axion64', 'Custom'};
    [indx,tf] = listdlg('PromptString',{'Please select which electrode',  'layout you are using'}, ...
        'ListString',availChanellLayout);
    drawnow; pause(1);
    Params.channelLayout = availChanellLayout{indx};


    % Sampling rate of recording 
    if strcmp(Params.channelLayout, 'Axion64')
        Params.fs = 12500;
    else
        Params.fs = 25000;
    end 
    
    % Ready to start pipeline 
    opts = struct();
    opts.Default = 'Run MEA-NAP!';
    opts.Interpreter = 'tex';
    pause(0.1);
    readyBox = questdlg("\fontsize{20} You are all set!", ...
     'Ready!', 'Run MEA-NAP!', opts);
    drawnow; pause(0.1);

    clear readyBox
end 