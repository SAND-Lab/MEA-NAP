%{
    Copyright (c) 2024 Axion BioSystems, Inc.
    Contact: support@axion-biosystems.com
    All Rights Reserved
%}
classdef StimulationChannels < Tag
    %STIMULATIONCHANNELS File data that enumerates channels used in a
    %stimulation
    properties (GetAccess = private, Constant = true)
        CurrentVersion = 0;
        MinArraySize = int64(20);
    end

    properties (SetAccess = private)
        ChannelGroups
    end

    methods
        function this = StimulationChannels(aFileID, aRawTag)
            this = this@Tag(aRawTag.TagGuid);

            %Move to the correct location in the file
            fStart = int64(aRawTag.Start + TagEntry.BaseSize);
            aSeekReult = fseek(aFileID, fStart, 'bof');

            fTagStart = int64(aRawTag.Start);
            fTagEnd = int64(fTagStart + aRawTag.EntryRecord.Length);

            if aSeekReult == 0
                fVersion =  fread(aFileID, 1, 'uint16=>uint16');
                switch fVersion
                    case StimulationChannels.CurrentVersion

                        fread(aFileID, 1, 'uint16=>uint16'); %Reserved short
                        this.ChannelGroups = struct([]);
                        fArray = 1;
                        fPos = int64(ftell(aFileID));
                        while (fTagEnd - fPos) >= StimulationChannels.MinArraySize
                            fId = fread(aFileID, 1, 'uint32=>uint32');
                            this.ChannelGroups(fArray).ID = fId;

                            fPlateType   = fread(aFileID, 1, 'uint32=>uint32');
                            this.ChannelGroups(fArray).PlateType = fPlateType;

                            fNumChannels = fread(aFileID, 1, 'uint32=>uint32');
                            fChannels = arrayfun(@(a)(ChannelMapping(aFileID)),...
                                1:fNumChannels,'UniformOutput',false);
                            this.ChannelGroups(fArray).Mappings = [fChannels{:}];

                            fArray = fArray +1;
                            fPos = int64(ftell(aFileID));
                        end

                    otherwise
                        this.ChannelGroups = cell(0);
                        warning('Stimulation channels version not suported');
                end
            else
                error('Encountered an error while loading StimulationChannels %s', aRawTag.TagGuid);
            end

            if ftell(aFileID) >  (fTagStart + aRawTag.EntryRecord.Length)
                warning('File may be corrupt');
            end

        end
    end

end

