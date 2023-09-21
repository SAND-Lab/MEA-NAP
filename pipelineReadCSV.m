function csv_data = pipelineReadCSV(spreadsheet_filename, csvRange)
%PIPELINEREADCSV Summary of this function goes here
%   Detailed explanation goes here
    opts = detectImportOptions(spreadsheet_filename);
    opts.Delimiter = ',';
    opts.VariableNamesLine = 1;
    opts.VariableTypes{1} = 'char';  % this should be the recoding file name
    opts.VariableTypes{2} = 'double';  % this should be the DIV
    opts.VariableTypes{3} = 'char'; % this should be Group 
    if length(opts.VariableNames) > 3
        opts.VariableTypes{4} = 'char'; % this should be Ground
    end 
    opts.DataLines = csvRange; % read the data in the range [StartRow EndRow]
    % csv_data = readtable(spreadsheet_filename, 'Delimiter','comma');
    csv_data = readtable(spreadsheet_filename, opts);
    
end

