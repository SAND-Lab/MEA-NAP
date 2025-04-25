function [adjMs, coords, channels, FisCell, FdenoisedIsCell, spksIsCell, spikeTimes, fs, Params, activityProperties] = suite2pToAdjm(suite2pFolder, Params, Info, oneFigureHandle)
%SUITE2PTOADJM Converts suite2p data to adjacency matrix 
%   Detailed explanation goes here

% Params = struct();
% Info = struct();
% adjMs = struct();

% Info.dataType = 'suite2p';
% Info.Grp = {'suite2p'}; 
% Info.FN = {'suite2pFile1'};
% Info.DIV = {1};

activityProperties = struct();

% suite2pFolder = '/home/timothysit/testSuite2pData/';

spksFpath = fullfile(suite2pFolder, 'spks.npy');
spks = readNPY(spksFpath);
iscellFpath = fullfile(suite2pFolder, 'iscell.npy');
iscell = readNPY(iscellFpath);
spksIsCell = spks(logical(iscell(:, 1)), :)';

Ffpath = fullfile(suite2pFolder, 'F.npy');
F = readNPY(Ffpath);
FisCell = F(logical(iscell(:, 1)), :)';

channels = 1:size(F, 1);
channels = channels(logical(iscell(:, 1)));

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
fs = double(fs);  % in case function returns Python int object

% Update parameter struct with new fs (should be one per file)
% This will be used in downstream steps for creating spikeMatrix
Params.fs = fs;


% do denoising and get peaks 
if strcmp(Params.twopActivity, 'peaks') || strcmp(Params.twopActivity, 'denoised F') || strcmp(Params.twopActivity, 'spks')
    resampleHz = 0;
    denoisePy.do_suite2p_processing(suite2pFolder, resampleHz, Params.twopRedoDenoising, ...
        Params.twopDenoisingThreshold, Params.twopDenoisingTimeBeforePeak, Params.twopDenoisingTimeAfterPeak);
    
    peakStartFramesPath = fullfile(suite2pFolder, 'peakStartFrames.npy');
    peakEndFramesPath = fullfile(suite2pFolder, 'peakEndFrames.npy');
    peakHeightsPath = fullfile(suite2pFolder, 'peakHeights.npy');
    eventAreasPath = fullfile(suite2pFolder, 'eventAreas.npy');
    
    FdenoisedPath = fullfile(suite2pFolder, 'Fdenoised.npy');
    timePointsPath = fullfile(suite2pFolder, 'timePoints.npy');
    timePoints = readNPY(timePointsPath);
    Fdenoised = readNPY(FdenoisedPath);
    peakStartFrames = readNPY(peakStartFramesPath);
    peakEndFrames = readNPY(peakEndFramesPath);
    peakHeights = readNPY(peakHeightsPath); 
    eventAreas = readNPY(eventAreasPath);
    peakDurationFrames = peakEndFrames - peakStartFrames;
    
    
    peakStartFramesIsCell = peakStartFrames(logical(iscell(:, 1)), :);
    peakDurationFramesIsCell = peakDurationFrames(logical(iscell(:, 1)), :);
    peakHeightsIsCell = peakHeights(logical(iscell(:, 1)), :);
    eventAreasIsCell = eventAreas(logical(iscell(:, 1)), :);
    
    FdenoisedIsCell = Fdenoised(logical(iscell(:, 1)), :)';
    
    
    
end


terminate(pyenv)

XYlocIsCell = XYloc(:, logical(iscell(:, 1)));
coords = XYlocIsCell';

