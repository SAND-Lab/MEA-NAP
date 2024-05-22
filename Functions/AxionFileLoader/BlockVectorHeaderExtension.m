%{
    Copyright (c) 2024 Axion BioSystems, Inc.
    Contact: support@axion-biosystems.com
    All Rights Reserved
%}
classdef BlockVectorHeaderExtension < Entry
    %BlockVectorHeaderExtension: Contains additional metadata about a loaded
    %   Block vector set.
    %
    %   ExtensionVersionMajor:  Latest and greatest is currently 1
    %
    %   ExtensionVersionMinor:  Latest and greatest is currently 0
    %
    %   DataType                Type of the data in this entry
    %                           (BlockVectorDataType.m)
    %
    %   Added:                  DateTime that this DataSet was last
    %                           Added to the file (DateTime.m)
    %
    %   Modified:               DateTime that this DataSet was last
    %                           modified (DateTime.m)
    %
    %   Name:   `               Name for this dataset (May be blank)
    %
    %   Description:            Textual metadata from axis with processing
    %                           metadata for this dataset

    properties(Constant, GetAccess = private)
       MaxNameChar = 50;
    end

    properties(GetAccess = public, SetAccess = private)
       ExtensionVersionMajor
       ExtensionVersionMinor
       DataType
       Added
       Modified
       Name
       Description
    end

    methods(Access = public)
        function this = BlockVectorHeaderExtension(aEntryRecord, aFileID)
            this = this@Entry(aEntryRecord, int64(ftell(aFileID)));

            this.ExtensionVersionMajor   = fread(aFileID, 1, 'uint16=>uint16');
            this.ExtensionVersionMinor   = fread(aFileID, 1, 'uint16=>uint16');
            this.DataType                = BlockVectorDataType.TryParse(fread(aFileID, 1, 'uint16=>uint16'));
            this.Added                   = DateTime(aFileID);
            this.Modified                = DateTime(aFileID);
            this.Name                    = deblank(fread(aFileID, ...
                (BlockVectorHeaderExtension.MaxNameChar), '*char').');
            this.Description             = deblank(fread(aFileID, ...
                (this.Start + this.EntryRecord.Length) - ftell(aFileID) , '*char').');

        end
    end
end