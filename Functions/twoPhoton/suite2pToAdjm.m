function [adjMs, coords, channels, FisCell, spksIsCell, fs] = suite2pToAdjm(suite2pFolder, Params)
%SUITE2PTOADJM Converts suite2p data to adjacency matrix 
%   Detailed explanation goes here

% Params = struct();
% Info = struct();
% adjMs = struct();

% Info.dataType = 'suite2p';
% Info.Grp = {'suite2p'}; 
% Info.FN = {'suite2pFile1'};
% Info.DIV = {1};

% suite2pFolder = '/home/timothysit/testSuite2pData/';
spksFpath = fullfile(suite2pFolder, 'spks.npy');
spks = readNPY(spksFpath);
iscellFpath = fullfile(suite2pFolder, 'iscell.npy');
iscell = readNPY(iscellFpath);
spksIsCell = spks(logical(iscell(:, 1)), :)';

Ffpath = fullfile(suite2pFolder, 'F.npy');
F = readNPY(Ffpath);
FisCell = F(logical(iscell(:, 1)), :)';

% pythonPath = '/home/timothysit/anaconda3/envs/suite2p/bin/python';

% pyenv("ExecutionMode","OutOfProcess", Version=Params.pythonPath)
% py.list; % Reload interprete
numpy = py.importlib.import_module('numpy');
cd(fullfile(Params.HomeDir, 'Functions', 'twoPhoton'));
readStatNPY = py.importlib.import_module('readStatNPY');
readOpsNPY = py.importlib.import_module('readOpsNPY');

cd(Params.HomeDir) 

% get cell locations
statFpath = fullfile(suite2pFolder, 'stat.npy');
XYloc = readStatNPY.getXYloc(statFpath);
XYloc = double(XYloc);

% get sampling rate 
opsFpath = fullfile(suite2pFolder, 'ops.npy');
fs = readOpsNPY.getFs(opsFpath);

terminate(pyenv)



XYlocIsCell = XYloc(:, logical(iscell(:, 1)));

% saveFolder = '/home/timothysit/AnalysisPipeline/OutputDataTestSuite2p/ExperimentMatFiles/';
% saveName = 'suite2pFile1_OutputDataTestSuite2p';

coords = XYlocIsCell';

% normalise to max, then scale by 8 
maxXY = max(XYloc(:));
minXY = min(XYloc(:));
coords = (coords - minXY) / (maxXY - minXY);
coords = coords * 8;
channels = 1:sum(iscell(:, 1));

% temporary subset 
spksIsCell = spksIsCell(:, 1:100);
channels = channels(1:100);
coords = coords(1:100, :);

lagVal = round(1 / fs * 1000);

adjMs.(strcat(['adjM', num2str(lagVal), 'mslag'])) = double(corr(spksIsCell));

% Info.channels = channels;

% save(fullfile(saveFolder, saveName), 'Params', 'Info', 'coords', 'channels', 'adjMs');


end

