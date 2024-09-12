%% Downlaod example CSV and data
if ~isdir('ExampleData')
    mkdir('ExampleData');
end

availableDataSource = {'HarvardDatabase', 'Dropbox'};
downloadSource = 'Dropbox';

app.MEANAPStatusTextArea.Value = [app.MEANAPStatusTextArea.Value; ...
        'Downloading example matlab files...'];

fileNames = { ...
  'exampleData.csv', ...
  'NGN2_20230208_P1_DIV14_A2.mat', ...
  'NGN2_20230208_P1_DIV14_A3.mat', ...
};

if strcmp(downloadSource, 'HarvardDatabase')
    matlabFileIDs = [8113210, 8113213, 8113212];
    for fileIdx = 1:length(matlabFileIDs)
       matFilePath =  sprintf('https://dataverse.harvard.edu/api/access/datafile/%.f', matlabFileIDs(fileIdx));
       savePath = fullfile('ExampleData', sprintf('%.f.mat', matlabFileIDs(fileIdx)));
       if ~isfile(savePath)
           actualFileName = websave(savePath, matFilePath);
       end 
    end
elseif strcmp(downloadSource, 'Dropbox')
    downloadLinks = {...
        'https://www.dropbox.com/scl/fi/w3no80utz1onjf5d6tu1n/exampleData.csv?rlkey=xm80c5pr1xrgvwngitrez9fw2&st=ie22e58n&dl=1', ...
        'https://www.dropbox.com/scl/fi/0puoqefido0yef12roxlu/NGN2_20230208_P1_DIV14_A2.mat?rlkey=ap7ipbzgh2vqkf3b1e57wzxns&st=2xs1h1ci&dl=1', ...
        'https://www.dropbox.com/scl/fi/wduekpzvrmqc16h6ima1h/NGN2_20230208_P1_DIV14_A3.mat?rlkey=4agamhx7r8u6d5shxfugoiwaj&st=r22bpn2u&dl=1', ...
        };
    
    for fileIdx = 1:length(downloadLinks)
        savePath = fullfile('ExampleData', fileNames{fileIdx});
        if ~isfile(savePath)
            websave(savePath, downloadLinks{fileIdx});
        end 
    end
end 

app.MEANAPStatusTextArea.Value = [app.MEANAPStatusTextArea.Value; ...
        'Download complete!'];


