function ID = coordinates2ID(coordinates, numRows, numCols)
    ID = numRows*(coordinates(1)-1) + coordinates(2);
    if ID > (numRows * numCols)
        error('ID out of range!')
    end
end