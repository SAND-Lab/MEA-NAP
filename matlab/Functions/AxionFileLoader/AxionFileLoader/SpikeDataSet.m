%{
    Copyright (c) 2024 Axion BioSystems, Inc.
    Contact: support@axion-biosystems.com
    All Rights Reserved
%}
classdef SpikeDataSet < DataSet

    properties (GetAccess = public, SetAccess = private)
        Duration;
        ChannelIDs;
        DataSetNames;
    end

    properties (GetAccess = private, SetAccess = private)
        mMappedData;
    end

    methods
        function this = SpikeDataSet(varargin)
            this@DataSet(varargin{1});
            this.mLoadData = @this.LoadSpikeData;
            
            fileName = this.SourceFile.FileName;
            numSpikes = this.NumBlocks;
            numSamples = double(this.NumDataSetsPerBlock * this.NumChannelsPerBlock * this.NumSamplesPerBlock);
            reservedSpace = double(this.BlockHeaderSize - Spike_v1.LOADED_HEADER_SIZE);
            
            if length(varargin) > 1 && isa(varargin{2}, 'DiscontinuousBlockVectorHeaderEntry')
                fEntry = varargin{2};
                this.ChannelIDs = fEntry.ChannelIDs;
                this.DataSetNames = {fEntry.DataSetName};
                this.Duration = fEntry.Duration;
            else
                this.ChannelIDs = [ ];
                this.DataSetNames = [ ];
                this.Duration = [ ];
            end 

            if (this.NumDataSetsPerBlock == 1 && ...
                this.NumChannelsPerBlock == 1 && ...
                this.NumSamplesPerBlock >= 1 &&...
                reservedSpace >= 0 &&...
                numSpikes > 0)

                if(reservedSpace == 0)
                    this.mMappedData = memmapfile(fileName,        ...
                        'Format', {                               ...
                            'int64'  [1 1] 'startingSample';      ... % 8 Bytes
                            'uint8'  [1 1] 'channel';             ... % 1 Byte
                            'uint8'  [1 1] 'chip';                ... % 1 Byte
                            'int32'  [1 1] 'triggerSample';       ... % 4 Bytes
                            'double' [1 1] 'standardDeviation';   ... % 8 Bytes
                            'double' [1 1] 'thresholdMultiplier'; ... % 8 Bytes
                            'int16'  [numSamples 1] 'data' },     ... % 2n Bytes
                        'Offset', this.DataRegionStart,           ...
                        'Repeat', numSpikes,                      ...
                        'Writable', false);
                else
                    this.mMappedData = memmapfile(fileName,        ...
                        'Format', {                                ...
                            'int64'  [1 1] 'startingSample';       ... % 8 Bytes
                            'uint8'  [1 1] 'channel';              ... % 1 Byte
                            'uint8'  [1 1] 'chip';                 ... % 1 Byte
                            'int32'  [1 1] 'triggerSample';        ... % 4 Bytes
                            'double' [1 1] 'standardDeviation';    ... % 8 Bytes
                            'double' [1 1] 'thresholdMultiplier';  ... % 8 Bytes
                            'uint8'  [reservedSpace 1] 'reserved'; ...
                            'int16'  [numSamples 1] 'data'},        ... % 2n Bytes
                        'Offset', this.DataRegionStart,            ...
                        'Repeat', numSpikes,                       ...
                        'Writable', false);
                end


            else
                this.mMappedData = [];
            end
        end

        function [aElectrodes, aTimes] = LoadAllSpikes(this)
            % LoadAllSpikes attempts to load all spikes from file
            %
            % Function returns an array of electrodes whre spikes occur
            % and array of times when spikes occur.  There is one entry for
            % every spike.
            %
            % aElectrodes : a structure with two elements (arrays of int8):
            %    aElectrodes.Achk    - Artichoke chip where spike occurred
            %    aElectrodes.Channel - Artichoke's channel where spike
            %    occurred
            %
            % aTimes : array of times (in seconds since file start) when spike occured
            %
            if this.NumChannelsPerBlock ~= 1
                error('Load_spike_v1:argNumChannelsPerBlock', ...
                    'Invalid header for SPIKE file: incorrect channels per block');
            end

            if this.NumDataSetsPerBlock ~= 1
                error('Load_spike_v1:argNumDataSetsPerBlock', ...
                    'Invalid header for SPIKE file: incorrect Data Sets per block');
            end

            if this.BlockHeaderSize < Spike_v1.LOADED_HEADER_SIZE
                error('Load_spike_v1:argBlockHeaderSize', ...
                    'Invalid header for SPIKE file: block header size too small');
            end

            if this.NumSamplesPerBlock < 1
                error('load_AxIS_spike:argNumSamplesPerBlock', ...
                    'Invalid header for SPIKE file: number of samples per block < 1');
            end

            if(isempty(this.mMappedData))
                aElectrodes = [];
                aTimes = [];
                return;
            end
            fData = this.mMappedData.Data;
            aElectrodes.Achk = int8([fData.chip]);
            aElectrodes.Channel = int8([fData.channel]);
            fStartingSample = double([fData.startingSample]);
            fSampleOffset = double([fData.triggerSample]);
            aTimes = (fStartingSample + fSampleOffset) ./ this.SamplingFrequency;
        end
    end

    methods (Access = private)
        function aData = LoadSpikeData(this, varargin)
            fLoadArgs = LoadArgs(varargin);
            fTargetWell = fLoadArgs.Well;
            fTargetElectrode = fLoadArgs.Electrode;

            fChannelsToLoad = DataSet.get_channels_to_load(this.ChannelArray, fTargetWell, fTargetElectrode);

            if fLoadArgs.SubsamplingFactor ~= 1
                warning('Spike file subsampling is not supported at this time.')
            end

            fDimensions = fLoadArgs.Dimensions;
            if(isempty(fDimensions))
                fDimensions = LoadArgs.ByElectrodeDimensions;
            end
            aData = this.GetSpikeV1Waveforms( ...
                this, ...
                fChannelsToLoad, ...
                fLoadArgs.Timespan, ...
                fDimensions);

        end

        function Waveforms = GetSpikeV1Waveforms(...
                this, ...
                aSourceSet, ...
                aChannelsToLoad, ...
                aTimeRange, ...
                aDimensions)

            fStorageType = 0;

            switch aDimensions
                case {LoadArgs.ByWellDimensions}
                    fStorageType = 1;
                case {LoadArgs.ByElectrodeDimensions}
                    fStorageType = 2;
            end

            if this.NumChannelsPerBlock ~= 1
                error('Load_spike_v1:argNumChannelsPerBlock', ...
                    'Invalid header for SPIKE file: incorrect channels per block');
            end

            if this.NumDataSetsPerBlock ~= 1
                error('Load_spike_v1:argNumDataSetsPerBlock', ...
                    'Invalid header for SPIKE file: incorrect Data Sets per block');
            end

            if this.BlockHeaderSize < Spike_v1.LOADED_HEADER_SIZE
                error('Load_spike_v1:argBlockHeaderSize', ...
                    'Invalid header for SPIKE file: block header size too small');
            end

            if this.NumSamplesPerBlock < 1
                error('load_AxIS_spike:argNumSamplesPerBlock', ...
                    'Invalid header for SPIKE file: number of samples per block < 1');
            end

            fMaxExtents = PlateTypes.GetElectrodeDimensions(aSourceSet.ChannelArray.PlateType);

            if (isempty(fMaxExtents))
                fMaxExtents = [max([aSourceSet.ChannelArray.Channels(:).WellRow]), ...
                    max([aSourceSet.ChannelArray.Channels(:).WellColumn]), ...
                    max([aSourceSet.ChannelArray.Channels(:).ElectrodeColumn]), ...
                    max([aSourceSet.ChannelArray.Channels(:).ElectrodeRow])];
            end

            fDesiredChannelsLut = zeros(length(aSourceSet.ChannelArray.Channels),1);

            fDesiredChannelsLut(aChannelsToLoad) = 1;

            fChannelArray = this.ChannelArray;

            if(isempty(this.mMappedData))
                Waveforms = [];
                return;
            end
            
            if(sum(fDesiredChannelsLut) < length(fChannelArray.Channels))
                data = this.mMappedData.Data;
                fLoadedSpikes = fChannelArray.LookupChannel(...
                    [data.chip], [data.channel]);
                fLoadedSpikes = this.mMappedData.Data(...
                    logical(fDesiredChannelsLut(fLoadedSpikes)));
            else
                fLoadedSpikes = this.mMappedData.Data;
            end

            if (~(ischar(aTimeRange) && strcmp(aTimeRange, 'all')))
                fFirstSample = aTimeRange(1) * this.SamplingFrequency;
                fLastSample  = aTimeRange(2) * this.SamplingFrequency;
                fLoadedSpikes = fLoadedSpikes([fLoadedSpikes.startingSample] >= fFirstSample);
                fLoadedSpikes = fLoadedSpikes([fLoadedSpikes.startingSample] < fLastSample);
            end
            switch fStorageType
                case 0
                    fLoadedSpikes = arrayfun(@(spikeStruct)(Spike_v1( ...
                        fChannelArray.LookupChannelMapping(spikeStruct.chip, spikeStruct.channel), ...
                        double(spikeStruct.startingSample) / this.SamplingFrequency, ...
                        spikeStruct.data, ...
                        aSourceSet, ...
                        spikeStruct.triggerSample, ...
                        spikeStruct.standardDeviation, ...
                        spikeStruct.thresholdMultiplier)), fLoadedSpikes, ...
                        'UniformOutput', false);
                    Waveforms = [fLoadedSpikes{:}];
                case 1
                    Waveforms = cell(double(fMaxExtents(1:2)));
                    for spikeStruct = fLoadedSpikes'
                        fSpike = Spike_v1( ...
                            fChannelArray.LookupChannelMapping(spikeStruct.chip, spikeStruct.channel), ...
                            double(spikeStruct.startingSample) / this.SamplingFrequency, ...
                            spikeStruct.data, ...
                            aSourceSet, ...
                            spikeStruct.triggerSample, ...
                            spikeStruct.standardDeviation, ...
                            spikeStruct.thresholdMultiplier);
                        fOuputIndex = double([...
                            fSpike.Channel.WellRow, ...
                            fSpike.Channel.WellColumn]);
                        Waveforms{fOuputIndex(1),fOuputIndex(2)}(...
                            length(Waveforms{fOuputIndex(1),fOuputIndex(2)}) + 1) = fSpike;
                    end

                case 2
                    Waveforms = cell(double(fMaxExtents));
                    for spikeStruct = fLoadedSpikes'
                        fSpike = Spike_v1( ...
                            fChannelArray.LookupChannelMapping(spikeStruct.chip, spikeStruct.channel), ...
                            double(spikeStruct.startingSample) / this.SamplingFrequency, ...
                            spikeStruct.data, ...
                            aSourceSet, ...
                            spikeStruct.triggerSample, ...
                            spikeStruct.standardDeviation, ...
                            spikeStruct.thresholdMultiplier);
                        fOuputIndex = double([...
                            fSpike.Channel.WellRow, ...
                            fSpike.Channel.WellColumn, ...
                            fSpike.Channel.ElectrodeColumn, ...
                            fSpike.Channel.ElectrodeRow]);
                        Waveforms{fOuputIndex(1),fOuputIndex(2), fOuputIndex(3),fOuputIndex(4)}(...
                            length(Waveforms{fOuputIndex(1),fOuputIndex(2), fOuputIndex(3),fOuputIndex(4)}) + 1) = fSpike;
                    end

            end
        end
    end
    
    methods (Access = protected)
        function propgrp = getPropertyGroups(obj)
            if ~isscalar(obj)
                propgrp = getPropertyGroups@matlab.mixin.CustomDisplay(obj);
            else
                if(~isempty(obj.DataSetNames) && iscell(obj.DataSetNames))
                    propList = struct(...
                        'Name',obj.Name,...
                        'DataSetNames',obj.DataSetNames,...
                        'Description',obj.Description,...
                        'SamplingFrequency', obj.SamplingFrequency,...
                        'Duration', obj.Duration,...
                        'VoltageScale', obj.VoltageScale,...
                        'ChannelIDs', obj.ChannelIDs,...
                        'BlockVectorStartTime', obj.BlockVectorStartTime.ToDateTimeString(), ...
                        'ExperimentStartTime',obj.ExperimentStartTime.ToDateTimeString(),...
                        'AddedDate', obj.AddedDate.ToDateTimeString(),...
                        'ModifiedDate', obj.ModifiedDate.ToDateTimeString());
                elseif(~(isempty(obj.AddedDate) ||  isempty(obj.ModifiedDate)))
                    propList = struct(...
                        'Description',obj.Description,...
                        'SamplingFrequency', obj.SamplingFrequency,...
                        'VoltageScale', obj.VoltageScale,...
                        'BlockVectorStartTime', obj.BlockVectorStartTime.ToDateTimeString(), ...
                        'ExperimentStartTime',obj.ExperimentStartTime.ToDateTimeString(),...
                        'AddedDate', obj.AddedDate.ToDateTimeString(),...
                        'ModifiedDate', obj.ModifiedDate.ToDateTimeString());
                else
                    propgrp = DataSet(obj).getPropertyGroups();
                    return;
                end
                propgrp = matlab.mixin.util.PropertyGroup(propList);
            end
        end
    end
end