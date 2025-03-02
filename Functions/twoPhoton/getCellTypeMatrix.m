function [cellTypeMatrix, cellTypeNames] = getCellTypeMatrix(cellTypesTable, channels)
%GETCELLTYPEMATRIX Summary of this function goes here
%   Detailed explanation goes here
%   cellTypesTable : Info.CellTypes

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

