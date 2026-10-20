%{
    Copyright (c) 2024 Axion BioSystems, Inc.
    Contact: support@axion-biosystems.com
    All Rights Reserved
%}
classdef StimulationLeds < Tag
    %STIMULATIONLEDS File data that enumerates LEDs used in a
    %stimulation
    properties(GetAccess = private, Constant = true)
        CurrentVersion = 0;
        MinArraySize = int64(20);
    end

    properties(SetAccess = private)
        LedGroups
    end

    methods
        function this = StimulationLeds(aFileID, aRawTag)
            this = this@Tag(aRawTag.TagGuid);

            %Move to the correct location in the file
            fStart = int64(aRawTag.Start + TagEntry.BaseSize);
            aSeekReult = fseek(aFileID, fStart, 'bof');

            fTagStart = int64(aRawTag.Start);
            fTagEnd = int64(fTagStart + aRawTag.EntryRecord.Length);

            if aSeekReult == 0
                fVersion =  fread(aFileID, 1, 'uint16=>uint16');
                switch fVersion
                    case StimulationLeds.CurrentVersion

                        fExpected = fread(aFileID, 1, 'uint16=>uint16');
                        this.LedGroups = struct([]);
                        fArray = 1;
                        fPos = int64(ftell(aFileID));
                        while (fTagEnd - fPos) >= StimulationLeds.MinArraySize
                            fId = fread(aFileID, 1, 'uint32=>uint32');
                            this.LedGroups(fArray).ID = fId;

                            fPlateType   = fread(aFileID, 1, 'uint32=>uint32');
                            this.LedGroups(fArray).PlateType = fPlateType;

                            fNumChannels = fread(aFileID, 1, 'uint32=>uint32');
                            fChannels = arrayfun(@(a)(LedPosition(aFileID)),...
                                1:fNumChannels,'UniformOutput',false);
                            this.LedGroups(fArray).Mappings = [fChannels{:}];

                            fArray = fArray +1;
                            fPos = int64(ftell(aFileID));
                        end

                        if fExpected ~= uint16(length(this.LedGroups))
                            error('Encountered an error while loading StimulationLeds: Expected %i groups, got %i',...
                                fExpected, ...
                                length(this.LedGroups));
                        end

                    otherwise
                        this.LedGroups = cell(0);
                        warning('Stimulation LEDs version not supported');
                end
            else
                error('Encountered an error while loading StimulationLeds %s', aRawTag.TagGuid);
            end

            if ftell(aFileID) >  (fTagStart + aRawTag.EntryRecord.Length)
                warning('File may be corrupt');
            end

        end
    end

end

