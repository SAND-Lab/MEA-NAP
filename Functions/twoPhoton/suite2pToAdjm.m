function [adjMs, coords, channels, FisCell, spksIsCell, fs, Params] = suite2pToAdjm(suite2pFolder, Params)
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
% pythonPath = '/home/timothysit/anaconda3/envs/msi/bin/python';

% pyenv("ExecutionMode","InProcess", Version=pythonPath)
% pyenv("ExecutionMode","OutOfProcess", Version=Params.pythonPath)
% py.list; % Reload interprete
numpy = py.importlib.import_module('numpy');
cd(fullfile(Params.HomeDir, 'Functions', 'twoPhoton'));
readStatNPY = py.importlib.import_module('readStatNPY');
readOpsNPY = py.importlib.import_module('readOpsNPY');
denoisePy = py.importlib.import_module('denoiseSuite2pData');
cd(Params.HomeDir) 

% get cell locations
statFpath = fullfile(suite2pFolder, 'stat.npy');
XYloc = readStatNPY.getXYloc(statFpath);
XYloc = double(XYloc);

% get sampling rate 
opsFpath = fullfile(suite2pFolder, 'ops.npy');
fs = readOpsNPY.getFs(opsFpath);

% do denoising and get peaks 
if strcmp(Params.twopActivity, 'peaks') || strcmp(Params.twopActivity, 'denoised F')
    resampleHz = 0;
    denoisePy.do_suite2p_processing(suite2pFolder, resampleHz, Params.twopRedoDenoising)
    peakStartFramesPath = fullfile(suite2pFolder, 'peakStartFrames.npy');
    FdenoisedPath = fullfile(suite2pFolder, 'Fdenoised.npy');
    timePointsPath = fullfile(suite2pFolder, 'timePoints.npy');
    timePoints = readNPY(timePointsPath);
    Fdenoised = readNPY(FdenoisedPath);
    peakStartFrames = readNPY(peakStartFramesPath);
    peakStartFramesIsCell = peakStartFrames(logical(iscell(:, 1)), :);
    FdenoisedIsCell = Fdenoised(logical(iscell(:, 1)), :)';
end


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
%{
spksIsCell = spksIsCell(:, 1:100);
channels = channels(1:100);
coords = coords(1:100, :);
FisCell = FisCell(:, 1:100);
peakStartFramesIsCell = peakStartFramesIsCell(1:100, :);
FdenoisedIsCell = FdenoisedIsCell(:, 1:100);
%}


lagVal = round(1 / fs * 1000);

% TODO: for cell with no events


%% Get adjacency matrix

if strcmp(Params.twopActivity, 'F')
    adjMs.(strcat(['adjM', num2str(lagVal), 'mslag'])) = double(corr(FisCell));
    Params.FuncConLagval = round(1/fs * 1000);
elseif strcmp(Params.twopActivity, 'spks')
    adjMs.(strcat(['adjM', num2str(lagVal), 'mslag'])) = double(corr(spksIsCell));
    Params.FuncConLagval = round(1/fs * 1000);
elseif strcmp(Params.twopActivity, 'denoised F')
    adjMs.(strcat(['adjM', num2str(lagVal), 'mslag'])) = double(corr(FdenoisedIsCell));
    Params.FuncConLagval = round(1/fs * 1000);
elseif strcmp(Params.twopActivity, 'peaks')
    % Make spike times structure
    numcell = size(peakStartFramesIsCell, 1);
    numTimeBins = size(FisCell, 1);
    spikeTimes = cell(numcell, 1);
    
    for cell_idx = 1:numcell
        cellPeakFrames = peakStartFramesIsCell(cell_idx, :);
        cellPeakFrames = cellPeakFrames(~isnan(cellPeakFrames)) + 1;  % +1 for 1-indexing
        if isempty(cellPeakFrames)
            cellPeakTimes = [];
        else
            cellPeakTimes = timePoints(cellPeakFrames);
        end
        spikeTimes{cell_idx} = struct();
        spikeTimes{cell_idx}.peak = cellPeakTimes;
    end
    duration_s = fs * numTimeBins;
    
    for p = 1:length(Params.FuncConLagval)
        lag = Params.FuncConLagval(p);
        [~, adjMci] = adjM_thr_parallel(spikeTimes, 'peak', lag, Params.ProbThreshTail, fs,...
                    duration_s, Params.ProbThreshRepNum);
        lagFieldName = strcat('adjM', num2str(lag), 'mslag');
        adjMs.(lagFieldName) = adjMci;
    end
    
end 

% Info.channels = channels;

% save(fullfile(saveFolder, saveName), 'Params', 'Info', 'coords', 'channels', 'adjMs');


end

