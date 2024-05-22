%{
    Copyright (c) 2024 Axion BioSystems, Inc.
    Contact: support@axion-biosystems.com
    All Rights Reserved
%}
classdef BlockVectorDataType < uint16
    %BLOCKVECTORDATATYPE Enumeration of known types of block vector data.
    %
    %   Raw_v1:     Continuous data from an Axion Muse or Maestro device.
    %
    %   Spike_v1:   Binary Spike Data recorded by a Spike detector in Axis.
    %
    %   NamedContinuousData: Continous data where every track of data has
    %   an associated channel and name
    %

    enumeration
        Raw_v1(0)
        Spike_v1(1)
        NamedContinuousData(2)
    end

    methods(Static)
        function [value , success] = TryParse(aInput)
            try
                value = BlockVectorDataType(aInput);
                success = true;
            catch e

                warning(...
                    'BlockVectorDataType:TryParse',  ...
                    ['Unsupported BlockVectorDataType', e]);

                value = aInput;
                success = false;
            end
        end
    end

end

