function createBatchCSVFile(raw_file_dir, batch_csv_fname, autofill_div, autofill_genotype, genotype)
    % Create batch .csv file containing information
    % (recording filenames, DIVs, genotypes, and ground electrodes). 
    % Function written by DO, Nov 2023
    % Overall aim of this script is to assist the functionality of
    % rawConvert.m. 
    % Update log 
    % ----------
    % 2024-09-19 : 
    % Also moves to the next row when autofill_div is not 'y' (Tim Sit)

    % Change to the specified directory
    cd(raw_file_dir);

    % Get a list of .mat files in the directory
    mat_files = dir('*.mat');

    % Create the full path for the metadata file
    batch_csv_file = fullfile(raw_file_dir, batch_csv_fname);

    % Define the headers for the batch .csv file
    batch_csv_Hdrs = {'Recording filename', 'DIV group', 'Genotype', 'Ground'};

    % Initialize variables
    row_number = 1; % row number in batch .csv file
    div_str = ''; % string that will be updated with the DIV of each recording filename that contains DIV in the format DIVXX (i.e., DIV7, DIV14)

    % Initialize cell arrays for batch data
    batch_csv_cell = cell(length(mat_files), length(batch_csv_Hdrs));
    batch_csv_table = cell2table(batch_csv_cell, 'VariableNames', batch_csv_Hdrs);

    % Iterate through each .mat file
    for i = 1:length(mat_files)

        % Extract filename without extension
        mat_fname = mat_files(i).name(1:end-4);

        % Automatically fill Filename column
        batch_csv_table.('Recording filename'){row_number} = mat_fname;

        % Automatically fill Genotype column if specified
        if strcmp(autofill_genotype, 'y')
            batch_csv_table.Genotype(:, 1) = {genotype};
        end

        % Automatically fill DIV column if specified
        if strcmp(autofill_div, 'y')
            ii = strfind(mat_fname, 'DIV') + 3;

            % Extract digits from the filename to get DIV value
            while isstrprop(mat_fname(ii), 'digit')
                div_str = append(div_str, mat_fname(ii));
                ii = ii + 1;
            end

            % Fill DIV column in the current row
            batch_csv_table.('DIV group'){row_number} = div_str;

            % Move to the next row
            row_number = row_number + 1;
            div_str = ''; % Reset div_str for the next iteration
        else 
            batch_csv_table.('DIV group'){row_number} = 0;
            % Move to the next row
            row_number = row_number + 1;
        end
    end

    % Write the batch table to the specified metadata file
    writetable(batch_csv_table, batch_csv_file)
end

