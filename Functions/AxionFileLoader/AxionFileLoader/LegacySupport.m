%{
    Copyright (c) 2024 Axion BioSystems, Inc.
    Contact: support@axion-biosystems.com
    All Rights Reserved
%}
classdef LegacySupport
    %LEGACYSUPPORT This is a static class that contains resources for
    %loading old style Axis Data
    properties(Constant)
        P200D30S_PLATE_TYPE      = hex2dec('0400001');
        INITIAL_HEADER_LENGTH = 1024;
        DATA_START_OFFSET = 44;
        CHANNEL_ARRAY_OFFSET = 4;

        NUM_COEFFICIENTS = 4;

        P200D30S_CHANNEL_MAPPING = ...
            [54 50 46 42 35 36 37 38 ;
            53 49 45 41 31 32 33 34 ;
            52 48 44 40 27 28 29 30 ;
            51 47 43 39 23 24 25 26 ;
            58 57 56 55  7 11 15 19 ;
            62 61 60 59  8 12 16 20 ;
            2  1  0 63  9 13 17 21 ;
            6  5  4  3 10 14 18 22 ];
    end

    methods(Static)

        function fEntryRecords = GenerateEntries(aFileID, aEntriesStart)

            fseek(aFileID, LegacySupport.INITIAL_HEADER_LENGTH + LegacySupport.DATA_START_OFFSET, 'bof');% 44 is the offset of the datastart in the Matlab Freindly Header
            fDataStart = fread(aFileID, 1, 'int64');

            fseek(aFileID, LegacySupport.INITIAL_HEADER_LENGTH + BlockVectorHeader.SIZE + LegacySupport.CHANNEL_ARRAY_OFFSET, 'bof');
            fNumChannels = fread(aFileID, 1, 'uint32=>uint32');
            fChannelArraySize = 8 * (fNumChannels + 1);

            fseek(aFileID, 0, 'eof');
            fEOF = ftell(aFileID);

            fPostNotesGap = LegacySupport.INITIAL_HEADER_LENGTH - (aEntriesStart + Note.SIZE);
            fPostChannelsGap = fDataStart - (LegacySupport.INITIAL_HEADER_LENGTH + BlockVectorHeader.SIZE +fChannelArraySize);

            fEntryRecords = EntryRecord(EntryRecordID.NotesArray, Note.SIZE);

            fEntryRecords = [fEntryRecords EntryRecord(EntryRecordID.Skip, fPostNotesGap)];

            fEntryRecords = [fEntryRecords EntryRecord(EntryRecordID.BlockVectorHeader, BlockVectorHeader.SIZE)];

            fEntryRecords = [fEntryRecords EntryRecord(EntryRecordID.ChannelArray, fChannelArraySize)];

            fEntryRecords = [fEntryRecords EntryRecord(EntryRecordID.Skip, fPostChannelsGap)];

            fEntryRecords = [fEntryRecords EntryRecord(EntryRecordID.BlockVectorData, fEOF - fDataStart)];

            fEntryRecords = [fEntryRecords EntryRecord(EntryRecordID.Terminate, 0)];

        end

        function [fType, fData, fChannelMapping, fHeader] = GenerateRolstonEntries(aFileID, aExtension)
            fChannelMapping = ChannelArray.version_0_1_channel_array();

            fseek(aFileID, 0, 'eof');
            fEOF = ftell(aFileID);
            fseek(aFileID, 0, 'bof');

            if strcmp(aExtension, '.raw')
                % Read header

                fType = BlockVectorDataType.Raw_v1;
                fNumChannels       = fread(aFileID, 1, 'uint16');
                fSamplingFrequency = fread(aFileID, 1, 'uint32');
                fread(aFileID, 1, 'uint16');  %Gain

                coefficients = fread(aFileID, LegacySupport.NUM_COEFFICIENTS, 'double');
                fVoltageScale = coefficients(2) / 1200;

                fExperimentStartTime = DateTime(aFileID);
                fNumSamples = 1;

            elseif strcmp(aExtension, '.spk')
                error('LegacySupport:Unsupported', ...
                    'File appears to be a deprecated AxIS v0.0 spike file, this type of file is not supported');
            else
                error('LegacySupport:extension', ...
                    'File appears to be a deprecated AxIS v0.0 file, but filename does not end with .raw or .spk');
            end

            fDataStart = ftell(aFileID);

            fHeader = BlockVectorHeader.Generate(...
                aFileID, ...
                fSamplingFrequency, ...
                fVoltageScale, ...
                fExperimentStartTime, ...
                fExperimentStartTime, ...
                fDataStart, ...
                fNumChannels, ...
                fNumSamples, ...
                0);

            fData = EntryRecord(EntryRecordID.BlockVectorData, fEOF - fDataStart);
            fseek(aFileID, double(fDataStart), 'bof');
            fData = BlockVectorData(fData, aFileID);

        end
    end
end

