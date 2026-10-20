%{
    Copyright (c) 2024 Axion BioSystems, Inc.
    Contact: support@axion-biosystems.com
    All Rights Reserved
%}
classdef VoltageWaveform < Waveform

    methods
        function this = VoltageWaveform(aChannel, aStart, aData, aSource, aSubsampleFactor)
            this@Waveform(aChannel, aStart, aData, aSource, aSubsampleFactor)
        end

        function [timeData, voltageData] = GetTimeVoltageVector(this)
            %GetTimeVoltageVector: Returns a vector for time and voltage
            % for this waveform in a single call
            timeData = this.GetTimeVector();
            voltageData = this.GetVoltageVector();
        end

        function voltageData = GetVoltageVector(this)
            % GetVoltageVector: returns a voltage vector for this waveform based
            % on the uncasted sample data (Stored as int16) and the source
            % header's specified voltage scale
            %
            % If this Method is called on an array of waveforms, the
            % lengths of the waveforms MUST agree
            fData = double([this(:).Data]);
            fSource = [this(:).Source];
            fVoltageScale = [fSource(:).VoltageScale];
            voltageData = fData * diag(fVoltageScale);
        end
    end

end