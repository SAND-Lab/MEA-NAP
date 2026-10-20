%{
    Copyright (c) 2024 Axion BioSystems, Inc.
    Contact: support@axion-biosystems.com
    All Rights Reserved
%}
classdef ViabilityImpedanceEvent < Tag & matlab.mixin.CustomDisplay
    %VIABILITYIMPEDANCEEVENT Tag for acquiring viability data
    
    properties(GetAccess = private, Constant = true)
        CurrentVersion = 0;
    end
    
    properties(SetAccess = private)
        %The timestamp when the viability impedance measurement finished
        MeasurementDateTime
        % The plate map type and the collection of measured channels
        ChannelArray
        %The collection of measured frequencies (Hz)
        Frequencies
        %The collection of measured impedance values where rows are channels and columns are frequencies
        ImpedanceValues
    end
    
    properties(GetAccess = private, SetAccess = private)
        %The date/time that this tag revision was created
        mCreationDate;
    end
    
    methods
        function this = ViabilityImpedanceEvent(aFileID, aRawTag)
            this = this@Tag(aRawTag.TagGuid);
            this.mCreationDate = aRawTag.CreationDate;
            fStart = aRawTag.Start + TagEntry.BaseSize;
            fSeekResult = fseek(aFileID, fStart, 'bof');

            if(fSeekResult == 0)
                fVersion = fread(aFileID, 2, 'uint16=>uint16');
                fVersion = fVersion(1); %Second shork is ignored
                if fVersion ~= ViabilityImpedanceEvent.CurrentVersion
                   error('Unknown Viability Impedance Event version')
                end
                this.MeasurementDateTime = DateTime(aFileID);

                fFrequenciesCount = fread(aFileID, 1, 'uint32=>uint32');
                this.Frequencies = zeros(fFrequenciesCount, 1);
                for fiFrequency = 1:fFrequenciesCount
                   this.Frequencies(fiFrequency) = fread(aFileID, 1, 'double=>double');
                end

                this.ChannelArray = BasicChannelArray(aFileID);

                fNumChannels = length(this.ChannelArray.Channels);

                this.ImpedanceValues = zeros(fNumChannels, fFrequenciesCount);
                for fiChannel = 1:fNumChannels
                    for fiFrequency = 1:fFrequenciesCount
                        fReal = fread(aFileID, 1, 'double=>double');
                        fImaginary = fread(aFileID, 1, 'double=>double');
                        this.ImpedanceValues(fiChannel, fiFrequency) = complex(fReal, fImaginary);
                    end
                end
            else
                error('Encountered an error while loading ViabilityImpedanceEvent %s', aRawTag.TagGuid);
            end

            fStart = aRawTag.Start + TagEntry.BaseSize;
            if ftell(aFileID) >  (fStart + aRawTag.EntryRecord.Length)
                error('File may be corrupt');
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
                propList.MeasurementDateTime = obj.MeasurementDateTime.ToDateTimeString();
                propgrp = matlab.mixin.util.PropertyGroup(propList);
            end
        end
    end
end
