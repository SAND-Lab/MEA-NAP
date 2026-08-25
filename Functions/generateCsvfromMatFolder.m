fprintf('Generating CSV with given rawData folder \n')
mat_file_list = dir(fullfile(rawData, '*mat'));
name_list = {mat_file_list.name}';
name_without_ext = {};
div = {};
for filenum = 1:length(name_list)
    name_without_ext{filenum} = name_list{filenum}(1:end-4);
    
    if strcmp(name_without_ext{filenum}(1:2), '._')
        name_without_ext{filenum} = name_list{filenum}(3:end-4);
    end 

    div{filenum} = name_list{filenum}((end-5):end-4);
end 
name = name_without_ext'; 
div = div';
name_table = table([name, div]);
writetable(name_table, spreadsheet_filename)