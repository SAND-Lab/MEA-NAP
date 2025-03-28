%{
    Copyright (c) 2024 Axion BioSystems, Inc.
    Contact: support@axion-biosystems.com
    All Rights Reserved
%}
classdef BlockVectorSampleType < uint16
    %SampleType Encoding of the type of samples stored by a block vector
    %
    %   Short: Signed 16-bit numbers (little-endian)
    %
    %   Int: Signed 32-bit numbers (little-endian)
    %
    %   Float: 32-bit floating point numbers (IEEE 754)
    %
    %   Double: 64-bit floating point numbers (IEEE 754)
    %

    enumeration
        Short(0)
        Int(1)
        Float(2)
        Double(3)
    end

    methods(Static)
        function [value , success] = TryParse(aInput)
            try
                value = BlockVectorSampleType(aInput);
                success = true;
            catch e

                warning(...
                    'BlockVectorSampleType:TryParse',  ...
                    ['Unsupported BlockVectorSampleType', e]);

                value = aInput;
                success = false;
            end
        end

        function value = GetSizeInBytes(aInput)
            switch(aInput)
                case BlockVectorSampleType.Short
                    value = 2;
                case BlockVectorSampleType.Int
                    value = 4;
                case BlockVectorSampleType.Float
                    value = 4;
                case BlockVectorSampleType.Double
                    value = 8;
                otherwise
                    error('Unknown SampleType enum: %d', aInput);
            end
        end

        function precision = GetFreadPrecision(aInput)
            switch(aInput)
                case BlockVectorSampleType.Short
                    precision = 'int16=>int16';
                case BlockVectorSampleType.Int
                    precision = 'int32=>int32';
                case BlockVectorSampleType.Float
                    precision = 'float32=>float32';
                case BlockVectorSampleType.Double
                    precision = 'float64=>float64';
                otherwise
                    error('Unknown SampleType enum: %d', aInput);
            end
        end
    end

end

