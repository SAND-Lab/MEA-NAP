%{
    Copyright (c) 2024 Axion BioSystems, Inc.
    Contact: support@axion-biosystems.com
    All Rights Reserved
%}
classdef BlockVectorHeader < Entry
    %BlockVectorHeader Primary data regarding a BlockVectorSet of Data
    %   This class contains the basic information about an entry of
    %   Block Vector Data that is necessary to load it as a series of
    %   vectors.
    %
    %    SamplingFrequency:     Recording sampling rate (in Hz) of the data
    %
    %    VoltageScale:          Voltage (in Volts) of the conversion factor
    %                           from the stored int16's in the Data vectors
    %                           to a real voltage value. i.e. Signal =
    %                           double(VoltageScale) * Waveform.Data
    %
    %    FileStartTime:         DateTime (See DateTime.m) when this
    %                           recording started
    %
    %    ExperimentStartTime:   DateTime (See DateTime.m) when the
    %                           device that acquired this data started
    %                           aquiring
    %
    %    FirstBlock:            Pointer (# of bytes frome the beginning of
    %                           the file) to the start of the associated
    %                           BlockVectorData entry
    %
    %    NumChannelsPerBlock:   Number of Channels of data stored in every
    %                           block of the data.
    %
    %    NumSamplesPerBlock:    Number of samples in every channel-wise
    %                           vector of the block.
    %
    %    BlockHeaderSize:       Number of bytes used for header of each
    %                           block.
    %
    properties (Constant = true, GetAccess = public)
        SIZE = 64;
    end

    properties(GetAccess = public, SetAccess = private)
        SamplingFrequency
        VoltageScale
        FileStartTime
        ExperimentStartTime
        FirstBlock
        NumChannelsPerBlock
        NumSamplesPerBlock
        BlockHeaderSize
    end

    methods
        function this = BlockVectorHeader(aEntryRecord, aFileID)
            this = this@Entry(aEntryRecord, int64(ftell(aFileID)));

            this.SamplingFrequency   = fread(aFileID, 1, 'double=>double');
            this.VoltageScale        = fread(aFileID, 1, 'double=>double');
            this.FileStartTime       = DateTime(aFileID);
            this.ExperimentStartTime = DateTime(aFileID);
            this.FirstBlock          = fread(aFileID, 1, 'int64=>int64');
            this.NumChannelsPerBlock = fread(aFileID, 1, 'uint32=>uint32');
            this.NumSamplesPerBlock  = fread(aFileID, 1, 'uint32=>uint32');
            this.BlockHeaderSize     = fread(aFileID, 1, 'uint32=>uint32');

            if(this.EntryRecord.Length ~= -1 && ...
                ftell(aFileID) ~= (this.Start + this.EntryRecord.Length))
                error('Unexpected BlockVectorHeader length')
            end

        end
    end

    methods (Static = true)
        function this = Generate(...
                aFileID, ...
                aSamplingFrequency, ...
                aVoltageScale, ...
                aFileStartTime, ...
                aExperimentStartTime, ...
                aFirstBlock, ...
                aNumChannelsPerBlock, ...
                aNumSamplesPerBlock, ...
                aBlockHeaderSize)

            this = BlockVectorHeader(EntryRecord(EntryRecordID.BlockVectorHeader, -1), aFileID);
            this.SamplingFrequency   = aSamplingFrequency;
            this.VoltageScale        = aVoltageScale;
            this.FileStartTime       = aFileStartTime;
            this.ExperimentStartTime = aExperimentStartTime;
            this.FirstBlock          = aFirstBlock;
            this.NumChannelsPerBlock = aNumChannelsPerBlock;
            this.NumSamplesPerBlock  = aNumSamplesPerBlock;
            this.BlockHeaderSize     = aBlockHeaderSize;

        end
    end

end