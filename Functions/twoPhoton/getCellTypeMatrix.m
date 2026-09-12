function [cellTypeMatrix, cellTypeNames] = getCellTypeMatrix(cellTypesTable, channels)
%GETCELLTYPEMATRIX Convert input cell type table to binary matrix of cell
%types
%   Detailed explanation goes here
%   cellTypesTable : Info.CellTypes
%     this is a table (read from csv) which contains the cell type of ROIs
%     from suite2p, this uses 0-indexing and indexes ROIs (ie. regardless
%     of whether it is a cell or not according to the `iscell` variable)
%   channels : vector 
%     this is a vector of the "channel" id used in MEA-NAP, derived from
%     suite2p index, this uses 1-indexing and again indexes ROI regardless
%     of whether it is a cell or not. Basicallly, suite2p index + 1.

cellTypesArray = table2array(cellTypesTable) + 1;  % go from 0-indexing to 1-indexing
numCellTypes = size(cellTypesArray, 2);
cellTypeMatrix = zeros(length(channels), numCellTypes);
cellTypeNames = cellTypesTable.Properties.VariableNames;


for cellTypeColumnIdx = 1:numCellTypes
    cellIds = cellTypesArray(:, cellTypeColumnIdx);
    cellIds = cellIds(~isnan(cellIds));
    cellIdsInChannel = cellIds(ismember(cellIds, channels));
    % can probably vectorised find, but this is easier to understand
    cellIndices = zeros(length(cellIdsInChannel), 1);
    for cellIdx = 1:length(cellIdsInChannel)
        cellIndices(cellIdx) = find(channels == cellIdsInChannel(cellIdx));
    end
    cellTypeMatrix(cellIndices, cellTypeColumnIdx) = 1;
end

end

