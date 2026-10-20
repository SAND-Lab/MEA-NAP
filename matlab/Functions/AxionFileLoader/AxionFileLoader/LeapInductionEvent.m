%{
    Copyright (c) 2024 Axion BioSystems, Inc.
    Contact: support@axion-biosystems.com
    All Rights Reserved
%}
classdef LeapInductionEvent < Tag & matlab.mixin.CustomDisplay
    %LEAPINDUCTIONEVENT Tag that describes a LEAP induction event

    properties(GetAccess = private, Constant = true)
        CurrentVersion = 0;
    end

    properties(SetAccess = private)
        %The time the Leap induction began
        LeapInductionStartTime;
        %The total duration of the LEAP induction period (In seconds)
        LeapInductionDuration;
        %PlateType of the LEAP induced plated
        PlateType
        %The Channels that were induced for LEAP
        LeapedChannels
    end

    properties(GetAccess = private, SetAccess = private)
        %The time the Leap induction began
        mCreationDate;
    end

    methods
        function this = LeapInductionEvent(aFileID, aRawTag)
            this = this@Tag(aRawTag.TagGuid);
            this.mCreationDate = aRawTag.CreationDate;
            fStart = aRawTag.Start + TagEntry.BaseSize;
            fSeekResult = fseek(aFileID, fStart, 'bof');

            if(fSeekResult == 0)
                fVersion = fread(aFileID, 2, 'uint16=>uint16');
                fVersion = fVersion(1); %Second shork is ignored
                if fVersion ~= LeapInductionEvent.CurrentVersion
                   error('Unknown LEAP induction event version')
                end
                this.LeapInductionStartTime = DateTime(aFileID);

                fTicks = fread(aFileID, 1, 'uint64=>uint64');
                this.LeapInductionDuration = double(fTicks) * 1e-7;

                this.PlateType = fread(aFileID, 1, 'uint32=>uint32');
                fNumChannels = fread(aFileID, 1, 'uint32=>uint32');
                this.LeapedChannels = arrayfun(@(a)(ChannelMapping(aFileID)),...
                    1:fNumChannels,'UniformOutput',false);
            else
                error('Encountered an error while loading LeapInductionEvent %s', aRawTag.TagGuid);
            end

            fStart = aRawTag.Start + TagEntry.BaseSize;
            if ftell(aFileID) >  (fStart + aRawTag.EntryRecord.Length)
                warning('File may be corrupt');
            end
        end

        function date = CreationDate(this)
            date = this.mCreationDate;
        end
    end
    
    methods (Access = protected)
        function propgrp = getPropertyGroups(obj)
            propgrp = getPropertyGroups@matlab.mixin.CustomDisplay(obj);
            if isscalar(obj)
                propList = propgrp.PropertyList;
                propList.LeapInductionStartTime = obj.LeapInductionStartTime.ToDateTimeString();
                propgrp = matlab.mixin.util.PropertyGroup(propList);
            end
        end
    end
end

