%{
    Copyright (c) 2024 Axion BioSystems, Inc.
    Contact: support@axion-biosystems.com
    All Rights Reserved
%}
classdef LedPosition
    %CHANNELMAPPING represents the Position and color of an LED on an
    %optical stimulation device.
    %
    %     WellRow:          Numeric representation of the well row (e.g. A -> 1)
    %
    %     WellColumn:       Well column number of this electrode
    %
    %     LedColor:         Color of the LED being used
    properties (GetAccess = private, Constant = true)
        nullByte = typecast(int8(-1), 'uint8');
        nullWord = typecast(int16(-1), 'uint16');
    end

    properties (GetAccess = public, SetAccess = private)
        WellRow
        WellColumn
        LedColor
    end

    methods(Access = public)

        function this = LedPosition( varargin )

            fNArgIn = length(varargin);

            if(fNArgIn == 0)
                % Create a nonsense (Null) Channel Mapping
                this.WellRow         = ChannelMapping.nullByte;
                this.WellColumn      = ChannelMapping.nullByte;
                this.LedColor        = ChannelMapping.nullWord;

            elseif(fNArgIn == 1)
                % Assume Argument is a file ID from fOpen and that is
                % seeked to the correct spot, read in arguments from this
                % file

                aFileID = varargin{1};

                this.WellColumn      = fread(aFileID, 1, 'uint8=>uint8');
                this.WellRow         = fread(aFileID, 1, 'uint8=>uint8');
                this.LedColor        = LedColor(fread(aFileID, 1, 'uint16=>uint16'));

            elseif (fNArgIn == 3)
                % Construct a new Channel Mapping from Scratch
                % Argument order is(WellRow, WellColumn, ElectrodeColumn,
                % ElectrodeRow, ChannelAchk, ChannelIndex)

                this.WellRow         = uint8(varargin{1});
                this.WellColumn      = uint8(varargin{2});
                this.LedColor        = uint16(varargin{3});
            else
                error('Argument Error')
            end
        end

        function retval = eq(this, aObj)
            if(~isa(aObj, 'LedPosition') ...
               || ~isa(this, 'LedPosition') )
                retval = 0;
                return;
            end
            retval = ...
                this.WellRow ==  aObj.WellRow ...
                && this.WellColumn ==  aObj.WellColumn ...
                && this.LedColor ==  aObj.LedColor;

        end
    end
end

