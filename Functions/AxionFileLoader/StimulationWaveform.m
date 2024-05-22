%{
    Copyright (c) 2024 Axion BioSystems, Inc.
    Contact: support@axion-biosystems.com
    All Rights Reserved
%}
classdef StimulationWaveform < Tag
    %STIMULATIONWAVEFORM Storage element for StimulationEventData, before it
    %is linked to StimulationEvents
    properties(GetAccess = private, Constant = true)
        CurrentVersion = 0;
    end

    properties(SetAccess = private)
        TagBlocks = StimulationEventData.empty(0);
        MicroOps;
    end

    methods
        function this = StimulationWaveform(aFileID, aRawTag)
            this = this@Tag(aRawTag.TagGuid);

            %Move to the correct location in the file
            fStart = aRawTag.Start + TagEntry.BaseSize;
            fSeekResult = fseek(aFileID, fStart, 'bof');

            if(fSeekResult == 0)
                fVersion =  fread(aFileID, 1, 'uint16=>uint16');
                switch fVersion
                    case StimulationWaveform.CurrentVersion
                        fNumBlocks = fread(aFileID, 1, 'uint16=>uint16'); %Reserved short
                        for fBlock = 1:fNumBlocks

                            fId = fread(aFileID, 1, 'uint16=>uint16');
                            fread(aFileID, 1, 'uint16=>uint16'); %Type: Unused for now
                            fStimDuration = fread(aFileID, 1, 'double=>double');
                            fArtElimDuration = fread(aFileID, 1, 'double=>double');
                            fChannelArrayIdList = fread(aFileID, 2, 'uint16=>uint16');
                            % Remove all channel array ID's that are 0 -
                            % they are placeholders.
                            fChannelArrayIdList = fChannelArrayIdList(fChannelArrayIdList ~= 0);

                            fDescription = freadstring(aFileID);
                            this.TagBlocks(fBlock) = StimulationEventData(...
                                fId, fStimDuration, fArtElimDuration,...
                                fChannelArrayIdList, fDescription);
                        end
                        this.MicroOps = freadstring(aFileID);
                    otherwise
                        this.TagBlocks = cell(0);
                        this.MicroOps = '';
                        warning('StimulationWaveform version not supported');
                end
            else
                error('Encountered an error while loading StimulationWaveform %s', aRawTag.TagGuid);
            end

            if ftell(aFileID) >  (fStart + aRawTag.EntryRecord.Length)
                warning('File may be corrupt');
            end

        end
    end

end

