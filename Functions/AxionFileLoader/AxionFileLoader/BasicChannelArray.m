%{
    Copyright (c) 2024 Axion BioSystems, Inc.
    Contact: support@axion-biosystems.com
    All Rights Reserved
%}
classdef BasicChannelArray < handle
    %BASICCHANNELARRAY Class used to hold plate type and channel mapping
    % lists within entries.
    %   PlateType:  Numeric ID of the loaded plate that thes channels are
    %               associated with.
    %
    %   Channels:   Vector of Channelmapping objects in the order that they
    %               are included in continuous file.

    properties (GetAccess = private, SetAccess = private)
        electrodeHashMap
        channelLut
    end

    properties(GetAccess = public, SetAccess = private)
        PlateType
        Channels
    end

    methods (Access = public)
        function this = BasicChannelArray(varargin)
            %BasicChannelArray: Constructs a new instance
            % of the BasicChannelArray class.
            %
            % BasicChannelArray()                       Constructs an new
            % instance with an empty plate type and channels properties.
            %
            % BasicChannelArray(aFileId)                Constructs an new
            % instance from an opened AxionFile with the specified file ID.
            %
            % BasicChannelArray(aPlateType, aChannels)  Constructs an new
            % instance with the specified plate type and channels.
            %

            this.PlateType = [];
            this.Channels = [];
            this.electrodeHashMap = [];
            this.channelLut = [];

            if (nargin == 2)
                this.PlateType = varargin{1};
                this.Channels = varargin{2};
            elseif (nargin == 1)
                fFileId = varargin{1};

                this.PlateType = fread(fFileId, 1, 'uint32=>uint32');

                fNumChannels = fread(fFileId, 1, 'uint32=>uint32');

                this.Channels = ChannelMapping.empty(0, fNumChannels);

                fIndices = int32(1:fNumChannels);
                for i = fIndices
                    this.Channels(i) = ChannelMapping(fFileId);
                end
            end

            this.RebuildHashMaps();
        end

        function index = LookupElectrode(this, ...
            aWellColumn, aWellRow,...
            aElectrodeColumn, aElectrodeRow)
            %LookupElectrode: Quickly finds the index Channels of a given
            % electrode position

            fHash = BasicChannelArray.HashElectrode(...
                aWellColumn, aWellRow, aElectrodeColumn, aElectrodeRow);
            index = this.electrodeHashMap(fHash);
        end

        function index = LookupChannel(this, ...
            aChannelAchk, aChannelIndex)
            %LookupChannel:   Quickly finds the index of the ChannelMapping
            % with a given amplifier (Artichoke) channel

            fHash = bitshift(uint32(aChannelAchk), 8);
            fHash = bitor(uint32(aChannelIndex), fHash);

            fHash = fHash + 1; % 1-based indexing for MATLAB

            index = this.channelLut(fHash);

        end
        
        function mapping = LookupChannelMapping(this, ...
            aChannelAchk, aChannelIndex)
            %LookupChannelMapping:  Finds the ChannelMapping
            % with a given amplifier (Artichoke) channel

            mapping = this.Channels(this.LookupChannel(aChannelAchk,...
                aChannelIndex));
        end

        function index = LookupChannelID(this, ...
            aChannelId)
            %LookupChannelID:   Find the index of the ChannelMapping
            % by a given ChannelID

            index = this.LookupChannel(...
                aChannelId.Artichoke,...
                aChannelId.Channel);
        end
    end

    methods(Access = private)
        function this = RebuildHashMaps(this)

            this.electrodeHashMap = containers.Map('KeyType', 'int32',...
                'ValueType', 'int32');
            this.channelLut = zeros(length(this.Channels),1);

            fIndices = 1 : length(this.Channels);

            for fIndex = fIndices
                fElectrodeHash = BasicChannelArray.HashElectrode(...
                    this.Channels(fIndex).WellColumn,...
                    this.Channels(fIndex).WellRow,...
                    this.Channels(fIndex).ElectrodeColumn,...
                    this.Channels(fIndex).ElectrodeRow);

                fChannelHash = BasicChannelArray.HashChannel(...
                    this.Channels(fIndex).ChannelAchk,...
                    this.Channels(fIndex).ChannelIndex);

                if (this.electrodeHashMap.isKey(fElectrodeHash))
                    error('Key already added in electrode hash map')
                end

                this.electrodeHashMap(fElectrodeHash) = fIndex;
                this.channelLut(fChannelHash + 1)     = fIndex;
            end
        end
    end

    methods(Access = private, Static = true)
        function hash = HashElectrode(...
            aWellColumn, aWellRow,...
            aElectrodeColumn, aElectrodeRow)

            hash = bitshift(uint32(aWellColumn), 24);
            hash = bitor(bitshift(uint32(aWellRow), 16), hash);
            hash = bitor(bitshift(uint32(aElectrodeColumn), 8), hash);
            hash = bitor(uint32(aElectrodeRow), hash);

            hash = uint32(hash);
        end

        function hash = HashChannel(...
            aChannelAchk, aChannelIndex)

            hash = bitshift(uint32(aChannelAchk), 8);
            hash = bitor(uint32(aChannelIndex), hash);

            hash = uint32(hash);
        end
    end
end
