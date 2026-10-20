%{
    Copyright (c) 2024 Axion BioSystems, Inc.
    Contact: support@axion-biosystems.com
    All Rights Reserved
%}
classdef EventTag < Tag
    %EVENTTAG Base class for tagged events in the file.Indicates
    %time stamps for particular events

    properties(SetAccess = private)
        % SamplingFrequency: Sampling frequency active during the event
        % that created this tag
        SamplingFrequency;
        % EventTimeSample: The starting sample for this event
        EventTimeSample;
        % EventTimeSample: Time of the event in seconds, as converted from
        % samples
        EventTime;
        % EventDurationSamples: The number of samples following the
        % EventTimeSample that are relevant to this tag or affected by this
        % event
        EventDurationSamples;
    end

    methods (Access = protected)
        function this = EventTag(aFileID, aRawTag)
            this = this@Tag(aRawTag.TagGuid);

            fStart = aRawTag.Start + TagEntry.BaseSize;
            fSeekResult = fseek(aFileID, fStart, 'bof');
            if(fSeekResult == 0)
                this.SamplingFrequency     = fread(aFileID, 1, 'double=>double');
                this.EventTimeSample       = fread(aFileID, 1, 'int64=>int64');
                this.EventDurationSamples  = fread(aFileID, 1, 'int64=>int64');

                this.EventTime =  double(this.EventTimeSample) /  this.SamplingFrequency;
            else
                error('Encountered an error while loading EventTag %s', aRawTag.TagGuid);
            end
        end

    end

end

