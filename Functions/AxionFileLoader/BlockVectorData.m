%{
    Copyright (c) 2024 Axion BioSystems, Inc.
    Contact: support@axion-biosystems.com
    All Rights Reserved
%}
classdef BlockVectorData < Entry
    %BlockVectorData contains instructions for loading the Data types
    %   (See BlockVectorDataType.m) from the data portions of the file
    %   listed in the header.

    methods
        function this = BlockVectorData(aEntryRecord, aFileID)
            %BlockVectorData: Constructs a new BlockVectorData corresponding
            % to an Entry Record and the file handle it came from
            this = this@Entry(aEntryRecord, int64(ftell(aFileID)));

            fseek(aFileID, double(this.EntryRecord.Length), 'cof');

            if ~(ftell(aFileID) == (this.Start + this.EntryRecord.Length) || isinf(this.EntryRecord.Length))
                error('Unexpected BlockVectorHeader length')
            end
        end
    end
end
