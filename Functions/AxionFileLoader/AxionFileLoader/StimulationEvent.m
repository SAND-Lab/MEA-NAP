%{
    Copyright (c) 2024 Axion BioSystems, Inc.
    Contact: support@axion-biosystems.com
    All Rights Reserved
%}
classdef StimulationEvent < EventTag
    %STIMULATIONEVENT Event data that corresponds to a tagged stimulation
    %that occurred in the file
    properties (GetAccess = public, Constant = true)
        CurrentVersion = 0;
    end

    properties (GetAccess = private, SetAccess = private)
        SequenceNumber;
        WaveformTag;
        ChannelsTag;
    end

    properties (SetAccess = private)
        PlateType;
        Electrodes;
        Leds;
        EventData;
    end

    methods
        function this = StimulationEvent(aFileID, aRawTag)
            this = this@EventTag(aFileID, aRawTag);
            %Assume EventTag leaves us at the correct location in the file

            fVersion =  fread(aFileID, 1, 'uint16=>uint16');
            switch fVersion
                case StimulationEvent.CurrentVersion
                    fread(aFileID, 1, 'uint16=>uint16');%Reserved

                    this.WaveformTag = parseGuid(fread(aFileID, 16, 'uint8=>uint8'));
                    this.ChannelsTag = parseGuid(fread(aFileID, 16, 'uint8=>uint8'));

                    this.EventData =  fread(aFileID, 1, 'uint16=>uint16');
                    this.SequenceNumber =  fread(aFileID, 1, 'uint16=>uint16');
                otherwise
                    this.WaveformTag = '';
                    this.ChannelsTag = '';
                    this.EventData = uint16(hex2dec('FFFF'));
                    this.SequenceNumber = uint16(hex2dec('FFFF'));
                    warning('Stimulation Event version not supported');
            end

            fStart = aRawTag.Start + TagEntry.BaseSize;
            if ftell(aFileID) >  (fStart + aRawTag.EntryRecord.Length)
                warning('File may be corrupt');
            end
        end
        
        function isValid = HasValidTags(this)
            if isempty(this)
                isValid = [];
            elseif isvector(this)
                isValid = arrayfun( @(event)...
                    ~strcmp(event.WaveformTag, '00000000-0000-0000-0000-000000000000') && ...
                    ~strcmp(event.ChannelsTag, '00000000-0000-0000-0000-000000000000'), ...
                    this);
            else
                isValid = ...
                    ~strcmp(this.WaveformTag, '00000000-0000-0000-0000-000000000000') && ...
                    ~strcmp(this.ChannelsTag, '00000000-0000-0000-0000-000000000000');
            end
        end
                

        function Link(this, aTagMap)
            if ~isa(aTagMap,'containers.Map')
                error('Link should be called with a map');
            end
            if(aTagMap.isKey(this.WaveformTag))
                this.WaveformTag = aTagMap(this.WaveformTag);
            else
                warning('Missing Stimulation Waveform Tag: %s', this.WaveformTag);
            end
            if(aTagMap.isKey(this.ChannelsTag))
                this.ChannelsTag = aTagMap(this.ChannelsTag);
            else
                warning('Missing Stimulation Channels Tag: %s', this.WaveformTag);
            end

            if isa(this.WaveformTag,'StimulationWaveform') && isa(this.ChannelsTag,'StimulationChannels')
                fEventDatas = this.WaveformTag.TagBlocks;
                fChannels = this.ChannelsTag.ChannelGroups;
                this.EventData = fEventDatas(find(arrayfun(@(a)(a.ID) == this.EventData, fEventDatas),1));

                this.Electrodes = arrayfun(...
                    @(aChanId)(fChannels(find(arrayfun(@(a)(a.ID) == aChanId, fChannels),1))),...
                    this.EventData.ChannelArrayIdList);

                this.PlateType = unique(arrayfun(@(a)(a.PlateType), this.Electrodes));
                this.Electrodes = arrayfun(@(a)(a.Mappings), this.Electrodes, 'UniformOutput', false);

                if length(this.Electrodes) == 1
                    this.Electrodes = this.Electrodes{1};
                end
            elseif isa(this.ChannelsTag,'StimulationLeds')
                fEventDatas = this.WaveformTag.TagBlocks;
                fChannels = this.ChannelsTag.LedGroups;
                this.EventData = fEventDatas(find(arrayfun(@(a)(a.ID) == this.EventData, fEventDatas),1));

                if isempty(this.EventData)
                     this.Leds = this.ChannelsTag.LedGroups;
                     this.EventData = StimulationEventData( 0, 0, 0, uint16(zeros(0,1)), '');
                else
                    this.Leds = arrayfun(...
                        @(aChanId)(fChannels(find(arrayfun(@(a)(a.ID) == aChanId, fChannels),1))),...
                        this.EventData.ChannelArrayIdList);
                    this.Leds = arrayfun(@(a)(a.Mappings), this.Leds, 'UniformOutput', false);
                end

                if length(this.Leds) == 1 && iscell(this.Leds)
                    this.Leds = this.Leds{1};
                end
            end

        end
    end
end

