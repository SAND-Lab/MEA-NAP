%{
    Copyright (c) 2024 Axion BioSystems, Inc.
    Contact: support@axion-biosystems.com
    All Rights Reserved
%}
classdef CombinedBlockVectorHeaderEntry < Entry
    %CombinedBlockVectorHeaderEntry Entry which contains the entirety of a
    %block vector
    %
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
    %   Duration: Number of seconds this entry reprsents
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
    %   Size: Size of this header in bytes.
    %
    %   DataRegionStart: Index of first byte of the data block, referenced
    %   from the start of the file.
    %
    %   DataRegionLength: Size of data region in bytes.
    %

    properties (Constant = true, GetAccess = private)
        BASE_SIZE_IN_BYTES = 120;
    end

    properties (GetAccess = public, SetAccess = private)
        VersionMajor
        VersionMinor
        DataType
        Name
        Description
        SamplingFrequency
        VoltageScale
        BlockVectorStartTime
        ExperimentStartTime
        AddedDate
        ModifiedDate
        Duration
        SampleType
        VectorHeaderSize
        BlockHeaderSize
        NumChannelsPerBlock
        NumDataSetsPerBlock
        NumSamplesPerBlock
        DataRegionStart
        DataRegionLength
        CombinedBlockVectorHeaderEntrySize
    end

    methods
        function this = CombinedBlockVectorHeaderEntry( ...
                aEntryRecord, ...
                aFileID, ...
                aVersionMajor, ...
                aVersionMinor, ...
                aDataType, ...
                aSampleType, ...
                aSamplingFrequency, ...
                aVoltageScale, ...
                aNumChannelsPerBlock, ...
                aNumDataSetsPerBlock, ...
                aNumSamplesPerBlock, ...
                aVectorHeaderSize, ...
                aBlockHeaderSize, ...
                aBlockVectorStartTime, ...
                aExperimentStartTime, ...
                aAddedDate, ...
                aModifiedDate, ...
                aDuration, ...
                aName, ...
                aDescription, ...
                aDataRegionStart, ...
                aDataRegionLength, ...
                aSize)

            this = this@Entry(aEntryRecord, int64(ftell(aFileID)));

            % version info
            this.VersionMajor = aVersionMajor;
            this.VersionMinor = aVersionMinor;
            
            % block vector data type
            this.DataType = aDataType;
            
            % sample type 
            this.SampleType = aSampleType;

            % sampling frequency
            this.SamplingFrequency = aSamplingFrequency;
            
            % voltage scale
            this.VoltageScale = aVoltageScale;
            
            this.NumChannelsPerBlock = aNumChannelsPerBlock;
            this.NumDataSetsPerBlock = aNumDataSetsPerBlock;
            this.NumSamplesPerBlock = aNumSamplesPerBlock;
            
            this.VectorHeaderSize = aVectorHeaderSize;
            this.BlockHeaderSize = aBlockHeaderSize;
            
            this.BlockVectorStartTime = aBlockVectorStartTime;
            this.ExperimentStartTime = aExperimentStartTime;
            this.AddedDate = aAddedDate;
            this.ModifiedDate = aModifiedDate;
            this.Duration = aDuration;
            
            this.Name = aName;
            
            this.Description = aDescription;
            
            % Maybe put Start and Length in the DataRegion object
            % (BlockVectorData.m)
            this.DataRegionStart = aDataRegionStart;
            this.DataRegionLength = aDataRegionLength;
            
            this.CombinedBlockVectorHeaderEntrySize = aSize;
        end
    end
    
    methods(Static)
        function obj = Deserialize(aEntryRecord, aFileID)
            % meta data start position in file
            fBlockVectorMetadataStartPos = ftell(aFileID);
            
            % version info
            fVersionMajor = fread(aFileID, 1, 'uint16=>uint16');
            fVersionMinor = fread(aFileID, 1, 'uint16=>uint16');
            
            % block vector data type
            fDataType = BlockVectorDataType.TryParse(fread(aFileID, 1, 'uint16=>uint16'));
            
            % sample type 
            fSampleType = BlockVectorSampleType.TryParse(fread(aFileID, 1, 'uint16=>uint16'));

            % sampling frequency
            fSamplingFrequency   = fread(aFileID, 1, 'double=>double');
            
            % voltage scale
            fVoltageScale        = fread(aFileID, 1, 'double=>double');
            
            fNumChannelsPerBlock = fread(aFileID, 1, 'uint32=>uint32');
            fNumDataSetsPerBlock = fread(aFileID, 1, 'uint32=>uint32');
            fNumSamplesPerBlock = fread(aFileID, 1, 'uint32=>uint32');
            
            fVectorHeaderSize = fread(aFileID, 1, 'uint32=>uint32');
            fBlockHeaderSize = fread(aFileID, 1, 'uint32=>uint32');
            
            fBlockVectorStartTime = DateTime(aFileID);
            fExperimentStartTime = DateTime(aFileID);
            fAddedDate = DateTime(aFileID);
            fModifiedDate = DateTime(aFileID);
            
            % New Duration 
            if (fVersionMajor > 1 || fVersionMinor >= 1)
                fDuration = fread(aFileID, 1, 'double=>double');
            else
                fDuration = [];
            end
            
            fNameStringSizeInBytes = fread(aFileID, 1, 'int=>int');
            fName = fread(aFileID, fNameStringSizeInBytes, '*char').';
            
            fDescriptionStringSizeInBytes = fread(aFileID, 1, 'int=>int');
            fDescription = fread(aFileID, fDescriptionStringSizeInBytes, '*char').';
            
            % Maybe put Start and Length in the DataRegion object
            % (BlockVectorData.m)
            fDataRegionStart = int64(fread(aFileID, 1, 'int64=>int64'));
            fDataRegionLength = int64(fread(aFileID, 1, 'int64=>int64'));
            
            fDataSize = ftell(aFileID) - fBlockVectorMetadataStartPos;
            
            % Calculate and check CRC
            fseek(aFileID, fBlockVectorMetadataStartPos, 'bof');
            fCRCBytes = fread(aFileID, fDataSize, 'uint8');
            
            fCalcCRC = CRC32(AxisFile.CRC_POLYNOMIAL, AxisFile.CRC_SEED).Compute(fCRCBytes);
            fReadCRC = fread(aFileID, 1, 'uint32');
            
            if(fReadCRC ~= fCalcCRC)
                error('BlockVectorMetaData checksum was incorrect: %s', fFilename);
            end
            
            fSize = CombinedBlockVectorHeaderEntry.BASE_SIZE_IN_BYTES + fNameStringSizeInBytes + fDescriptionStringSizeInBytes + 8;
            
            if (fVersionMajor > 1 || fVersionMinor >= 1)
                fSize = fSize + 8; % addDuration Feild
            end
            
            % actual read size
            fBlockVectorMetadataReadSize = ftell(aFileID) - fBlockVectorMetadataStartPos;
            
            if(fSize ~= fBlockVectorMetadataReadSize)
                error('Unexpected BlockVectorMetadata length');
            end
            
            obj = CombinedBlockVectorHeaderEntry( ...
                aEntryRecord, ...
                aFileID, ...
                fVersionMajor, ...
                fVersionMinor, ...
                fDataType, ...
                fSampleType, ...
                fSamplingFrequency, ...
                fVoltageScale, ...
                fNumChannelsPerBlock, ...
                fNumDataSetsPerBlock, ...
                fNumSamplesPerBlock, ...
                fVectorHeaderSize, ...
                fBlockHeaderSize, ...
                fBlockVectorStartTime, ...
                fExperimentStartTime, ...
                fAddedDate, ...
                fModifiedDate, ...
                fDuration, ...
                fName, ...
                fDescription, ...
                fDataRegionStart, ...
                fDataRegionLength, ...
                fSize);
        end
    end
    
end

