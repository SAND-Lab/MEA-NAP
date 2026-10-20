%{
    Copyright (c) 2024 Axion BioSystems, Inc.
    Contact: support@axion-biosystems.com
    All Rights Reserved
%}
classdef ContractilityWaveform < Waveform
% ContractilityWaveform: Waveform class for contractality data
    methods
        function this = ContractilityWaveform(aChannel, aStart, aData, aSource, aSubsampleFactor)
            this@Waveform(aChannel, aStart, aData, aSource, aSubsampleFactor)
        end

        function [timeData, contractilityData] = GetTimeContractilityVector(this)
            %GetTimeContractilityVector: Returns a vector for time and Contractility
            % for this waveform in a single call in units of Percent (1% = 1)
            
            %Get the Time Vector 
            timeData = this.GetTimeVector();
            
            %Get Base Data
            fData = double([this(:).Data]);
            fSource = [this(:).Source];
            fVoltageScale = [fSource(:).VoltageScale];
            contractilityData = fData * diag(fVoltageScale);
            
            %Subtract the first order polyfit to remove the baseline
            for fI = 1:size(contractilityData, 2)
                poly = polyfit(timeData(:,fI),contractilityData(:,fI),1);
                
                fBaseline = polyval(poly, timeData(:,fI));
                
                %Scale as a percent of baseline 
                contractilityData(:,fI) = (contractilityData(:,fI) - fBaseline) * 100 ./ fBaseline;
            end
        end

        function contractilityData = GetContractilityVector(this)
            % GetContractilityVector: returns a contractility vector for this waveform based
            % on the raw impedance data in units of Percent (1% = 1)
            %
            % If this Method is called on an array of waveforms, the
            % lengths of the waveforms MUST agree
            [~, contractilityData] = GetTimeContractilityVector(this);
        end

        function [timeData, impedanceData] = GetTimeImpedanceVector(this)
            %GetTimeImpedanceVector: Returns a vector for time and impedance
            % for this waveform in a single call
            timeData = this.GetTimeVector();
            impedanceData = this.GetImpedanceVector();
        end

        function impedanceData = GetImpedanceVector(this)
            % GetImpedanceVector: returns a Impedance vector for this waveform based
            % on the raw sample data (Stored as doubles) and the source
            % header's specified voltage scale
            %
            % If this Method is called on an array of waveforms, the
            % lengths of the waveforms MUST agree
            fData = double([this(:).Data]);
            fSource = [this(:).Source];
            fVoltageScale = [fSource(:).VoltageScale];
            impedanceData = fData * diag(fVoltageScale);
        end
    end

end
