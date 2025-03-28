%{
    Copyright (c) 2024 Axion BioSystems, Inc.
    Contact: support@axion-biosystems.com
    All Rights Reserved
%}
classdef EntryRecord
    %ENTRYRECORD Structure representing an area of data in an Axis file
    %
    %   Type:   Type of data in the associated entry. See: EntryRecordID.m
    %
    %   Length: Length (in bytes) of the associated data entry.
    %

    properties(Constant, GetAccess = private)
        LENGTH_MASK_HIGH = uint64(hex2dec(  'ffffff'));
        LENGTH_MASK_LOW  = uint64(hex2dec('ffffffff'));

    end

    properties(GetAccess = public, SetAccess = private)
        Type
        Length
    end

    methods
        function this = EntryRecord(aType, aLength)
            if nargin > 0
                this.Type = EntryRecordID(aType);
                if(isinf(aLength) == 1)
                    this.Length = inf;
                else
                    this.Length = int64(aLength);
                end
            end
        end
    end

    methods(Static = true)

        function this = FromUint64(aValues)
            % FromUint64: Deserailizes an entry record from its native 64
            % bit format in AxIS files.
            %
            %   ----------------64 Bits--------------
            %   | ID (1 Byte) |   Length (7 Bytes)  |
            %   -------------------------------------
            %
            % Note that only the last entry in a file amy have length ==
            % (0x00ff ffff ffff  ffff) which denotes an entry that reads to
            % the end of the file. These entrist have a length feild == inf
            % when deserialized
            %
            this = EntryRecord.empty(0, length(aValues));

            if(~isa(aValues, 'uint64'))
                error('EntryRecord.FromUint64: aValues must be of type uint64)');
            end

            for i= 1:length(aValues)
                long = aValues(i);
                % Read the upper word (with ID feild)
                [fID, fHaveParser] = EntryRecordID.TryParse(bitshift(long, int8(8-64)));
                % Shift right 4 bytes and mask with LENGTH_MASK_HIGH
                fLength = uint64(bitand(bitshift(long, int8(32-64)), EntryRecord.LENGTH_MASK_HIGH));
                % Start the check to see if this may be a 'Read to the end'
                % style EntryRecord
                fIsinf = fLength == EntryRecord.LENGTH_MASK_HIGH;
                % Shift left 4 bytes to be andded with lower word
                fLength = uint64(bitshift(fLength, 32));

                % Read the lower word
                fLowWord = uint64(bitand(long, EntryRecord.LENGTH_MASK_LOW));
                % Finish the check to see if this may be a 'Read to the end'
                % style EntryRecord
                fIsinf = fIsinf && (fLowWord == EntryRecord.LENGTH_MASK_LOW);

                %Recombine the upper and lower length portions.
                fLength = int64(bitor(...
                    fLength,...
                    fLowWord));

                % If we don't know this Entry record type, read it as
                % skipped
                if(~fHaveParser)
                    fID = EntryRecordID.Skip;
                end

                if(fIsinf)
                    this(i) = EntryRecord(fID, inf);
                else
                    this(i) = EntryRecord(fID, fLength);
                end
            end
        end
    end
end

