function rawConvertFunc(HomeDir, raw_file_dir, batch_csv_fname, autofill_div, autofill_genotype, genotype, fs)
% Parameters 
% ----------
% HomeDir : 
% raw_file_dir : 
% batch_csv_fname : 
% autofill_div : 
% autofill_genotype : 
% genotype : 
% fs : int 
%      sampling frequency of your recording (Hz)
% Use this script to convert raw data collected with the Axion Maestro MEA system
% from plate to individual MEAs.  This is the first step to using the data with our 
% analysis pipeline developed for MCS data.
%
% Function written by MH, Dec 2021; edited by SM, Jan 2022; edited by DO,
% Nov 2023. Edited by TS 2024

% Overall aim of this script is to split raw data from multi-well plate
% into a separate .mat file for each MEA in the plate.  It can currently
% accommodate 6- up to 48-well plates.  
% Function written by MH, Dec 2021; edited by SM, Jan 2022; edited by DO,
% Nov 2023. Edited by TS 2024

% Overall aim of this script is to split raw data from multi-well plate
% into a separate .mat file for each MEA in the plate.  It can currently
% accommodate 6- up to 48-well plates.

% Step 1 - Specify the path of your MEA-NAP directory
% HomeDir = '[INPUT REQUIRED]';

% Step 2 - Load the folder where your .raw data files are from plate to individual MEAs.  This is the first step to using the data with our 
% analysis pipeline developed for MCS data. Please include appropriate slash (/ or \) at the end of your path. 
% raw_file_dir = '[INPUT_REQUIRED]';

% Step 3 - Name of the batch csv file that will be created in directory containing raw files (raw_file_dir). 
% This .csv file stores information about your recordings, including recording filename, DIV, genotype, and grounded electrodes.
if ~contains(batch_csv_fname, '.csv')
    batch_csv_fname = [batch_csv_fname, '.csv'];
end 
batch_csv_fname = [batch_csv_fname];

% Step 4 - Adjust these additional settings to automatically fill certain columns of batch .csv file (batch_csv_fname).
% autofill_div = '[INPUT_REQUIRED]'; %Do your recording filenames include DIV in the following format: DIV7, DIV14, DIV21, etc. ('y' for yes, 'n' for no)
% autofill_genotype = '[INPUT_REQUIRED]'; %Did you only use one genotype group for this set of recordings? ('y' for yes, 'n' for no) 
% genotype = '[INPUT_REQUIRED]'; %If user answered no ('n') for autofill_genotype, leave as empty string (''). Otherwise, write your genotype group as a MATLAB string array. 

if ~ischar(autofill_div)
    if autofill_div == 0
        autofill_div = 'n';
    else
        autofill_div = 'y';
    end 
end 

if ~ischar(autofill_genotype)
    if autofill_genotype == 0
        autofill_genotype = 'n';
    else
        autofill_genotype = 'y';
    end 
end  

if strcmp(autofill_genotype, 'n')
    genotype = '';
end 

% Verify variables in Step 3 have been set to valid values
assert((isequal(autofill_div, 'y') | isequal(autofill_div, 'n')), "User did not select valid option for fill_div ('y' for yes or 'n' for no).")
assert(isequal(autofill_genotype, 'y') | isequal(autofill_genotype, 'n'), "User did not select valid option for fill_genotype ('y' for yes or 'n' for no).") 
if isequal(autofill_genotype, 'n') 
    assert(isequal(genotype, '') && isa(genotype, 'char'), "User should leave genotype as empty string ('')")
elseif isequal(autofill_genotype, 'y')
    assert(isa(genotype, 'char') , "User did not enter valid option for genotype.")
end

% Add path of folder contain Axion Bioystems functions (AxIS MATLAB Files)
addpath(genpath(fullfile(HomeDir, 'Functions')))

% Loop through all of the files.  This first part extracts the names of the
% raw data files, arrangement of the wells and creates a .csv file with the
% file names for use downstream in the network analysis pipeline.
filenames = dir(raw_file_dir);
rownames = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H'];

% This line opens the .csv with the names in order to create three columns
% that are read by the network analysis pipeline.
for i = 1:length(filenames)
    if length(filenames(i).name) > 4
        suffix = filenames(i).name(end-3:end);
        % check .raw extension and remove '._' hidden files (on Mac OS)
        if (strcmp(suffix, '.raw')) && (~strcmp(filenames(i).name(1:2), '._'))
            % For each recording, this step loads the raw data calling a
            % function from the AxIS MATLAB Files folder
            AllData = AxisFile(fullfile(raw_file_dir, filenames(i).name)).RawVoltageData.LoadData;
            % For each recording, this step loops over the wells to extra
            % the voltage vectors. Again this uses functions from the AxIS
            % MATLAB File folder
            for j1 = 1:size(AllData, 1)
                for j2 = 1:size(AllData, 2)
                    temp = [AllData{j1,j2,:,:}];

                    if ~isempty(temp)
                        dat = temp.GetVoltageVector;
                        % For each individual MEA (well), this step saves the 
                        % voltage vector along with two variables used in the
                        % network analysis pipeline as an .mat file with the
                        % suffix indicating the well number (e.g., _A1).
                        savenamefile = fullfile(raw_file_dir, strcat(filenames(i).name(1:end-4), '_', rownames(j1), int2str(j2), '.mat'));
    
                        % Use row and column information to assign channel
                        % names
                        tempChannel = {temp.Channel};
                        channels = zeros(length(tempChannel), 1);
                        for channelIdx = 1:length(tempChannel)
                            channels(channelIdx) = double(tempChannel{channelIdx}.ElectrodeColumn) * 10 + double(tempChannel{channelIdx}.ElectrodeRow);
                        end
                        
                        % This is the step saves the .mat file for each MEA
                        % (well) with voltage vectors (dat), the names/location
                        % of the electrodes (channels) and  the acquisition rate (fs). 
                        % Setting MATLAB version "-v7.3" appears necessary for saving.
                        save(savenamefile, '-v7.3', "dat", "channels", "fs")
                    end 
                end
               end
            % This step adds filename without the suffix to the list for
            % batch analysis.
        end
    
    end
end

createBatchCSVFile(raw_file_dir, batch_csv_fname, autofill_div, autofill_genotype, genotype); 
cd(HomeDir)

% The next step is to run the .mat file outputs through the network
% analysis pipeline starting with the spike detection (Step 1).
end

