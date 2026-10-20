%{
    Copyright (c) 2024 Axion BioSystems, Inc.
    Contact: support@axion-biosystems.com
    All Rights Reserved
%}

%DATASET: Handle by which data is laoded from an Axion File.
%   VersionMajor: Writing version (Major number) that was used to
%   serialize this BlockVector.
%
%   VersionMinor: Writing version (Minor number) that was used to
%   serialize this BlockVector.
%
%   DataType: Type of the data in this entry. (BlockVectorDataType.m)
%
%   Name: Name of this data set.
%
%   Description: Description of this data set.
%
%   SamplingFrequency: Sampling frequency of the data associated with
%   this header in Hz.
%
%   VoltageScale: The value by which to multiply encoded values to get
%   the actual voltage in native units. e.g. Volts / Count
%
%   BlockVectorStartTime: The time that this specific vector started
%   recording.
%
%   ExperimentStartTime: The time that the experiment started
%   recording. Note: This is constant across multiple files within an
%   experiment.
%
%   AddedDate: The Date/Time that this data was added to this file.
%
%   ModifiedDate: The Date/Time that this data was last
%   modified(Created, Not updated if copied from another file!)
%
%   DataRegion: Area where the block vector is located. Commented for
%   now.
%
%   SampleType: Type of the samples stored in the block vector.
%
%   VectorHeaderSize: Number of bytes that lead the actual data blocks
%   with Vector specific header.
%
%   BlockHeaderSize: The total size of a specific Data-Block Header.
%   (See individual file formats for description.)
%
%   NumChannelsPerBlock: Number of channels for each Raw Data Block.
%
%   NumDataSetsPerBlock: Number of data sets per channel per block.
%
%   NumSamplesPerBlock: Number of samples for each Raw Data Block.
%
%   DataRegionStart: Index of first byte of the data block, referenced
%   from the start of the file.
%
%   DataRegionLength: Size of data region in bytes.
%
classdef DataSet < handle & matlab.mixin.Heterogeneous & matlab.mixin.CustomDisplay

    properties (GetAccess = public, SetAccess = protected)
        ChannelArray
    end

    properties (GetAccess = private, SetAccess = protected)
        mLoadData;
    end

    properties (GetAccess = public, SetAccess = private)
        FileID                 % File Handle to be used for file reading operations.
        SourceFile             % Axion file to keep the parnt instanc from being GC'd
                                % if we orphan this set
        %Normaly Visible
        Name
        Description
        SamplingFrequency
        VoltageScale
        BlockVectorStartTime
        ExperimentStartTime
        AddedDate
        ModifiedDate

        %Public, but hidden
        VersionMajor
        VersionMinor
        DataType
        SampleType
        VectorHeaderSize
        BlockHeaderSize
        NumChannelsPerBlock
        NumDataSetsPerBlock
        NumSamplesPerBlock
        DataRegionStart
        DataRegionLength
    end

    methods (Static = true)
        % Construct() - Construct an emprty Data Set
        % Construct(BlockVectorSet) Construct a Data set from a block Vector set
        function this = Construct(varargin)
            this = DataSet(varargin{:});
            fUpgrade = false;
            fCombinedBlockVector = [];
            switch nargin
                case 0
                    fUpgrade = false;
                case 1
                    if (isa(varargin{1}, 'BlockVectorSet'))
                        fUpgrade = true;
                        fCombinedBlockVector = varargin{1}.CombinedBlockVector;
                    end
                otherwise
                    error('Unexpected Argument')
            end
            if(fUpgrade)
                switch this.DataType
                    case BlockVectorDataType.Raw_v1
                        this = ContinuousDataSet(this);
                    case BlockVectorDataType.Spike_v1
                        this = SpikeDataSet(this, fCombinedBlockVector);
                    case BlockVectorDataType.NamedContinuousData
                        this = ContinuousDataSet(this, fCombinedBlockVector);
                end
            end
        end
    end

    methods
        % DataSet() - Construct an emprty Data Set
        % DataSet(ChannelArray, CombinedBlockVector) Construct a data set from a CombinedBlockVector
        % DataSet(ChannelArray, Header, HeaderExtension, Data) Construct a data set from an Old Block Vector Set
        function this = DataSet(varargin)
            this = this@handle();
            this@matlab.mixin.Heterogeneous();
            this@matlab.mixin.CustomDisplay();

            switch nargin
                case 0
                    % Creating an empty Data Set
                    this.FileID = [];
                    this.SourceFile = [];
                    this.VersionMajor = [];
                    this.VersionMinor = [];
                    this.DataType = [];
                    this.SampleType = [];
                    this.VectorHeaderSize = [];
                    this.BlockHeaderSize = [];
                    this.NumChannelsPerBlock = [];
                    this.NumDataSetsPerBlock = [];
                    this.NumSamplesPerBlock = [];
                    this.DataRegionStart = [];
                    this.DataRegionLength = [];
                    this.ChannelArray = [];
                    this.Name = [];
                    this.Description = [];
                    this.SamplingFrequency = [];
                    this.VoltageScale = [];
                    this.BlockVectorStartTime = [];
                    this.ExperimentStartTime = [];
                    this.AddedDate = [];
                    this.ModifiedDate = [];
                case 1
                    fArg = varargin{1};
                    if (isa(fArg, 'DataSet'))
                        this.FileID = fArg.FileID;
                        this.SourceFile = fArg.SourceFile;
                        this.VersionMajor = fArg.VersionMajor;
                        this.VersionMinor = fArg.VersionMinor;
                        this.DataType = fArg.DataType;
                        this.SampleType = fArg.SampleType;
                        this.VectorHeaderSize = fArg.VectorHeaderSize;
                        this.BlockHeaderSize = fArg.BlockHeaderSize;
                        this.NumChannelsPerBlock = fArg.NumChannelsPerBlock;
                        this.NumDataSetsPerBlock = fArg.NumDataSetsPerBlock;
                        this.NumSamplesPerBlock = fArg.NumSamplesPerBlock;
                        this.DataRegionStart = fArg.DataRegionStart;
                        this.DataRegionLength = fArg.DataRegionLength;
                        this.ChannelArray = fArg.ChannelArray;
                        this.mLoadData = fArg.mLoadData;
                        this.Name = fArg.Name;
                        this.Description = fArg.Description;
                        this.SamplingFrequency = fArg.SamplingFrequency;
                        this.VoltageScale = fArg.VoltageScale;
                        this.BlockVectorStartTime = fArg.BlockVectorStartTime;
                        this.ExperimentStartTime = fArg.ExperimentStartTime;
                        this.AddedDate = fArg.AddedDate;
                        this.ModifiedDate = fArg.ModifiedDate;
                    elseif (isa(fArg, 'BlockVectorSet'))
                        %Source File and File handle come from the
                        %BlockVector set
                        this.SourceFile = fArg.SourceFile;
                        this.FileID = fArg.SourceFile.FileID;
                        if (isa(fArg.CombinedBlockVector, 'CombinedBlockVectorHeaderEntry'))
                            %Extract the feilds we need
                            fChannelArray = fArg.ChannelArray;
                            fCombinedBlockVector = fArg.CombinedBlockVector;

                            % Filter Channel Array
                            this.ChannelArray = fChannelArray;

                            % All Other Properties
                            this.VersionMajor = fCombinedBlockVector.VersionMajor;
                            this.VersionMinor = fCombinedBlockVector.VersionMinor;
                            this.DataType = fCombinedBlockVector.DataType;
                            this.SampleType = fCombinedBlockVector.SampleType;
                            this.VectorHeaderSize = fCombinedBlockVector.VectorHeaderSize;
                            this.BlockHeaderSize = fCombinedBlockVector.BlockHeaderSize;
                            this.NumChannelsPerBlock = fCombinedBlockVector.NumChannelsPerBlock;
                            this.NumDataSetsPerBlock = fCombinedBlockVector.NumDataSetsPerBlock;
                            this.NumSamplesPerBlock = fCombinedBlockVector.NumSamplesPerBlock;
                            this.DataRegionStart = fCombinedBlockVector.DataRegionStart;
                            this.DataRegionLength = fCombinedBlockVector.DataRegionLength;
                            this.Name = fCombinedBlockVector.Name;
                            this.Description = fCombinedBlockVector.Description;
                            this.SamplingFrequency = fCombinedBlockVector.SamplingFrequency;
                            this.VoltageScale = fCombinedBlockVector.VoltageScale;
                            this.BlockVectorStartTime = fCombinedBlockVector.BlockVectorStartTime;
                            this.ExperimentStartTime = fCombinedBlockVector.ExperimentStartTime;
                            this.AddedDate = fCombinedBlockVector.AddedDate;
                            this.ModifiedDate = fCombinedBlockVector.ModifiedDate;
                        else
                            %Extract the feilds we need
                            fChannelArray = fArg.ChannelArray;
                            fHeader = fArg.Header;
                            fHeaderExtension = fArg.HeaderExtension;
                            fData = fArg.Data;

                            % Stub in new Options
                            this.SampleType = BlockVectorSampleType.Short;
                            this.VectorHeaderSize = 0;
                            this.NumDataSetsPerBlock = 1;

                            % ChannelArray Members
                            this.ChannelArray = fChannelArray;

                            % Header Memembers
                            this.BlockHeaderSize = fHeader.BlockHeaderSize;
                            this.NumSamplesPerBlock = fHeader.NumSamplesPerBlock;
                            this.NumChannelsPerBlock = fHeader.NumChannelsPerBlock;
                            this.SamplingFrequency = fHeader.SamplingFrequency;
                            this.VoltageScale = fHeader.VoltageScale;
                            this.BlockVectorStartTime = fHeader.FileStartTime;
                            this.ExperimentStartTime = fHeader.ExperimentStartTime;

                            % Header Extension Memembers
                            if( isempty(fHeaderExtension) )
                                this.VersionMajor = 0;
                                this.VersionMinor = 0;
                                this.DataType = BlockVectorDataType.Raw_v1;
                                this.Name = [];
                                this.Description = [];
                                this.AddedDate = [];
                                this.ModifiedDate = [];
                            else
                                this.VersionMajor = fHeaderExtension.ExtensionVersionMajor;
                                this.VersionMinor = fHeaderExtension.ExtensionVersionMinor;
                                this.DataType = fHeaderExtension.DataType;
                                this.Name = fHeaderExtension.Name;
                                this.Description = fHeaderExtension.Description;
                                this.AddedDate = fHeaderExtension.Added;
                                this.ModifiedDate = fHeaderExtension.Modified;
                            end
                            %Data Members
                            this.DataRegionStart = fData.Start;
                            this.DataRegionLength = fData.EntryRecord.Length;
                        end
                    end
                otherwise
                    error('Unexpected Argument count')
            end

        end
    end

    methods
       % LoadData loads a Dataset, creaing a data structure similar
        % to the one created by load_AxIS_file (Deprecated)
        %
        %  Legal forms:
        %     data = LoadData();
        %     data = LoadData(well);
        %     data = LoadData(electrode);
        %     data = LoadData(well, electrode);
        %     data = LoadData(timespan);
        %     data = LoadData(well, timespan);
        %     data = LoadData(electrode, timespan);
        %     data = LoadData(well, electrode, timespan);
        %     data = LoadData(dimensions);
        %     data = LoadData(well, dimensions);
        %     data = LoadData(electrode, dimensions);
        %     data = LoadData(well, electrode, dimensions);
        %     data = LoadData(timespan, dimensions);
        %     data = LoadData(well, timespan, dimensions);
        %     data = LoadData(electrode, timespan, dimensions);
        %     data = LoadData(well, electrode, timespan, dimensions);
        %
        %  Optional arguments:
        %    well        String listing which wells (in a multiwell file) to load.
        %                Format is a comma-delimited string with whitespace ignored, e.g.
        %                'A1, B2,C3' limits the data loaded to wells A1, B2, and C3.
        %                Also acceptable: 'all' to load all wells.
        %                If this parameter is omitted, all wells are loaded.
        %                For a single-well file, this parameter is ignored.
        %
        %    electrode   Which electrodes to load.  Format is either a comma-delimited string
        %                with whitespace ignored (e.g. '11, 22,33') or a single channel number;
        %                that is, a number, not part of a string.
        %                Also acceptable: 'all' to load all channels and 'none', '-1', or -1
        %                to load no data (returns only header information).
        %                If this parameter is omitted, all channels are loaded.
        %
        %    timespan    Span of time, in seconds, over which to load data.  Format is a two-element
        %                array, [t0 t1], where t0 is the start time and t1 is the end time and both
        %                are in seconds after the first sample in the file.  Samples returned are ones
        %                that were taken at time >= t0 and <= t1.  The beginning of the file
        %                is at 0 seconds.
        %                If this parameter is omitted, the data is not filtered based on time.
        %
        %    dimensions  Preferred number of dimensions to report the waveforms in.
        %                Value must be a whole number scalar: 1, 3, or 5 (Other values are ignored):
        %
        %                dimensions = 1 -> ByPlate: returns a vector of Waveform objects, 1 Waveform
        %                                  per signal in the plate
        %
        %                dimensions = 3 -> ByWell: Cell Array of vectors of waveform 1 Waveform per signal
        %                                  in the electrode with size (well Rows) x (well Columns)
        %
        %                dimensions = 5 -> ByElectrode: Cell Array of vectors of waveform 1 Waveform per .
        %                                  signal in the electrode with size (well Rows) x (well Columns) x
        %                                  (electrode Columns) x (electrode Rows)
        %
        %                NOTE: The default loading dimensions for
        %                continous raw data is 5 and the default for
        %                spike data is 3.
        function aData = LoadData(this, varargin)
            aData = this.mLoadData(varargin{:});
        end
    end

    methods(Static, Access = protected)

        function ChannelListOut = get_channels_to_load(aChannelArray, aTargetWells, aTargetElectrodes)

            % Decode the aTargetWells string
            if strcmp(aTargetWells, 'all')
                % User has requested all wells - figure out what those
                % are from the channel array
                fTargetWells = DataSet.all_wells_electrodes([aChannelArray.Channels.WellColumn], ...
                    [aChannelArray.Channels.WellRow]);
            else
                fTargetWells = aTargetWells;
            end

            % Decode the aTargetElectrodes string
            if strcmp(aTargetElectrodes, 'all')
                % User has requested all electrodes - figure out what those
                % are from the channel array
                switch aChannelArray.PlateType
                    case {PlateTypes.NinetySixWell, PlateTypes.NinetySixWellCircuit, ...
                          PlateTypes.NinetySixWellTransparent, PlateTypes.NinetySixWellLumos,  ...
                          PlateTypes.Reserved02}
                        fTargetElectrodes = DataSet.all_8electrodes();
                    otherwise
                        fTargetElectrodes = DataSet.all_wells_electrodes(...
                            [aChannelArray.Channels.ElectrodeColumn], ...
                            [aChannelArray.Channels.ElectrodeRow]);
                end

            elseif strcmp(aTargetElectrodes, 'none')
                % User has requested no electrodes
                fTargetElectrodes = [];
            else
                fTargetElectrodes = aTargetElectrodes;
            end

            ChannelListOut = zeros(1, size(fTargetWells, 1) * size(fTargetElectrodes, 1));
            if ~isempty(ChannelListOut)

                for fChannelArrayIndex = 1:length(aChannelArray.Channels)
                    fCurrentChannel = aChannelArray.Channels(fChannelArrayIndex);

                    [fFoundWell, fIdxWell] = ismember( [fCurrentChannel.WellColumn  fCurrentChannel.WellRow], ...
                        fTargetWells, 'rows');
                    if ~any(fFoundWell)
                        continue;
                    end

                    [fFoundElectrode, fIdxElectrode ] = ismember( [fCurrentChannel.ElectrodeColumn  fCurrentChannel.ElectrodeRow], ...
                        fTargetElectrodes, 'rows');

                    if ~any(fFoundElectrode)
                        continue;
                    end

                    ChannelListOut( (fIdxWell - 1) * size(fTargetElectrodes, 1) + fIdxElectrode ) = fChannelArrayIndex;
                end

                % Notify the user of any requested channels that weren't found in the channel array.
                % This is not necessarily an error; for example, if a whole well is requested, and
                % some channels in that well weren't recorded, we should return the well without
                % the "missing" channel.
                fChannelIdxZeros = find(ChannelListOut == 0);
                for i=1:length(fChannelIdxZeros)
                    fIdxNotFound = fChannelIdxZeros(i);
                    fMissingWell = floor((fIdxNotFound-1) / size(fTargetElectrodes, 1)) + 1;
                    fMissingElectrode = mod(fIdxNotFound-1, size(fTargetElectrodes, 1)) + 1;
                    warning('get_channels_to_load:invalidWellElectrode', ...
                        sprintf('Well/electrode %d %d / %d %d not recorded in file', ...
                        fTargetWells(fMissingWell, 1), fTargetWells(fMissingWell, 2), ...
                        fTargetElectrodes(fMissingElectrode, 1), fTargetElectrodes(fMissingElectrode, 2)));
                end

                % Strip out any zeros from aChannelListOut, because these correspond to channels that weren't in
                % the loaded channel array, and therefore won't be loaded.
                ChannelListOut = ChannelListOut( ChannelListOut ~= 0 );
            end

        end % end function

        % Subfunction to expand an 'all' well or electrode list
        function fOutput = all_wells_electrodes(aColumns, aRows)
            aColumns = unique(aColumns); % sort ascending and dedup
            aRows    = unique(aRows);

            fNumRows = length(aRows);
            fNumCols = length(aColumns);
            fOutput  = zeros(fNumRows * fNumCols, 2);
            for fiRow = 1:fNumRows
                for fiCol = 1:fNumCols

                    fIndex = ((fiRow-1) * fNumCols) + (fiCol-1) + 1;
                    fOutput(fIndex, 1) = aColumns(fiCol);
                    fOutput(fIndex, 2) = aRows(fiRow);

                end
            end
        end

        % Subfunction to expand an 'all' for 8 well electrodes
        function fOutput = all_8electrodes()
            fOutput = uint8([...
                [1, 1];...
                [2, 1];...
                [3, 1];...
                [1, 2];...
                [2, 2];...
                [1, 3];...
                [2, 3];...
                [3, 3]]);...
        end

        % Subfunction to help with channel array search
        function aMatch = match_well_electrode(aChannelStruct, aWellElectrode)

            if aChannelStruct.wellColumn == aWellElectrode(1) && ...
                    aChannelStruct.wellRow    == aWellElectrode(2) && ...
                    aChannelStruct.electrodeColumn == aWellElectrode(3) && ...
                    aChannelStruct.electrodeRow    == aWellElectrode(4)
                aMatch = 1;
            else
                aMatch = 0;
            end

        end
    end

    methods (Access = protected)
        function propgrp = getPropertyGroups(obj)
            if ~isscalar(obj)
                propgrp = getPropertyGroups@matlab.mixin.CustomDisplay(obj);
            else
                propList = struct(...
                    'SamplingFrequency', obj.SamplingFrequency,...
                    'VoltageScale', obj.VoltageScale,...
                    'BlockVectorStartTime', obj.BlockVectorStartTime.ToDateTimeString(), ...
                    'ExperimentStartTime', obj.ExperimentStartTime.ToDateTimeString());
                propgrp = matlab.mixin.util.PropertyGroup(propList);
            end
        end
    end

    methods
        function bytes = NumBytesPerBlock(this)
            bytes = this.BlockHeaderSize + ...
            this.NumDataSetsPerBlock * ...
            this.NumChannelsPerBlock * ...
            this.NumSamplesPerBlock * ...
            BlockVectorSampleType.GetSizeInBytes(this.SampleType);
        end

        function blocks = NumBlocks(this)
            blocks = this.DataRegionLength / int64(this.NumBytesPerBlock);
        end

        function outVal = IsRawVoltage(this)
            switch this.DataType
                case BlockVectorDataType.Raw_v1
                    outVal = true;
                    return;
                case BlockVectorDataType.NamedContinuousData
                    if( strcmp(this.Name, 'Voltage') && ...
                         (iscell(this.DataSetNames)) && ...
                         (length(this.DataSetNames) == 1))
                        outVal =...
                            strcmp(this.DataSetNames{1}, 'Raw') || ...
                            strcmp(this.DataSetNames{1}, 'Broadband High-Frequency') || ...
                            strcmp(this.DataSetNames{1}, 'Broadband Low-Frequency') ;
                        return;
                    end
            end
            outVal = false;
        end
        
        function outVal = IsBbpHigh(this)
            outVal = (this.DataType == BlockVectorDataType.NamedContinuousData &&...
                 strcmp(this.Name, 'Voltage') && ...
                 (iscell(this.DataSetNames)) && ...
                 (length(this.DataSetNames) == 1) && ...
                 strcmp(this.DataSetNames{1}, 'Broadband High-Frequency'));
            return;
        end
        
        function outVal = IsBbpLow(this)
            outVal = (this.DataType == BlockVectorDataType.NamedContinuousData &&...
                 strcmp(this.Name, 'Voltage') && ...
                 (iscell(this.DataSetNames)) && ...
                 (length(this.DataSetNames) == 1) && ...
                 strcmp(this.DataSetNames{1}, 'Broadband Low-Frequency'));
            return;
        end

        
        function outVal = IsRawContractility(this)
            switch this.DataType
                case BlockVectorDataType.NamedContinuousData
                    if( strcmp(this.Name, 'Impedance') && ...
                         (iscell(this.DataSetNames)) && ...
                         (length(this.DataSetNames) == 1) && ...
                         strcmp(this.DataSetNames{1}, 'Raw') )
                        outVal = true;
                        return;
                    end
            end
            outVal = false;
        end

        function outVal = IsSpikes(this)
            switch this.DataType
                case BlockVectorDataType.Spike_v1
                    outVal = isempty(this.DataSetNames) || ...
                        ((iscell(this.DataSetNames)) && ...
                         (length(this.DataSetNames) == 1) && ... 
                         strcmp(this.DataSetNames, 'Spikes'));
                    return;
            end
            outVal = false;
        end
        
        function outVal = IsLfp(this)
            
            switch this.DataType
                case BlockVectorDataType.Spike_v1
                    outVal = ~isempty(this.DataSetNames) && strcmp(this.DataSetNames, 'LFP Events');
                    return;
            end
             outVal = this.DataType == BlockVectorDataType.Spike_v1 && ...
                iscell(this.DataSetNames) && ...
                length(this.DataSetNames) == 1 && ... 
                strcmp(this.DataSetNames, 'Spikes');
        end
    end
end