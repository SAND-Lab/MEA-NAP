%{
    Copyright (c) 2024 Axion BioSystems, Inc.
    Contact: support@axion-biosystems.com
    All Rights Reserved
%}
classdef EntryRecordID < uint8
    %ENTRYRECORDID Values for entry record types used in headers /
    %   subheaders
    %
    %   Terminate: Used to indicate the end of the record entries in
    %   headers/ subheaders.
    %
    %   Skip: Indicates an area of the file to be ignored.
    %
    %   NotesArray: see Notes.m
    %
    %   ChannelArray: see ChannelArray.m
    %
    %   BlockVectorHeader: see BlockVectorHeader.m
    %
    %   BlockVectorData: see BlockVectorData.m
    %
    %   BlockVectorHeaderExtension: see BlockVectorHeaderExtension.m
    %
    %   CombinedBlockVectorHeader: see CombinedBlockVectorHeaderEntry.m
    %

    enumeration
        Terminate(uint8(hex2dec('00'))),...
        Skip(uint8(hex2dec('ff'))),...
        NotesArray(uint8(hex2dec('01'))) ,...
        ChannelArray(uint8(hex2dec('02'))),...
        BlockVectorHeader(uint8(hex2dec('03'))),...
        BlockVectorData(uint8(hex2dec('04'))),...
        BlockVectorHeaderExtension(uint8(hex2dec('05'))),...
        Tag(uint8(hex2dec('06'))),...
        CombinedBlockVectorHeader(uint8(hex2dec('07')))
    end

    methods(Static)
        function [value , success] = TryParse(aInput)
            try
                value = EntryRecordID(aInput);
                success = true;
            catch e
                warning(...
                    'EntryRecordID:TryParse',  ...
                    ['Unsupported EntryRecordID', e.message]);

                value = aInput;
                success = false;
            end
        end
    end

end

