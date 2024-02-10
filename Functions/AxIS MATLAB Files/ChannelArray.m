classdef ChannelArray < Entry
    %CHANNELARRAY Class that represents a list of loaded Channels in a BlockVectorDataSet
    %
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
            entryConstructorArgs = ChannelArray.HandleVarargin(varargin{:}); ...
            this = this@Entry(entryConstructorArgs{:});

            if(nargin == 0)
                this.PlateType = [];
                this.Channels = [];
                this.electrodeHashMap = [];
                this.channelLut = [];
            elseif(nargin == 2)
                aFileID = varargin{2};
                this.PlateType   = fread(aFileID, 1, 'uint32=>uint32');
                fNnumChannels = fread(aFileID, 1, 'uint32=>uint32');

                this.Channels = ChannelMapping.empty(0, fNnumChannels);

                fIndices = int32(1:fNnumChannels);
                for i = fIndices
                    this.Channels(i) = ChannelMapping(aFileID);
                end


                this.RebuildHashMaps();


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

            index = this.electrodeHashMap(ChannelMapping.HashElectrode(...
                aWellColumn, aWellRow, aElectrodeColumn, aElectrodeRow));

        end

        function index = LookupChannel(this, ...
                aChannelAchk, aChannelIndex)
            %LookupChannel:   Quickly finds the index Channels of a given
            %                 Amplifier (Artichoke) channel
            hash = bitshift(uint32(aChannelAchk), 8);
            hash = bitor(uint32(aChannelIndex), hash);

            hash = hash + 1; % 1-based indexing for MATLAB

            index = this.channelLut(hash);

        end
        
        function mapping = LookupChannelMapping(this, ...
                aChannelAchk, aChannelIndex)
            mapping = this.Channels(this.LookupChannel(aChannelAchk, aChannelIndex));
        end

        function index = LookupChannelID(this, ...
                aChannelId)

            index = this.LookupChannel(...
                aChannelId.Artichoke,...
                aChannelId.Channel);
        end

        function fChannelArray = GetNewForChannels(this, ...
            aChannels)
            fChannelArray = ChannelArray();
            fChannelArray.PlateType = this.PlateType;
            fChannelArray.Channels = aChannels;
            fChannelArray.RebuildHashMaps();
        end


    end

    methods(Access = private)

        function RebuildHashMaps(this)

            this.electrodeHashMap = containers.Map('KeyType', 'int32', 'ValueType', 'int32');
            this.channelLut = zeros(length(this.Channels),1);

            fIndices = 1 : length(this.Channels);

            for fIndex = fIndices

                fElectrodeHash = ChannelArray.HashElectrode( ...
                    this.Channels(fIndex).WellColumn,...
                    this.Channels(fIndex).WellRow,...
                    this.Channels(fIndex).ElectrodeColumn,...
                    this.Channels(fIndex).ElectrodeRow);

                fChannelHash = ChannelArray.HashChannel( ...
                    this.Channels(fIndex).ChannelAchk,...
                    this.Channels(fIndex).ChannelIndex);

                if (this.electrodeHashMap.isKey(fElectrodeHash))
                    error('Key already added')
                end

                this.electrodeHashMap(fElectrodeHash) =  fIndex;
                this.channelLut(fChannelHash+1) = fIndex;

            end
        end
    end

    methods(Access = private, Static = true)


        function hash = HashElectrode( ...
                aWellColumn, aWellRow,...
                aElectrodeColumn, aElectrodeRow)

            hash = bitshift(uint32(aWellColumn), 24);
            hash = bitor(bitshift(uint32(aWellRow), 16), hash);
            hash = bitor(bitshift(uint32(aElectrodeColumn), 8), hash);
            hash = bitor(uint32(aElectrodeRow), hash);

            hash = uint32(hash);

        end

        function hash = HashChannel( ...
                aChannelAchk, aChannelIndex)

            hash = bitshift(uint32(aChannelAchk), 8);
            hash = bitor(uint32(aChannelIndex), hash);

            hash = uint32(hash);

        end

    end

    methods (Static)
        function fChannelArray = version_0_1_channel_array()

            fChannelArray = ChannelArray();
            % Hardware-to-grid channel mapping. This is a constant only for Muse Beta (AxIS v0.1)
            % and file format version 0.1.  For later versions, mapping is loaded from the file itself.
            fChannelMapping          = LegacySupport.P200D30S_CHANNEL_MAPPING;
            fChannelArray.PlateType   = LegacySupport.P200D30S_PLATE_TYPE;

            fChannelArray.Channels = ChannelMapping.empty(0,(length(fChannelMapping)));

            for fiCol = 1:size(fChannelMapping, 1)
                for fiRow = 1:size(fChannelMapping, 2)
                    fCurrentChannelIndex = fChannelMapping(fiRow, fiCol);

                    fNewMapping = ChannelMapping(...
                        1, 1,...
                        fiCol, fiRow,...
                        0, fCurrentChannelIndex);

                    fChannelArray.Channels(fCurrentChannelIndex + 1) = fNewMapping;
                end
            end

            fChannelArray.RebuildHashMaps();

        end
    end

end

