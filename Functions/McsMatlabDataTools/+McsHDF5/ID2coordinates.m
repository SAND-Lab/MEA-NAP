function coordinates = ID2coordinates(ID, numRows, numCols)
%Converts the sensor ID representation to its coordinate representation on
%the CMOS chip
    ID = ID - 1;
    x = floor(ID/numRows)+1;
    y = mod(ID,numRows)+1;
    %x = floor(ID/numRows)+1;
    %y = mod(ID,(floor(ID/numRows)*numRows));
    %coordinates = [ floor(ID/numRows)+1 ; mod(ID,numRows) ];
    coordinates = [ x ; y ];
    if (coordinates(1)>numRows || coordinates(2)>numCols || coordinates(1)<1 || coordinates(2)<1)
        error('Single sensor coordinates exceed total sensor size!')
    end
end

