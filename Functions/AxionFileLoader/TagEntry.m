%{
    Copyright (c) 2024 Axion BioSystems, Inc.
    Contact: support@axion-biosystems.com
    All Rights Reserved
%}
classdef TagEntry < Entry
    %TAGENTRY Section of an AxisFile that contains TagRevison

    properties(GetAccess = public, Constant = true)
        BaseSize = int64(2 + DateTime.Size + 16 + 4);
    end

    properties(GetAccess = public, SetAccess = private)
        % CreationDate: The date/time that this tag revision was created
        CreationDate;
        % TagGuid: GUID unique to this tag and its revisions
        TagGuid;
        % RevisionNumber: The number of times this tag has been revised up to this revision
        RevisionNumber;
        % Type: The type of event that created this tag (UserAnnotation, DataLossEvent, etc)
        Type;
    end

    methods
        function this = TagEntry(aEntryRecord, aFileID)
            this = this@Entry(aEntryRecord, int64(ftell(aFileID)));

            fTypeShort = fread(aFileID, 1, 'uint16=>uint16');
            try
               this.Type             = TagType(fTypeShort);
            catch e
                if(strcmp('MATLAB:class:InvalidEnum', e.identifier))
                    warning('TagEntry:UnknonwTagType','Unknown tag type %i will be ignored', fTypeShort);
                else
                    e.throw;
                end
               this.Type             = TagType(TagType.Deleted);
            end
            this.CreationDate        = DateTime(aFileID);
            guidBytes                = fread(aFileID, 16, 'uint8=>uint8');
            this.TagGuid             = parseGuid(guidBytes);
            this.RevisionNumber      = fread(aFileID, 1, 'uint32=>uint32');

            %Seek to the end, we only parse the heads of the TagEntries as
            %the file loads
            fseek(aFileID, int64(this.EntryRecord.Length) - TagEntry.BaseSize, 'cof');

        end
    end

end

