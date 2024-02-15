classdef McsCmosSpikeStream < McsHDF5.McsStream
% Holds the contents of a Cmos spike stream object
%
% Important fields:
%   SpikeData       -   (struct) Contains fields SensorID and Timestamp. If
%                       cutouts are present, it will also have a field
%                       Cutout. SensorID and Timestamp are vectors with one
%                       entry per spike. Cutout is a (samples x spikes)
%                       matrix, where 'samples' is the number of samples in
%                       the cutout
%
%   Settings        -   (struct) Contains settings datasets if any are 
%                       present in the file. Each settings dataset is
%                       represented as a field in the Settings struct
%
%   Info            -   (struct) Contains meta information
%
%   The other attributes provide information about the data types and the
%   data dimensions.
%
% (c) 2017 by Multi Channel Systems MCS GmbH

    properties (SetAccess = private)
        SpikeData = []; % (struct) Has fields SensorID, Timestamp and (optional) Cutout
        DataDimensions = 'SensorID: spikes x 1, Timestamp: spikes x 1, Cutout: spikes x samples';
        DataUnit % (string) The data unit for the cutout data
        DataType % (string) The data type for the cutout data, e.g. 'double' or 'single' or 'raw'
        TimeStampDataType % (string) The type of the time stamps, 'double' or 'int64'
        Settings = []; % (struct) Contains settings datasets, each as a field
    end
    
    methods
        function str = McsCmosSpikeStream(filename, strStruct, varargin)
        % Constructs a McsCmosSpikeStream object that holds spike data
        %
        % function str = McsCmosSpikeStream(filename, strStruct)
        % function str = McsCmosSpikeStream(filename, strStruct, cfg)
        %
        % Reads the meta information but does not read the spike data. This
        % is done the first time that the spike data is accessed.
        %
        % Optional input:
        %   cfg     -   configuration structure, contains one or more of
        %               the following fields:
        %               'dataType': The type of the data, can be one of
        %               'double' (default), 'single' or 'raw'. For 'double'
        %               and 'single' the data is converted to meaningful
        %               units, while for 'raw' no conversion is done and
        %               the data is kept in ADC units. This uses less
        %               memory than the conversion to double, but you might
        %               have to convert the data prior to analysis, for
        %               example by using the getConvertedData function.
        %               'timeStampDataType': The type of the time stamps,
        %               can be either 'int64' (default) or 'double'. Using
        %               'double' is useful for older Matlab versions without
        %               int64 arithmetic.          
            if exist('h5info')
                mode = 'h5';
            else
                mode = 'hdf5';
            end
            
            cfg = McsHDF5.McsStream.checkStreamParameter(varargin{:});
            str = str@McsHDF5.McsStream(filename,strStruct,'Spike','CMOS-MEA');
            
            if strcmpi(cfg.timeStampDataType,'int64')
                str.TimeStampDataType = 'int64';
            else
                type = cfg.timeStampDataType;
                if ~strcmp(type,'double')
                    error('Only int64 and double are supported for timeStampDataType!');
                end
                str.TimeStampDataType = type;
            end
            
            str.Label = McsHDF5.McsH5Helper.GetFromAttributes(strStruct, 'ID.Instance', mode);
            str.DataSubType = McsHDF5.McsH5Helper.GetFromAttributes(strStruct, 'SubType', mode);
            if isfield(cfg, 'From')
                str.Info.From = cfg.From;
            end
            if isfield(cfg, 'To')
                str.Info.To = cfg.To;
            end
            
            if strcmpi(cfg.dataType,'double')
                str.DataType = 'double';
            else
                type = cfg.dataType;
                if ~strcmpi(type,'double') && ~strcmpi(type,'single') && ~strcmpi(type,'raw')
                    error('Only double, single and raw are allowed as data types!');
                end
                str.DataType = cfg.dataType;
            end
            
            str.Settings = McsHDF5.McsCmosSpikeStream.ReadSettingsDatasets(filename, strStruct, mode);
        end
        
        function data = get.SpikeData(str)
        % Accessor function for the SpikeData field
        %
        % function data = get.SpikeData(str)
        %
        % Reads the spike data from the file the first time that the
        % SpikeData field is accessed.
            if exist('h5info')
                mode = 'h5';
            else
                mode = 'hdf5';
            end
            
            if ~str.Internal && ~str.DataLoaded
                fprintf('Reading spike data...')
                try 
                    spikeData = McsHDF5.McsH5Helper.ReadCompoundDataset(str.FileName, [str.StructName '/SpikeData'], mode);
                    fn = fieldnames(spikeData);
                    numCutout = sum(cellfun(@(x)(~isempty(regexp(x, 'x\d+', 'once'))), fn));
                    cutouts = zeros(numCutout, length(spikeData.SensorID));
                    for ni = 1:numCutout
                        cutouts(ni,:) = spikeData.(['x' num2str(ni)]);
                    end
                    str.SpikeData.SensorID = spikeData.SensorID;
                    str.SpikeData.TimeStamp = spikeData.TimeStamp;
                    if numCutout > 0
                        if strcmpi(str.DataType, 'single')
                            str.SpikeData.Cutout = cast(cutouts', str.DataType);
                        else
                            str.SpikeData.Cutout = cutouts';
                        end
                        [ignore,unit_prefix] = McsHDF5.ExponentToUnit(str.Info.Exponent,0);
                        str.DataUnit = [unit_prefix str.Info.Unit{1}];
                        str.DataUnit = replace(str.DataUnit, '\mu', 'u');
                    end
                    if ~strcmp(str.TimeStampDataType, 'int64')
                        str.SpikeData.TimeStamp = cast(str.SpikeData.TimeStamp, str.TimeStampDataType);
                    end
                end
                fprintf('done!\n');
                str.DataLoaded = true;
            end
            data = str.SpikeData;
        end
        
        function s = disp(str)
            s = 'McsCmosSpikeStream object\n\n';
            s = [s 'Properties:\n'];
            s = [s '\tStream Label:\t\t\t ' strtrim(str.Label) '\n'];
            s = [s '\tStream Data Type:\t\t ' str.DataSubType '\n'];
            s = [s '\tSpikes Loaded:\t\t\t '];
            if str.DataLoaded
                s = [s 'true\n'];
            else
                s = [s 'false\n'];
            end
            s = [s '\n'];
            
            s = [s 'Available Fields:\n'];
            s = [s '\tSpikeData:\t\t\t\t '];
            if str.DataLoaded
                s = [s 'SensorID: {' num2str(size(str.SpikeData.SensorID,1)) 'x' num2str(size(str.SpikeData.SensorID,2)) ' ' class(str.SpikeData.SensorID) '}'];
                s = [s ', TimeStamp: {' num2str(size(str.SpikeData.TimeStamp,1)) 'x' num2str(size(str.SpikeData.TimeStamp,2)) ' ' class(str.SpikeData.TimeStamp) '}'];
                if isfield(str.SpikeData, 'Cutout')
                    s = [s ', Cutout: {' num2str(size(str.SpikeData.Cutout,1)) 'x' num2str(size(str.SpikeData.Cutout,2)) ' ' class(str.SpikeData.Cutout) '}'];
                end
            else
                s = [s 'not loaded'];
            end
            s = [s '\n'];
            s = [s '\tDataDimensions:\t\t\t ' str.DataDimensions];
            s = [s '\n'];
            s = [s '\tDataUnit:\t\t\t\t ' str.DataUnit];
            s = [s '\n'];
            s = [s '\tDataType:\t\t\t\t ' str.DataType];
            s = [s '\n'];
            s = [s '\tTimeStampDataType:\t\t ' str.TimeStampDataType];
            s = [s '\n'];
            s = [s '\tStreamInfoVersion:\t\t ' num2str(str.StreamInfoVersion)];
            s = [s '\n'];
            s = [s '\tStreamGUID:\t\t\t\t ' str.StreamGUID];
            s = [s '\n'];
            s = [s '\tStreamType:\t\t\t\t ' str.StreamType];
            s = [s '\n'];
            s = [s '\tSourceStreamGUID:\t\t ' str.SourceStreamGUID];
            s = [s '\n'];
            s = [s '\tLabel:\t\t\t\t\t ' str.Label];
            s = [s '\n'];
            s = [s '\tDataSubType:\t\t\t ' str.DataSubType];
            s = [s '\n'];
            s = [s '\tInfo:\t\t\t\t\t [1x1 struct]'];
            s = [s '\n'];
            if ~isempty(str.Settings)
                s = [s '\tSettings:\t\t\t\t [1x1 struct]'];
                s = [s '\n'];
            end
            s = [s '\n'];
            fprintf(s);
        end
    end
    
    methods (Static, Access=private)
        function set = ReadSettingsDatasets(filename, strStruct, mode)
            settingsTypes = {'a95db4a1-d124-4c52-8889-2264fcdb489b',...
                '58c92502-516e-46f6-ac50-44e6dd17a3ff',...
                'ef54ef3d-3619-43aa-87ba-dc5f57f7e861',...
                'f5dc873b-4aed-4a54-8c19-5743908684bb'};
            
            set = McsHDF5.McsH5Helper.ReadDatasetsToStruct(filename, strStruct, mode, settingsTypes);
        end
    end
end