%{
    Copyright (c) 2024 Axion BioSystems, Inc.
    Contact: support@axion-biosystems.com
    All Rights Reserved
%}
classdef AxisFile < handle & matlab.mixin.CustomDisplay
    %AXISFILE: Class that holds all Data for a loaded Axion 1.X File
    %
    % Calling A = AxisFile('filename.raw') or AxisFile('filename.spk') will
    % create an AxisFile object which contains the data set corresponding
    % to file 'y', as well as the notes and file name.
    %
    %   A = AxisFile('filename.raw') - loads file header information
    %
    % From here, the command 'z = A.DataSets(1)' stores a copy of the handle
    % to the first "BlockVectorSet" object in the file, which acts as a data
    % map for the user.
    %
    % Becasue ther may be more than one data set in a file, extra tools are
    % provided to get the data you are looking for quickly:
    %
    %   A = AxisFile('filename.raw').RawVoltageData
    %   A = AxisFile('filename.raw').RawContractilityData
    %   A = AxisFile('filename.spike').SpikeData
    %
    % y = z.LoadData() of z, loads specific data regions of the dataset
    % to y without reloading the entire file each time. For example:
    %
    %   a1data = z.LoadData('A1', 11)
    %
    % will load all A1_11 information in the file and store it in a1Data.
    %
    %   y = x.DataSets.LoadData(well, electrode, timespan, dimensions) - loads
    %      channel data into array
    %
    %      dimension 1 ->   by plate, vector with 1 waveform per signal in
    %                       the plate
    %      dimension 3 ->   by well, cell array of vectors 1 waveform per
    %                       signal with size (well rows, well columns)
    %      dimension 5 ->   by electrode, reference electrodes by y{well row,
    %                       well column, electrode column, electrode row}
    %
    % The LoadData() function loads data into instances of the class
    % 'Waveform', where the voltage and time vector data can be accessed via
    % the methods GetTimeVector() and GetVoltageVector(). See Also: Waveform.m
    %
    %   y{wr, wc, ec, er}.GetTimeVector - returns time vector based on start
    %                       time, length of data, and Sampling Frequency
    %                       in units of Seconds
    %   y{wr, wc, ec, er}.GetVoltageVector - returns the voltage vector
    %                       with units of Volts
    %
    % Properties of AxisFile include:
    %
    %   FileName:           Path to file that this instance points to
    %
    %   PrimaryDataType:    The type of the Original / most relevant data
    %                       in this file. See Also: BlockVectorDataType.m
    %
    %   HeaderVersionMajor: Major version number of the loaded file.
    %                       (modern files should be 1)
    %
    %   HeaderVersionMinor: Minor version number of the loaded file.
    %
    %   RecordingName:      RecordingName that was entired in AxIS at the
    %                       Time of recording
    %
    %   Investigator:       Investigator that was entired in AxIS at the
    %                       Time of recording
    %
    %   Description:        Description that was entired in AxIS at the
    %                       Time of recording
    %
    % See Also: BlockVectorSet, Waveform, BlockVectorSet,
    % BlockVectorDataType, Note

    properties (Constant = true, GetAccess = private)
        %The following are contants used in the opening of Axis Files
        MAGIC_WORD      = 'AxionBio';           % Preface to all modern Axis files
        MAGIC_BETA_FILE = 64;                   % Preface to Some legacy Axis files
        EXPECTED_NOTES_LENGTH_FIELD = 600;      % Number used as a validity check in Axis 1.0 file headers

        %Header Size Constants, see documentation for details
        PRIMARY_HEADER_CRCSIZE = 1018;
        SUBHEADER_CRCSIZE = 1016;
        PRIMARY_HEADER_MAXENTRIES = 123;
        SUBHEADER_MAXENTRIES = 126;

        %Header CRC32 calculation constants
        mcCrcPolynomial = hex2dec('edb88320');
        mcCrcSeed = hex2dec('ffffffff');

        mcDescriptionKey = 'Description';
        mcInvestigatorKey = 'Investigator';
        mcRecordingNameKey = 'RecordingName';
        mcAnalogModeKey = 'AnalogMode';
    end

    properties (Constant = true, GetAccess = public)
        % Version of AxIS this script is released with
        AXIS_VERSION='6.0.0.6';
    end

    properties (SetAccess = private, GetAccess = public)
        %Basic File Data
        FileName;
        FileID
        PrimaryDataType

        %Contained File Data
        ChannelArray;
        DataSets;
        Annotations;
        PlateMap;
        StimulationEvents;
        UnlinkedStimulationEvents
        LeapInduction;
        MetaData;
        ViabilityImpedanceEvents;

        %Version Number: Current version is (1.3)
        HeaderVersionMajor
        HeaderVersionMinor
    end

    methods(Static)
        function value = CRC_POLYNOMIAL()
            value = AxisFile.mcCrcPolynomial;
        end
        function value = CRC_SEED()
            value = AxisFile.mcCrcSeed;
        end
    end

    methods
        function this = AxisFile(varargin)
            %AxisFile Opens a new handle to an Axis File
            %  Required arguments:
            %    filename    Pathname of the file to load
            %                Note: Calling with mulitple file names results
            %                in vector of AxisFile objects corresponding to
            %                the input argument file names

            %Empty Constructor
            if(nargin == 0)
                this.FileID =  [];
                this.PrimaryDataType = [];
                this.HeaderVersionMajor = [];
                this.HeaderVersionMinor = [];
                this.FileName = [];
                this.DataSets = [];
                this.Annotations = [];
                this.PlateMap = [];
                this.StimulationEvents = [];
                this.LeapInduction = [];
                this.ViabilityImpedanceEvents = [];
                this.MetaData = [];
                return;
            end

            %Array of files / file names
            if(nargin > 1)
                this(nargin) = AxisFile;
                for i = 1: nargin
                    this(i) = AxisFile(varargin{i});
                end
                return;
            end

            %Just Casting
            if(isa(varargin{1}, 'AxisFile'))
                this = varargin{1};
            end

            %Construct From a path
            fFilename = varargin{1};
            this.FileName = fFilename;
            this.FileID =  fopen(fFilename,'r');
            fEntriesStart = 0;

            this.MetaData = containers.Map('KeyType', 'char', 'ValueType', 'char');

            fSetMap = containers.Map('KeyType', 'int64', 'ValueType', 'any');
            fNotes = Note.empty(0,0);

            if (this.FileID <= 0)
                error(['AxisFile: ' this.FileName ' not found.']);
            end
            % Make sure that this is a format that we understand
            versionOk = false;
            versionWarn = false;

            % Check for the "magic word" sequence
            fMagicRead = fread(this.FileID, length(AxisFile.MAGIC_WORD), '*char').';
            if ~strcmp(AxisFile.MAGIC_WORD, fMagicRead)

                % Magic phrase not found -- check to see if this is an old-style file
                if ~isempty(fMagicRead) && uint8(fMagicRead(1)) == AxisFile.MAGIC_BETA_FILE
                    % This looks like a deprecated beta file
                    warning('AxisFile:versionCheck', ['File ' fFilename ' looks like a deprecated AxIS v0.0 file format, Please Re-record it in Axis to update the header data']);

                    [fType, fData, fChannelMapping, fHeader] = LegacySupport.GenerateRolstonEntries(this.FileID, fFilename((end-3):end));

                    this.DataSets = DataSet.Construct(BlockVectorSet(this, fData, fChannelMapping, fHeader));
                    this.HeaderVersionMajor = 0;
                    this.HeaderVersionMinor = 0;
                    this.PrimaryDataType = fType;

                    return;
                else
                    fclose(this.FileID);
                    error('File format not recognized: %s', fFilename);
                end

            else

                this.PrimaryDataType         = fread(this.FileID, 1, 'uint16=>uint16');
                this.HeaderVersionMajor      = fread(this.FileID, 1, 'uint16=>uint16');
                this.HeaderVersionMinor      = fread(this.FileID, 1, 'uint16=>uint16');
                fNotesStart                  = fread(this.FileID, 1, 'uint64=>uint64');
                fNotesLength                 = fread(this.FileID, 1, 'uint32=>uint32');

                if(fNotesLength ~= AxisFile.EXPECTED_NOTES_LENGTH_FIELD)
                    error('Incorrect legacy notes length field');
                end

                if this.HeaderVersionMajor == 0
                    if this.HeaderVersionMinor == 1
                        versionOk = true;
                    elseif this.HeaderVersionMinor == 2
                        versionOk = true;
                    end

                    fEntriesStart = int64(fNotesStart);
                    fEntryRecords = LegacySupport.GenerateEntries(this.FileID, fEntriesStart);

                elseif this.HeaderVersionMajor == 1
                    versionOk = true;

                    fEntriesStart        = fread(this.FileID, 1, 'int64=>int64');
                    fEntrySlots = fread(this.FileID, AxisFile.PRIMARY_HEADER_MAXENTRIES, 'uint64=>uint64');
                    fEntryRecords = EntryRecord.FromUint64(fEntrySlots);

                    % Check CRC
                    fseek(this.FileID, 0, 'bof');
                    fCRCBytes = fread(this.FileID, AxisFile.PRIMARY_HEADER_CRCSIZE, 'uint8');
                    fReadCRC = fread(this.FileID, 1, 'uint32');
                    fCalcCRC = CRC32(AxisFile.CRC_POLYNOMIAL, AxisFile.CRC_SEED).Compute(fCRCBytes);

                    if(fReadCRC ~= fCalcCRC)
                        error('File header checksum was incorrect: %s', fFilename);
                    end

                    if this.HeaderVersionMinor > 0
                        versionWarn = true;
                    end
                end

            end

            if ~versionOk
                error('Unsupported file version %u.%u', ...
                    this.HeaderVersionMajor, ...
                    this.HeaderVersionMinor);
            end

            % Start Reading Entries
            fseek(this.FileID, fEntriesStart, 'bof');

            fTerminated = false;

            fTagEntries = TagEntry.empty(0);

            this.ChannelArray = [];

            % Load file entries from the header
            while(~fTerminated)
                for entryRecord = fEntryRecords
                    switch(entryRecord.Type)

                        case EntryRecordID.Terminate
                            fTerminated = true;
                            break

                        case EntryRecordID.ChannelArray
                            this.ChannelArray = ChannelArray(entryRecord, this.FileID);

                            if exist('fCurrentBlockVectorSet','var')
                                if(~isa(fCurrentBlockVectorSet.ChannelArray , 'ChannelArray'))
                                    fCurrentBlockVectorSet.SetValue(this.ChannelArray);
                                    fSetMap(int64(fCurrentHeader.FirstBlock)) = fCurrentBlockVectorSet;
                                else
                                    error('AxisFile: Only one ChannelArray per BlockVectorSet');
                                end
                            end
                        case EntryRecordID.BlockVectorHeader
                            fCurrentHeader = BlockVectorHeader(entryRecord, this.FileID);

                            fCurrentBlockVectorSet = BlockVectorSet(this, fCurrentHeader);

                            fKey = int64(fCurrentHeader.FirstBlock);
                            fSetMap(fKey) = fCurrentBlockVectorSet;

                        case EntryRecordID.BlockVectorHeaderExtension
                            if(~isempty(fCurrentBlockVectorSet.HeaderExtension) || ...
                                    isa(fCurrentBlockVectorSet.HeaderExtension, 'BlockVectorHeaderExtension'))
                                error('AxisFile: Only one BlockVectorHeaderExtension per BlockVectorSet');
                            end
                            fCurrentBlockVectorSet.SetValue(BlockVectorHeaderExtension(entryRecord, this.FileID));
                            fSetMap(fCurrentBlockVectorSet.Header.FirstBlock) = fCurrentBlockVectorSet;

                        case EntryRecordID.BlockVectorData
                            fData = BlockVectorData(entryRecord, this.FileID);
                            if(~isempty(fCurrentBlockVectorSet.Data) || ...
                                    isa(fCurrentBlockVectorSet.Data, 'BlockVectorData'))
                                error('AxisFile: Only one BlockVectorData per BlockVectorSet');
                            end
                            fTargetSet = fSetMap(int64(fData.Start));
                            if (~isa(fTargetSet, 'BlockVectorSet'))
                                error('AxisFile: No header to match to data');
                            end
                            fTargetSet.SetValue(fData);
                            fSetMap(fData.Start) = fTargetSet;

                        case EntryRecordID.NotesArray
                            fNotes = [fNotes ; Note.ParseArray(entryRecord, this.FileID)];

                        case EntryRecordID.Tag
                            fTagEntries(end+1) = TagEntry(entryRecord, this.FileID);

                        case EntryRecordID.CombinedBlockVectorHeader
                            % Deserialize CombinedBlockVectorHeaderEntry
                            fCombinedBlockVector = CombinedBlockVectorHeaderEntry.Deserialize(entryRecord, this.FileID);

                            switch(fCombinedBlockVector.DataType)
                                case BlockVectorDataType.NamedContinuousData
                                    fCurrentCombinedBlockVector = ContinuousBlockVectorHeaderEntry.DeserializeFromCombinedBlockVectorHeaderEntry(entryRecord, fCombinedBlockVector, this.FileID);
                                case BlockVectorDataType.Spike_v1
                                    fCurrentCombinedBlockVector = DiscontinuousBlockVectorHeaderEntry.DeserializeFromCombinedBlockVectorHeaderEntry(entryRecord, fCombinedBlockVector, this.FileID);
                                otherwise
                                    warning('Unsupported BlockVectorDataType: %d. Skipping record...', fCombinedBlockVector.DataType);
                            end

                            if exist('fCurrentCombinedBlockVector','var')
                                fCurrentBlockVectorSet = BlockVectorSet(this, fCurrentCombinedBlockVector);

                                % Add ChannelArray to the BlockVectorSet
                                if ~isempty(this.ChannelArray)
                                    fLocalMappings = this.ChannelArray.Channels(arrayfun(@(a)(this.ChannelArray.LookupChannelID(a)),[fCurrentCombinedBlockVector.ChannelIDs{:}]));
                                    fCurrentBlockVectorSet.SetValue(this.ChannelArray.GetNewForChannels(fLocalMappings));
                                end

                                fSetMap(int64(fCurrentCombinedBlockVector.Start)) = fCurrentBlockVectorSet;
                            end

                        otherwise
                            fSkipSpace = double(entryRecord.Length);
                            if(0 ~= fseek(this.FileID, fSkipSpace, 'cof'))
                                error(ferror(this.FileID));
                            end

                    end
                end

                if(~fTerminated)

                    %Check Magic Bytes
                    fMagicRead = fread(this.FileID, length(AxisFile.MAGIC_WORD), '*char').';
                    if ~strcmp(AxisFile.MAGIC_WORD, fMagicRead)
                        error('Bad sub header magic numbers: %s', fFilename);
                    end

                    %Read Entry Records
                    fEntrySlots = fread(this.FileID, AxisFile.SUBHEADER_MAXENTRIES, 'uint64=>uint64');
                    fEntryRecords = EntryRecord.FromUint64(fEntrySlots);

                    %Check CRC of subheader
                    fseek(this.FileID,( -1 * length(AxisFile.MAGIC_WORD)) - (8 * AxisFile.SUBHEADER_MAXENTRIES),'cof');
                    fCRCBytes = fread(this.FileID, AxisFile.SUBHEADER_CRCSIZE, 'uint8');
                    fReadCRC = fread(this.FileID, 1, 'uint32');
                    fCalcCRC = CRC32(AxisFile.CRC_POLYNOMIAL, AxisFile.CRC_SEED).Compute(fCRCBytes);
                    if(fReadCRC ~= fCalcCRC)
                        error('Bad sub header checksum : %s', fFilename);
                    end

                    %skip 4 reserved bytes
                    fseek(this.FileID, 4,'cof');
                end

            end

            fValueSet = fSetMap.values;

            %Record Final Data Sets
            this.DataSets = DataSet.empty(0,length(fSetMap));
            for i = 1 : length(fValueSet)
                this.DataSets(i) = DataSet.Construct(fValueSet{i});
            end

            %Sort Notes
            [~,idx]=sort([fNotes.Revision]);
            fNotes = fNotes(idx);

            %Collect Tags
            fTagMap = containers.Map();
            for fEntryNum = 1:length(fTagEntries)
                fEntry = fTagEntries(fEntryNum);
                fGuid = fEntry.TagGuid;
                if fTagMap.isKey(fGuid)
                    fTag = fTagMap(fGuid);
                else
                    fTag = Tag(fGuid);
                    fTagMap(fGuid) = fTag;
                end
                fTag.AddNode(fEntry);
            end
            this.Annotations = Annotation.empty(0);
            this.PlateMap = WellInformation.empty(0);
            this.StimulationEvents = StimulationEvent.empty(0);
            this.LeapInduction = LeapInductionEvent.empty(0);
            this.ViabilityImpedanceEvents = ViabilityImpedanceEvent.empty(0);

            for fKey = fTagMap.keys
                ffKey = fKey{1};
                fTag = fTagMap(ffKey).Promote(this.FileID);
                if isa(fTag, 'Annotation')
                    this.Annotations(end+1) = fTag;
                elseif isa(fTag, 'WellInformation')
                    this.PlateMap(end+1) = fTag;
                elseif isa(fTag, 'StimulationEvent')
                    this.StimulationEvents(end+1) = fTag;
                elseif isa(fTag, 'LeapInductionEvent')
                    this.LeapInduction(end+1) = fTag;
                elseif isa(fTag, 'ViabilityImpedanceEvent')
                    this.ViabilityImpedanceEvents(end+1) = fTag;
                elseif isa(fTag, 'KeyValuePairTag')
                    this.MetaData(fTag.Key) = fTag.Value;
                end
                fTagMap(ffKey) = fTag;
            end

            %Upgrade notes to the string diconarty feilds, if needed
            if(this.MetaData.length == 0 && ~isempty(fNotes))
                this.MetaData(AxisFile.mcRecordingNameKey) = fNotes.RecordingName;
                this.MetaData(AxisFile.mcInvestigatorKey) = fNotes.Investigator;
                this.MetaData(AxisFile.mcDescriptionKey) = fNotes.Description;
            end

            if(isvector(this.StimulationEvents))
                fValid = this.StimulationEvents.HasValidTags();
                this.UnlinkedStimulationEvents = this.StimulationEvents(~fValid);
                this.StimulationEvents = this.StimulationEvents(fValid);
            elseif(~this.StimulationEvents.HasValidTags())
                this.UnlinkedStimulationEvents = this.StimulationEvents;
                this.StimulationEvents = [];
            end
            
            if(~isempty(this.UnlinkedStimulationEvents))
                warning('%i Stimulation events were missing metadata', length(this.UnlinkedStimulationEvents))
            end
            
            for fStimEvent = this.StimulationEvents
                fStimEvent.Link(fTagMap);
            end

            this.Annotations = this.Annotations';
            this.PlateMap = this.PlateMap';
            this.StimulationEvents = this.StimulationEvents';
            this.UnlinkedStimulationEvents = this.UnlinkedStimulationEvents';
             %There Should only be LeapInduction tag, we follow the same practice as AxIS to limit it to 1,
             %We use the tage with the most recent CreationDate, which shoudl be the youngest tag...
            this.LeapInduction = this.LeapInduction';
            if(length(this.LeapInduction) > 1)
                dates = arrayfun(@(a)(a.CreationDate.ToDateTimeNumber), this.LeapInduction);
                [~,maxind] = max(dates);
                this.LeapInduction = this.LeapInduction(maxind);
            end
            this.ViabilityImpedanceEvents = this.ViabilityImpedanceEvents';
        end

        function delete(this)
            %DELETE is the destructor for the class, ensures that the file
            %stream is closed as the file reference is cleared from the
            %workspace

            if ~isempty(this.FileID)
                fclose(this.FileID);
            end
        end
    end

    methods(Access = protected)
        function propgrp = getPropertyGroups(obj)
            if ~isscalar(obj)
                propgrp = getPropertyGroups@matlab.mixin.CustomDisplay(obj);
            else
                propList = struct(...
                    'FileName',obj.FileName);
                %Only display tihings that are not empty
                if(~isempty(obj.RecordingName))
                    propList.RecordingName = obj.RecordingName;
                end
                if(~isempty(obj.Investigator))
                    propList.Investigator = obj.Investigator;
                end
                if(~isempty(obj.Description))
                    propList.Description = obj.Description;
                end
                if(~isempty(obj.AnalogMode))
                    propList.AnalogMode = obj.AnalogMode;
                end
                if(~isempty(obj.Annotations))
                    propList.Annotations = obj.Annotations;
                end
                if(~isempty(obj.PlateMap))
                    propList.PlateMap = obj.PlateMap;
                end
                if(~isempty(obj.StimulationEvents))
                    propList.StimulationEvents = obj.StimulationEvents;
                end
                if(~isempty(obj.UnlinkedStimulationEvents))
                    propList.UnlinkedStimulationEvents = obj.UnlinkedStimulationEvents;
                end
                if(~isempty(obj.LeapInduction))
                    propList.LeapInduction = obj.LeapInduction;
                end
                if(~isempty(obj.ViabilityImpedanceEvents))
                    propList.ViabilityImpedanceEvents = obj.ViabilityImpedanceEvents;
                end
                if(~isempty(obj.RawVoltageData))
                    propList.RawVoltageData = obj.RawVoltageData;
                end
                if(~isempty(obj.BroadbandHighFrequency))
                    propList.BroadbandHighFrequency = obj.BroadbandHighFrequency;
                end
                if(~isempty(obj.BroadbandLowFrequency))
                    propList.BroadbandLowFrequency = obj.BroadbandLowFrequency;
                end
                if(~isempty(obj.RawContractilityData))
                    propList.RawContractilityData = obj.RawContractilityData;
                end
                if(~isempty(obj.SpikeData))
                    propList.SpikeData = obj.SpikeData;
                end
                if(~isempty(obj.LfpData))
                    propList.LfpData = obj.LfpData;
                end
                propgrp = matlab.mixin.util.PropertyGroup(propList);
            end
        end
    end

    % Data Look-up
    methods
        function dataSet = RawVoltageData(this)
            fSearch = arrayfun(@(a)(a.IsRawVoltage()), this.DataSets, 'UniformOutput', false);
            fSearch = [fSearch{:}];
            dataSet = this.DataSets(fSearch);
        end
        
        function dataSet = BroadbandHighFrequency(this)
            fSearch = arrayfun(@(a)(a.IsBbpHigh()), this.DataSets, 'UniformOutput', false);
            fSearch = [fSearch{:}];
            dataSet = this.DataSets(fSearch);
        end

        function dataSet = BroadbandLowFrequency(this)
            fSearch = arrayfun(@(a)(a.IsBbpLow()), this.DataSets, 'UniformOutput', false);
            fSearch = [fSearch{:}];
            dataSet = this.DataSets(fSearch);
        end

        function dataSet = RawContractilityData(this)
            fSearch = arrayfun(@(a)(a.IsRawContractility()), this.DataSets, 'UniformOutput', false);
            fSearch = [fSearch{:}];
            dataSet = this.DataSets(fSearch);
        end

        function dataSet = SpikeData(this)
            fSearch = arrayfun(@(a)(a.IsSpikes()), this.DataSets, 'UniformOutput', false);
            fSearch = [fSearch{:}];
            dataSet = this.DataSets(fSearch);
        end
        
        function dataSet = LfpData(this)
            fSearch = arrayfun(@(a)(a.IsLfp()), this.DataSets, 'UniformOutput', false);
            fSearch = [fSearch{:}];
            dataSet = this.DataSets(fSearch);
        end
    end



    % Non-Displayed, but accessable values
    methods
        function value = RecordingName(this)
            if(this.MetaData.isKey(AxisFile.mcRecordingNameKey))
                value = this.MetaData(AxisFile.mcRecordingNameKey);
            else
                value = [];
            end
        end

        function value = Investigator(this)
            if(this.MetaData.isKey(AxisFile.mcInvestigatorKey))
                value = this.MetaData(AxisFile.mcInvestigatorKey);
            else
                value = [];
            end
        end

        function value = Description(this)
            if(this.MetaData.isKey(AxisFile.mcDescriptionKey))
                value = this.MetaData(AxisFile.mcDescriptionKey);
            else
                value = [];
            end
        end

        function value = AnalogMode(this)
            if(this.MetaData.isKey(AxisFile.mcAnalogModeKey))
                value = this.MetaData(AxisFile.mcAnalogModeKey);
            else
                value = [];
            end
        end
    end
end



