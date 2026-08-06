% Ground truth for python/test_axion_raw.py
%
% Reads an Axion .raw with Axion's own bundled MATLAB toolbox, driven exactly
% the way Functions/convertRawToMat/rawConvertFunc.m drives it, and saves one
% reference per well. The Python reader must reproduce these bit-for-bit.
%
% The .raw itself is not in the repo (they are gigabytes). Point RAW_FILE at a
% recording and re-run; the saved references are small because only the first
% couple of seconds are kept.
%
% Usage (from the repo root):
%   matlab -batch "run('python/test_fixtures/gen_axion_reference.m')"

RAW_FILE = fullfile(getenv('HOME'), 'Downloads', 'Plate2_treated24hrs_DIV75.raw');
WELLS    = {'A1', 'B3', 'D6', 'C1', 'A6'};
SECONDS  = [0 2];

thisDir = fileparts(mfilename('fullpath'));
addpath(genpath(fullfile(thisDir, '..', '..', 'Functions', 'AxionFileLoader')));

if ~isfile(RAW_FILE)
    error('Axion raw file not found: %s', RAW_FILE);
end

D = AxisFile(RAW_FILE).RawVoltageData;
allChannels = D.ChannelArray.Channels;
rownames = 'ABCDEFGH';

fprintf('%s\n', RAW_FILE);
fprintf('  fs = %.10g Hz, VoltageScale = %.17g\n', D.SamplingFrequency, D.VoltageScale);
fprintf('  PlateType = %d, %d channels, DataRegion %d + %d bytes\n', ...
    double(D.ChannelArray.PlateType), numel(allChannels), ...
    D.DataRegionStart, D.DataRegionLength);

for w = 1:numel(WELLS)
    well = WELLS{w};
    wellRow = find(rownames == well(1));
    wellCol = str2double(well(2:end));

    AllData = D.LoadData(well, SECONDS);
    waveforms = [AllData{wellRow, wellCol, :, :}];

    % Same two lines rawConvertFunc.m uses to build a per-well .mat
    dat = waveforms.GetVoltageVector;
    wfChannels = {waveforms.Channel};
    channels = zeros(numel(wfChannels), 1);
    for k = 1:numel(wfChannels)
        channels(k) = double(wfChannels{k}.ElectrodeColumn) * 10 + ...
                      double(wfChannels{k}.ElectrodeRow);
    end

    % Index of each electrode within the plate-wide channel array, so the Python
    % reader's column ordering can be checked as well as its sample values.
    idx = zeros(numel(wfChannels), 1);
    for k = 1:numel(wfChannels)
        for a = 1:numel(allChannels)
            if allChannels(a).WellRow    == wfChannels{k}.WellRow && ...
               allChannels(a).WellColumn == wfChannels{k}.WellColumn && ...
               allChannels(a).ElectrodeRow    == wfChannels{k}.ElectrodeRow && ...
               allChannels(a).ElectrodeColumn == wfChannels{k}.ElectrodeColumn
                idx(k) = a;
                break;
            end
        end
    end

    outFile = fullfile(thisDir, sprintf('axion_well_%s_reference.mat', well));
    save(outFile, '-v7.3', 'dat', 'channels', 'idx');
    fprintf('  %s: %d samples x %d electrodes -> %s\n', ...
        well, size(dat, 1), size(dat, 2), outFile);
end

fprintf('done\n');
