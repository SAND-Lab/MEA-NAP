%{
    Copyright (c) 2024 Axion BioSystems, Inc.
    Contact: support@axion-biosystems.com
    All Rights Reserved
%}
classdef ChannelArray < Entry
    %CHANNELARRAY Class that represents a list of loaded Channels
    % in a BlockVectorDataSet
    %
    %   PlateType:  Numeric ID of the loaded plate that thes channels are
    %               associated with.
    %
    %   Channels:   Vector of Channelmapping objects in the order that they
    %               are included in continuous file.

    properties (GetAccess = private, SetAccess = private)
        basicChannelArray
    end

    properties(GetAccess = public, SetAccess = private)
        PlateType
        Channels
    end

    methods
        function value = get.PlateType(this)
            value = this.basicChannelArray.PlateType;
        end

        function value = get.Channels(this)
            value = this.basicChannelArray.Channels;
        end
    end

    methods(Static, Access = private)
        function varagout = HandleVarargin(varargin)
            if(nargin == 0)
                varagout = {};
            elseif(nargin == 2)
                varagout{1} = varargin{1};
                varagout{2} = int64(ftell( varargin{2}));
            else
                error('Argument Error')
            end
        end
    end

    methods (Access = public)
        function this = ChannelArray(varargin)
            entryConstructorArgs = ChannelArray.HandleVarargin(...
                varargin{:});
            this = this@Entry(entryConstructorArgs{:});

            if(nargin == 0)
                this.basicChannelArray = BasicChannelArray();
            elseif(nargin == 2)
                aFileID = varargin{2};

                this.basicChannelArray = BasicChannelArray(aFileID);

                if(ftell(aFileID) ~= (this.Start + this.EntryRecord.Length))
                    error('Unexpected Channel array length')
                end
            else
                error('Argument Error')
            end
        end

        function index = LookupElectrode(this, ...
                aWellColumn, aWellRow,...
                aElectrodeColumn, aElectrodeRow)
            %LookupElectrode: Quickly finds the index Channels of a given
            %                 electrode position

            index = this.basicChannelArray.LookupElectrode(aWellColumn,...
                aWellRow, aElectrodeColumn, aElectrodeRow);
        end

        function index = LookupChannel(this, ...
                aChannelAchk, aChannelIndex)
            %LookupChannel:   Quickly finds the index Channels of a given
            %                 Amplifier (Artichoke) channel

            index = this.basicChannelArray.LookupChannel(aChannelAchk,...
                aChannelIndex);
        end
        
        function mapping = LookupChannelMapping(this, ...
                aChannelAchk, aChannelIndex)

            mapping = this.basicChannelArray.LookupChannelMapping(...
                aChannelAchk, aChannelIndex);
        end

        function index = LookupChannelID(this, aChannelId)

            index = this.basicChannelArray.LookupChannelID(aChannelId);
        end

        function fChannelArray = GetNewForChannels(this, aChannels)

            fChannelArray = ChannelArray();
            fChannelArray.basicChannelArray = BasicChannelArray(this.basicChannelArray.PlateType, aChannels);
        end
    end

    methods (Static)
        function fChannelArray = version_0_1_channel_array()

            % Hardware-to-grid channel mapping. This is a constant only for Muse Beta (AxIS v0.1)
            % and file format version 0.1.  For later versions, mapping is loaded from the file itself.
            fChannelMapping          = LegacySupport.P200D30S_CHANNEL_MAPPING;
            fPlateType  = LegacySupport.P200D30S_PLATE_TYPE;

            fChannels = ChannelMapping.empty(0,(length(fChannelMapping)));

            for fiCol = 1:size(fChannelMapping, 1)
                for fiRow = 1:size(fChannelMapping, 2)
                    fCurrentChannelIndex = fChannelMapping(fiRow, fiCol);

                    fNewMapping = ChannelMapping(...
                        1, 1,...
                        fiCol, fiRow,...
                        0, fCurrentChannelIndex);

                    fChannels(fCurrentChannelIndex + 1) = fNewMapping;
                end
            end

            fChannelArray = ChannelArray();
            fChannelArray.basicChannelArray = BasicChannelArray(...
                fPlateType, fChannels);
        end
    end
end