if Params.removeNodesWithNoPeaks
    % Subset only cells with peaks 
    cellSubsetIndex = find(1 - all(isnan(peakStartFramesIsCell), 2));
    FdenoisedIsCell = FdenoisedIsCell(:, cellSubsetIndex);
    
    peakStartFramesIsCell = peakStartFramesIsCell(cellSubsetIndex, :);
    peakDurationFramesIsCell = peakDurationFramesIsCell(cellSubsetIndex, :);
    peakHeightsIsCell = peakHeightsIsCell(cellSubsetIndex, :);
    eventAreasIsCell = eventAreasIsCell(cellSubsetIndex, :);
    
    FisCell = FisCell(:, cellSubsetIndex);
    spksIsCell = spksIsCell(:, cellSubsetIndex);
    channels = channels(cellSubsetIndex);
    coords = coords(cellSubsetIndex, :);
    activityProperties.cellsWithPeaks = cellSubsetIndex;
end 

% Get peak / event properties
activityProperties.peakDurationFrames = peakDurationFramesIsCell;
activityProperties.peakHeights = peakHeightsIsCell;
activityProperties.eventAreas = eventAreasIsCell;

% normalise to max, then scale by 8 
maxXY = max(XYloc(:));
minXY = min(XYloc(:));
coords = (coords - minXY) / (maxXY - minXY);
coords = coords * 8;

lagVal = round(1 / fs * 1000);



%% Get adjacency matrix

if strcmp(Params.twopActivity, 'F')
    adjMs.(strcat(['adjM', num2str(lagVal), 'mslag'])) = double(corr(FisCell));
    Params.FuncConLagval = round(1/fs * 1000);
    spikeTimes = [];
elseif strcmp(Params.twopActivity, 'spks')
    adjMs.(strcat(['adjM', num2str(lagVal), 'mslag'])) = double(corr(spksIsCell));
    Params.FuncConLagval = round(1/fs * 1000);
    spikeTimes = [];
elseif strcmp(Params.twopActivity, 'denoised F')
    adjMs.(strcat(['adjM', num2str(lagVal), 'mslag'])) = double(corr(FdenoisedIsCell));
    Params.FuncConLagval = round(1/fs * 1000);
    spikeTimes = [];
elseif strcmp(Params.twopActivity, 'peaks')
    % Make spike times structure
    numcell = size(peakStartFramesIsCell, 1);
    numTimeBins = size(FisCell, 1);
    spikeTimes = cell(1, numcell);
    
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
    duration_s = numTimeBins / fs;
    
    for p = 1:length(Params.FuncConLagval)
        lag = Params.FuncConLagval(p);
        
        if length(spikeTimes) >= 2
            
            % if it is a randomly chosen check point
            if Params.randRepCheckExN2p(Params.ExN) && (lag == Params.randRepCheckLag2p(Params.ExN))  
                % plot data over incresing repetition number to check stability of
                % probabilistic thresholding
                [oneFigureHandle, ~, adjMci] = adjM_thr_checkreps(spikeTimes, 'peak', lag, Params.ProbThreshTail, fs,...
                    duration_s, Params.ProbThreshRepNum, oneFigureHandle);
    
                % Export figure
                figFolder = fullfile(Params.outputDataFolder, ...
                            Params.outputDataFolderName, '3_EdgeThresholdingCheck');
                figName = strcat([char(Info.FN), num2str(lag), 'msLagProbThreshCheck']);
                figPath = fullfile(figFolder, figName);
                pipelineSaveFig(figPath, Params.figExt, Params.fullSVG, oneFigureHandle);
                
                if ~Params.showOneFig
                    close all
                else
                    clf(oneFigureHandle)
                end 

            else

                [~, adjMci] = adjM_thr_parallel(spikeTimes, 'peak', lag, Params.ProbThreshTail, fs,...
                            duration_s, Params.ProbThreshRepNum);

            end 
        else 
            adjMci = [];
        end
        lagFieldName = strcat('adjM', num2str(lag), 'mslag');
        adjMs.(lagFieldName) = adjMci;
    end
    
end 

% Info.channels = channels;

% save(fullfile(saveFolder, saveName), 'Params', 'Info', 'coords', 'channels', 'adjMs');


end

