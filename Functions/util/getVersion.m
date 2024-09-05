function getVersion(HomeDir, app)

localVersion = importdata(fullfile(HomeDir, 'version.txt')); 
localVersion = localVersion{1};
localVersion = strtrim(localVersion);

app.MEANAPStatusTextArea.Value = ...
            [app.MEANAPStatusTextArea.Value; ...
            sprintf('You are using version %s of MEA-NAP \n', localVersion)];

% This is where you get the latest github version code
url = 'https://raw.githubusercontent.com/SAND-Lab/MEA-NAP/main/version.txt';
% Create options for webread to avoid using the cache
options = weboptions('HeaderFields', {'Cache-Control', 'no-cache'; 'Pragma', 'no-cache'});

% Read the content of the file from the URL
try 
    onlineVersion = webread(url, options);
    onlineVersion = strtrim(onlineVersion);  % not sure why there is this end space
    
    if strcmp(localVersion, onlineVersion)
        app.MEANAPStatusTextArea.Value = ...
            [app.MEANAPStatusTextArea.Value; ...
            'Your MEA-NAP version is up to date!'];
    else
        app.MEANAPStatusTextArea.Value = ...
            [app.MEANAPStatusTextArea.Value; ...
            sprintf('Your MEA-NAP version is out of date, the latest version is %s', onlineVersion)];
    end
    
catch
   app.MEANAPStatusTextArea.Value = ...
            [app.MEANAPStatusTextArea.Value; ...
            'You are not connected to the internet, cannot check the latest version of MEA-NAP'];
end


end