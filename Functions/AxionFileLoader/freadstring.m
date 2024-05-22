%{
    Copyright (c) 2024 Axion BioSystems, Inc.
    Contact: support@axion-biosystems.com
    All Rights Reserved
%}
function FileString = freadstring( aFileID )
%FREADSTRING reads a unicode string starting at the current location 
%of the file handle held by aFileID. Note that this function assumes that the
%next 4 bytes will be an int32 that gives the length of a utf-8 string in bytes,
%immediately after it.

    fBytes = fread(aFileID, 1, 'int32=>int32');
    fBytes = fread(aFileID, double(fBytes), 'uint8=>uint8');
    fBytes = fBytes';
    FileString = native2unicode(fBytes, 'UTF-8');

end

