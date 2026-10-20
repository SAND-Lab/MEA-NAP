%{
    Copyright (c) 2024 Axion BioSystems, Inc.
    Contact: support@axion-biosystems.com
    All Rights Reserved
%}
classdef Waveform < matlab.mixin.Heterogeneous
    %WAVEFORM Container for single dimensional recorded sample data
    %
    %   Channel:    Source Location of the waveform
    %
    %   Start:      Time(In Seconds) of Recording Start
    %
    %   Data:       Sample data
    %
    %   Source:     BlockVectorDataSet that contains this Waveform

    properties(GetAccess = public, SetAccess = protected)
        Channel;
        Start;
        Data;
        Source;
    end

    properties(GetAccess = protected, SetAccess = protected)
        SubsampleFactor;
    end

    methods

        function this = Waveform(aChannel, aStart, aData, aSource, aSubsampleFactor)
            this@matlab.mixin.Heterogeneous();

            if(nargin == 0)
                return;
            end

            if(~isa(aChannel,'ChannelMapping'))
                error(['Waveform: Unexpected Argument for aChannel: ' aChannel]);
            end

            if(~isa(aSource,'DataSet'))
                error(['Waveform: Unexpected Argument for aSource: ' aSource]);
            end

            this.Channel = aChannel;
            this.Start = aStart;
            this.Data = aData;
            this.Source = aSource;
            this.SubsampleFactor = aSubsampleFactor;
        end

        function timeData = GetTimeVector(this)
            % GetTimeVector: returns a time vector for this waveform based
            % on the Start time, Length of the data, and the Sampling
            % Frequency of the source header
            %
            % If this Method is called on an array of waveforms, the
            % lengths of the waveforms MUST agree
            fSource = [this(:).Source];

            fSamplingPeriod = 1./[fSource(:).SamplingFrequency];
            timeData = repmat((0 : (length(this(1).Data) - 1))', 1,length(this));
            timeData = timeData .* this(1).SubsampleFactor;
            timeData = timeData * diag(fSamplingPeriod);

            fStart = ones(size(timeData));
            fStart = fStart * diag([this(:).Start]);

            timeData = timeData + fStart;
        end

    end

end

