%{
    Copyright (c) 2024 Axion BioSystems, Inc.
    Contact: support@axion-biosystems.com
    All Rights Reserved
%}
classdef ChannelMapping
    %CHANNELMAPPING represents the mapping of an electrode position to an
    %Amplifier (Artichoke) channel by way of the plate it was recorded
    %with.
    %
    %     WellRow:          Numeric representation of the well row (e.g. A -> 1)
    %
    %     WellColumn:       Well column number of this electrode
    %
    %     ElectrodeColumn:  Column in the well of the electrode
    %
    %     ElectrodeRow:     Row in the well of the electrode
    %
    %     ChannelAchk:      Specific amplifer chip (Artichoke) to which the
    %                       electrode was connected
    %
    %     ChannelIndex:     Specific channel number of connected amplifier
    %                       to which the electrode was connected
    %
    %     AuxData:          Additional data for programmatic usage

    properties (GetAccess = private, Constant = true)
        nullByte = typecast(int8(-1), 'uint8');
        nullWord = typecast(int16(-1), 'uint16');
    end

    properties (GetAccess = public, SetAccess = private)
        WellRow
        WellColumn
        ElectrodeColumn
        ElectrodeRow
        ChannelAchk
        ChannelIndex
        AuxData
    end

    methods(Access = public)

        function this = ChannelMapping( varargin )

            fNArgIn = length(varargin);

            if(fNArgIn == 0)
                % Create a nonsense (Null) Channel Mapping
                this.WellRow         = ChannelMapping.nullByte;
                this.WellColumn      = ChannelMapping.nullByte;
                this.ElectrodeColumn = ChannelMapping.nullByte;
                this.ElectrodeRow    = ChannelMapping.nullByte;
                this.ChannelAchk     = ChannelMapping.nullByte;
                this.ChannelIndex    = ChannelMapping.nullByte;
                this.AuxData         = ChannelMapping.nullWord;

            elseif(fNArgIn == 1)
                % Assume Argument is a file ID from fOpen and that is
                % seeked to the correct spot, read in arguments from this
                % file

                aFileID = varargin{1};

                this.WellColumn      = fread(aFileID, 1, 'uint8=>uint8');
                this.WellRow         = fread(aFileID, 1, 'uint8=>uint8');
                this.ElectrodeColumn = fread(aFileID, 1, 'uint8=>uint8');
                this.ElectrodeRow    = fread(aFileID, 1, 'uint8=>uint8');
                this.ChannelAchk     = fread(aFileID, 1, 'uint8=>uint8');
                this.ChannelIndex    = fread(aFileID, 1, 'uint8=>uint8');
                this.AuxData         = fread(aFileID, 1, 'uint16=>uint16');

            elseif (fNArgIn == 6)
                % Construct a new Channel Mapping from Scratch
                % Argument order is(WellRow, WellColumn, ElectrodeColumn,
                % ElectrodeRow, ChannelAchk, ChannelIndex)

                this.WellRow         = uint8(varargin{1});
                this.WellColumn      = uint8(varargin{2});
                this.ElectrodeColumn = uint8(varargin{3});
                this.ElectrodeRow    = uint8(varargin{4});
                this.ChannelAchk     = uint8(varargin{5});
                this.ChannelIndex    = uint8(varargin{6});
                this.AuxData         = ChannelMapping.nullWord;

            elseif (fNArgIn == 7)
                % Construct a new Channel Mapping from Scratch
                % Argument order is(WellRow, WellColumn, ElectrodeColumn,
                % ElectrodeRow, ChannelAchk, ChannelIndex, AuxData)

                this.WellRow         = uint8(varargin{1});
                this.WellColumn      = uint8(varargin{2});
                this.ElectrodeColumn = uint8(varargin{3});
                this.ElectrodeRow    = uint8(varargin{4});
                this.ChannelAchk     = uint8(varargin{5});
                this.ChannelIndex    = uint8(varargin{6});
                this.AuxData         = uint16(varargin{7});
            else
                error('Argument Error')
            end
        end

        function retval = eq(this, aObj)
            if(~isa(aObj, 'ChannelMapping') ...
               || ~isa(this, 'ChannelMapping') )
                retval = 0;
                return;
            end
            retval = ...
                this.WellRow ==  aObj.WellRow ...
                && this.WellColumn ==  aObj.WellColumn ...
                && this.ElectrodeColumn ==  aObj.ElectrodeColumn ...
                && this.ElectrodeRow ==  aObj.ElectrodeRow ...
                && this.ChannelAchk ==  aObj.ChannelAchk ...
                && this.ChannelIndex ==  aObj.ChannelIndex;

        end
    end
end

