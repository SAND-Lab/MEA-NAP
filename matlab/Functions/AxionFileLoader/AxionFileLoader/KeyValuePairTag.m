%{
    Copyright (c) 2024 Axion BioSystems, Inc.
    Contact: support@axion-biosystems.com
    All Rights Reserved
%}
classdef KeyValuePairTag < Tag
    properties(SetAccess = private)
        % Key of this Dictonary Entry
        Key;
        % Key of this Dictonary Entry
        Value;
    end

    methods
        function this = KeyValuePairTag(aFileID, aRawTag)
            this = this@Tag(aRawTag.TagGuid);

            fStart = aRawTag.Start + TagEntry.BaseSize;
            fSeekResult = fseek(aFileID, fStart, 'bof');

            if(fSeekResult == 0)
                this.Key = freadstring(aFileID);
                this.Value = freadstring(aFileID);
            else
                error('Encountered an error while loading LeapInductionEvent %s', aRawTag.TagGuid);
            end

            fStart = aRawTag.Start + TagEntry.BaseSize;
            if ftell(aFileID) >  (fStart + aRawTag.EntryRecord.Length)
                warning('File may be corrupt');
            end

        end
    end

end