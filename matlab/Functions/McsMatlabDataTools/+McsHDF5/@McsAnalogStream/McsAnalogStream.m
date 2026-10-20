classdef McsAnalogStream < McsHDF5.McsStream
% Holds the contents of an AnalogStream. 
%
% Important fields:
%   ChannelData         -   (channels x samples) array of the sampled data.
%                           Samples are given in units of 10 ^ Info.Exponent 
%                           [Info.Unit]
%
%   ChannelDataTimeStamps - (1 x samples) vector of time stamps given in
%                           microseconds.
%
% The other fields and the Info field provide general information about the
% analog stream.
%
% (c) 2016 by Multi Channel Systems MCS GmbH

    properties (SetAccess = private)
        ChannelData = []; % (channels x samples) Data matrix
        ChannelDataTimeStamps = int64([]); % (1 x samples) Vector of time stamps in microseconds
        DataDimensions = 'channels x samples'; % (string) The data dimensions
        
        % DataUnit - (1 x channels) Cell array with the unit of each sample (e.g. 'nV'). 
        % 'ADC', if the data is not yet converted to voltages.
        DataUnit = {};
        DataType % (string) The data type, e.g. 'double', 'single' or 'raw'
        TimeStampDataType % (string) The type of the time stamps, 'double' or 'int64'
    end
    
    properties (Access = private)
        ChannelDataSets = {};
        StructInfo
    end
    
    methods
        
        function str = McsAnalogStream(filename, strStruct, source, varargin)
        % Constructs a McsAnalogStream object
        %
        % function str = McsAnalogStream(filename, strStruct, source)    
        % function str = McsAnalogStream(filename, strStruct, source, cfg)
        %
        % Reads the meta-information and the time stamps, not the analog
        % data. Reading the analog data is done the first time that
        % ChannelData is accessed.
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
        %               'double' is useful for older Matlab version without
        %               int64 arithmetic.
            if exist('h5info')
                mode = 'h5';
            else
                mode = 'hdf5';
            end
            
            cfg = McsHDF5.McsStream.checkStreamParameter(varargin{:});
            str = str@McsHDF5.McsStream(filename,strStruct,'Channel',source);
            str.StructInfo = strStruct;
            
            if strcmp(source, 'DataManager')
                str = ConstructFromDataManager(str, strStruct, mode, filename, cfg);
            elseif strcmp(source, 'CMOS-MEA')
                str = ConstructFromCMOSMea(str, strStruct, mode, cfg);
            else
                error('Unknown source!');
            end
        end
        
        function data = get.ChannelData(str)
        % Accessor function for the ChannelData field.
        %
        % function data = get.ChannelData(str)
        %
        % Will read the channel data from file the first time this field is
        % accessed.
            if exist('h5info')
                mode = 'h5';
            else
                mode = 'hdf5';
            end
            
            if ~str.Internal && ~str.DataLoaded
                fprintf('Reading analog data...')
                str = LoadDataFromFile(str, mode);
                fprintf('done!\n');
                str.DataLoaded = true;
                if ~strcmp(str.DataType,'raw')
                    for ch = 1:length(str.Info.Unit)
                        [ignore,unit_prefix] = McsHDF5.ExponentToUnit(str.Info.Exponent(ch),0);
                        if strcmp(mode,'h5')
                            str.DataUnit{ch} = [unit_prefix str.Info.Unit{ch}];
                        else
                            str.DataUnit{ch} = [unit_prefix str.Info.Unit(ch)];
                        end
                    end
                    convert_from_raw(str);    
                else
                    for ch = 1:length(str.Info.Unit)
                        str.DataUnit{ch} = 'ADC';
                    end
                end
            end
            data = str.ChannelData;
        end
        
        function s = disp(str)
            s = 'McsAnalogStream object\n\n';
            s = [s 'Properties:\n'];
            s = [s '\tStream Label:\t\t\t ' strtrim(str.Label) '\n'];
            s = [s '\tNumber of Channels:\t\t ' num2str(length(str.Info.ChannelID)) '\n'];
            s = [s '\tTime Range:\t\t\t\t ' num2str(McsHDF5.TickToSec(str.ChannelDataTimeStamps(1))) ...
                ' - ' num2str(McsHDF5.TickToSec(str.ChannelDataTimeStamps(end))) ' s\n'];
            s = [s '\tData Loaded:\t\t\t '];
            if str.DataLoaded
                s = [s 'true\n'];
            else
                s = [s 'false\n'];
            end
            s = [s '\n'];
            
            s = [s 'Available Fields:\n'];
            s = [s '\tChannelData:\t\t\t [' num2str(length(str.Info.ChannelID)) 'x' num2str(length(str.ChannelDataTimeStamps))];
            if str.DataLoaded
                s = [s ' ' class(str.ChannelData) ']'];
            else
                s = [s ', not loaded]'];
            end
            s = [s '\n'];
            s = [s '\tChannelDataTimeStamps:\t [' num2str(size(str.ChannelDataTimeStamps,1))...
                'x' num2str(size(str.ChannelDataTimeStamps,2)) ' ' class(str.ChannelDataTimeStamps) ']'];
            s = [s '\n'];
            s = [s '\tDataDimensions:\t\t\t ' str.DataDimensions];
            s = [s '\n'];
            s = [s '\tDataUnit:\t\t\t\t {' num2str(size(str.DataUnit,1)) 'x' num2str(size(str.DataUnit,2)) ' cell}'];
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
            s = [s '\n\n'];
            fprintf(s);
        end
        
        function data = getConvertedData(str,cfg)
        % Returns the converted data
        %
        % function data = getConvertedData(str,cfg)
        %
        % If the DataType is 'raw', this will convert the data to
        % meaningful units and return it, but not change the internal
        % ChannelData field. If the DataType is 'single' or 'double' this
        % will either return the ChannelData field (if cfg.dataType equals
        % the DataType) or cast the ChannelData entry to the requested data
        % type in cfg.dataType.
        %
        % Input:
        %   cfg     -   A configuration structure. Can contain the field
        %               'dataType' which describes the requested data type.
        %               The default is 'double'. cfg.dataType has to be one
        %               of the built-in types.
        %
        % Output:
        %   data    -   The ChannelData converted to cfg.dataType. If the
        %               original DataType is 'raw', this includes the
        %               conversion from ADC units to units of 10 ^
        %               Info.Exponent [Info.Unit]
            
            cfg = McsHDF5.checkParameter(cfg, 'dataType', 'double');
            
            if ~strcmp(str.DataType,'raw')
                if ~strcmp(str.DataType,cfg.dataType)
                    data = cast(str.ChannelData,cfg.dataType);
                else
                    data = str.ChannelData;
                end
            else
                conv_factor = cast(str.Info.ConversionFactor,cfg.dataType);
                data = cast(str.ChannelData,cfg.dataType);
                if strcmp(str.SourceType, 'DataManager')
                    adzero = cast(str.Info.ADZero,cfg.dataType);
                    data = bsxfun(@minus,data,adzero);
                end
                data = bsxfun(@times,data,conv_factor);
            end
        end
       
        function out_str = readPartialChannelData(str,cfg)
        % Read a segment from the stream.
        %
        % function out_str = readPartialChannelData(str,cfg)
        %
        % Reads a segment of the channel data from the HDF5 file and
        % returns the McsAnalogStream object containing only the specific
        % segment. Useful, if the data has not yet been read from the file
        % and the user is only interested in a specific segment.
        %
        % Input:
        %   str       -   A McsAnalogStream object
        %
        %   cfg       -   Either empty (for default parameters) or a
        %                 structure with (some of) the following fields:
        %                 'window': If empty, the whole time interval, otherwise
        %                   [start end] in seconds
        %                 'channel': channel range, given as [first last]
        %                 channel index. If empty, all channels are used.
        %
        % Output:
        %   out_str     -   The McsAnalogStream with the requested data
        %                   segment
            if exist('h5info')
                mode = 'h5';
            else
                mode = 'hdf5';
            end
            ts = str.ChannelDataTimeStamps;
            defaultChannel = 1:length(str.Info.ChannelID);
            defaultWindow = 1:length(ts);
            
            [cfg, isDefault] = McsHDF5.checkParameter(cfg, 'channel', defaultChannel);
            if ~isDefault
                cfg.channel = cfg.channel(1):cfg.channel(2);
                if any(cfg.channel < 1 | cfg.channel > length(defaultChannel))
                    cfg.channel = cfg.channel(cfg.channel >= 1 & cfg.channel <= length(defaultChannel));
                    if isempty(cfg.channel)
                        error('No channel indices found!');
                    else
                        warning(['Using only channel indices between ' num2str(cfg.channel(1)) ' and ' num2str(cfg.channel(end)) '!']);
                    end
                end
            end
            
            [cfg, isDefault] = McsHDF5.checkParameter(cfg, 'window', defaultWindow);
            if ~isDefault
                t = find(ts >= McsHDF5.SecToTick(cfg.window(1)) & ts <= McsHDF5.SecToTick(cfg.window(2)));
                if McsHDF5.TickToSec(ts(t(1)) - str.Info.Tick(1)) > cfg.window(1) || ...
                        McsHDF5.TickToSec(ts(t(end)) + str.Info.Tick(1)) < cfg.window(2)
                    warning(['Using only time range between ' num2str(McsHDF5.TickToSec(ts(t(1)))) ...
                        ' and ' num2str(McsHDF5.TickToSec(ts(t(end)))) ' s!']);
                elseif isempty(t)
                    error('No time range found!');
                end
                cfg.window = t;
            end
            
            tmpStruct = str.StructInfo;
            tmpcfg = [];
            tmpcfg.dataType = str.DataType;
            tmpcfg.timeStampDataType = str.TimeStampDataType;
            out_str = McsHDF5.McsAnalogStream(str.FileName, tmpStruct, str.SourceType, tmpcfg);
            
            out_str.Internal = true;
            if str.DataLoaded
                out_str.ChannelData = str.ChannelData(cfg.channel, cfg.window);
            else
                % read data segment
                fprintf('Reading partial analog data...');
                out_str = LoadPartialDataFromFile(cfg, str, out_str);
                fprintf('done!\n');
            end
            out_str.ChannelDataTimeStamps = ts(cfg.window);
            out_str.DataLoaded = true;
            out_str.DataType = str.DataType;
            out_str.TimeStampDataType = str.TimeStampDataType;
            out_str.copyFields(str, cfg.channel);
            if ~strcmp(str.DataType,'raw') && ~str.DataLoaded
                convert_from_raw(out_str);
            end
            out_str.Internal = false;
            if ~isempty(str.DataUnit)
                out_str.DataUnit = repmat({str.DataUnit},length(cfg.channel),1);
            elseif strcmp(out_str.DataType,'raw')
                out_str.DataUnit = repmat({'ADC'},length(cfg.channel),1);
            else
                [ignore,unit_prefix] = McsHDF5.ExponentToUnit(out_str.Info.Exponent(1),0);
                out_str.DataUnit = repmat({[unit_prefix out_str.Info.Unit{1}]},length(cfg.channel),1);
            end
        end
    end
    
    methods (Access = private)
        function convert_from_raw(str)
            % Converts the raw channel data to useful units.
            %
            % function out = convert_from_raw(str)
            %
            % This is performed directly after the data is loaded from the
            % hdf5 file.
            conv_factor = cast(str.Info.ConversionFactor,str.DataType);
            try
                str.ChannelData = cast(str.ChannelData,str.DataType);
            catch ME
                errorMessage = sprintf('Error in function convert_from_raw().\n\nError Message:\n%s', ME.message);
                uiwait(errordlg(errorMessage));
                return
            end
            if strcmp(str.SourceType, 'DataManager')
                adzero = cast(str.Info.ADZero,str.DataType);
                str.ChannelData = bsxfun(@minus,str.ChannelData,adzero);
            end
            str.ChannelData = bsxfun(@times,str.ChannelData,conv_factor);
        end 
        
        function str = ConstructFromDataManager(str, strStruct, mode, filename, cfg)

            if strcmp(mode,'h5')
                timestamps = h5read(filename, [strStruct.Name '/ChannelDataTimeStamps']);
            else
                timestamps = hdf5read(filename, [strStruct.Name '/ChannelDataTimeStamps']);
            end
            if size(timestamps,1) ~= 3
                timestamps = timestamps';
            end
            
            if strcmpi(cfg.timeStampDataType,'int64') 
                timestamps = bsxfun(@plus,timestamps,int64([0 1 1])');
                for tsi = 1:size(timestamps,2)
                    str.ChannelDataTimeStamps(timestamps(2,tsi):timestamps(3,tsi)) = ...
                        (int64(0:numel(timestamps(2,tsi):timestamps(3,tsi))-1) .* ...
                        str.Info.Tick(1)) + timestamps(1,tsi);
                end
                str.TimeStampDataType = 'int64';
            else
                type = cfg.timeStampDataType;
                if ~strcmp(type,'double')
                    error('Only int64 and double are supported for timeStampDataType!');
                end
                str.ChannelDataTimeStamps = cast([],type);
                timestamps = bsxfun(@plus,double(timestamps),[0 1 1]');
                for tsi = 1:size(timestamps,2)
                    str.ChannelDataTimeStamps(timestamps(2,tsi):timestamps(3,tsi)) = ...
                        ((0:numel(timestamps(2,tsi):timestamps(3,tsi))-1) .* ...
                        cast(str.Info.Tick(1),type)) + timestamps(1,tsi);
                end
                str.TimeStampDataType = type;
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
            
            grp = [];
            grp.From = str.ChannelDataTimeStamps(1);
            grp.To = str.ChannelDataTimeStamps(end) + cast(str.Info.Tick(1),cfg.timeStampDataType);
            grp.Name = [strStruct.Name '/ChannelData'];
            str.ChannelDataSets{1} = grp;
        end
        
        function str = ConstructFromCMOSMea(str, strStruct, mode, cfg)

            for didx = 1:length(strStruct.Datasets)
                dataset = strStruct.Datasets(didx);
                typeID = McsHDF5.McsH5Helper.GetFromAttributes(dataset, 'ID.TypeID', mode);
                if strcmpi(typeID, '5efe7932-dcfe-49ff-ba53-25accff5d622')
                    from = McsHDF5.McsH5Helper.GetFromAttributes(dataset, 'From', mode);
                    to = McsHDF5.McsH5Helper.GetFromAttributes(dataset, 'To', mode);
                    tick = str.Info.Tick(1);
                    
                    if strcmpi(cfg.timeStampDataType,'int64') 
                        timeStamps = from:tick:(to - 1);
                        str.ChannelDataTimeStamps = [str.ChannelDataTimeStamps cast(timeStamps, 'int64')];
                        str.TimeStampDataType = 'int64';
                    else
                        timeStamps = double(from):double(tick):(double(to) - 1);
                        type = cfg.timeStampDataType;
                        if ~strcmp(type,'double')
                            error('Only int64 and double are supported for timeStampDataType!');
                        end
                        str.ChannelDataTimeStamps = cast([],type);
                        str.ChannelDataTimeStamps = [str.ChannelDataTimeStamps cast(timeStamps, type)];
                        str.TimeStampDataType = type;
                    end
                    grp = [];
                    grp.From = from;
                    grp.To = to;
                    if strcmp(mode, 'h5')
                        grp.Name = [strStruct.Name '/' dataset.Name];
                    else
                        grp.Name = dataset.Name;
                    end
                    str.ChannelDataSets = [str.ChannelDataSets, {grp}];
                end
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
            str.Label = McsHDF5.McsH5Helper.GetFromAttributes(strStruct, 'ID.Instance', mode);
            str.DataSubType = McsHDF5.McsH5Helper.GetFromAttributes(strStruct, 'SubType', mode);
        end
        
        function str = LoadDataFromFile(str, mode)
            if strcmp(str.SourceType, 'DataManager')
                if strcmp(mode,'h5')
                    str.ChannelData = h5read(str.FileName, [str.StructName '/ChannelData'])';
                else
                    str.ChannelData = hdf5read(str.FileName, [str.StructName '/ChannelData'])';
                end
            elseif strcmp(str.SourceType, 'CMOS-MEA')
                oldInternal = str.Internal;
                str.Internal = true;
                for gidx = 1:length(str.ChannelDataSets)
                    dataset = str.ChannelDataSets{gidx};
                    if ~isempty(strfind(dataset.Name,'ChannelData'))
                        if strcmp(mode,'h5')
                            data = h5read(str.FileName, dataset.Name)';
                        else
                            data = hdf5read(str.FileName, dataset.Name)';
                        end
                        str.ChannelData = [str.ChannelData data];
                    end
                end
                str.Internal = oldInternal;
            end
        end
        
        function out_str = LoadPartialDataFromFile(cfg, str, out_str)

            fid = H5F.open(str.FileName, 'H5F_ACC_RDONLY', []);
            if strcmp(str.SourceType, 'DataManager')
                gid = H5G.open(fid,str.StructName);
                did = H5D.open(gid,'ChannelData');
                dims = [length(cfg.channel) length(cfg.window)];
                offset = [cfg.channel(1)-1 cfg.window(1)-1];
                mem_space_id = H5S.create_simple(2,dims,[]);
                file_space_id = H5D.get_space(did);
                H5S.select_hyperslab(file_space_id,'H5S_SELECT_SET',offset,[1 1],[1 1],dims);

                out_str.ChannelData = H5D.read(did,'H5ML_DEFAULT',mem_space_id,file_space_id,'H5P_DEFAULT')';
                
                H5D.close(did);
                H5G.close(gid); 
            elseif strcmp(str.SourceType, 'CMOS-MEA')
                from = (cfg.window(1)-1) * str.Info.Tick(1);
                to = from + length(cfg.window) * str.Info.Tick(1);
                for gidx = 1:length(str.ChannelDataSets)
                    set = str.ChannelDataSets{gidx};
                    if strcmp(str.TimeStampDataType, 'int64')
                        setFrom = set.From;
                        setTo = set.To;
                    else
                        setFrom = double(set.From);
                        setTo = double(set.To);
                    end
                    if setFrom < to && setTo > from
                        startOffset = (from - setFrom) / str.Info.Tick(1);
                        startOffset = max(0, startOffset);
                        count = (min(setTo, to) - max(setFrom, from)) / str.Info.Tick(1);
                        if count > 0
                            did = H5D.open(fid, set.Name);
                            dims = double([length(cfg.channel) count]);
                            offset = double([cfg.channel(1)-1 startOffset]);
                            mem_space_id = H5S.create_simple(2,dims,[]);
                            file_space_id = H5D.get_space(did);
                            H5S.select_hyperslab(file_space_id,'H5S_SELECT_SET',offset,[1 1],[1 1],dims);
                            
                            data = H5D.read(did,'H5ML_DEFAULT',mem_space_id,file_space_id,'H5P_DEFAULT')';
                            out_str.ChannelData = [out_str.ChannelData data];
                            H5D.close(did);
                        end
                    end
                end
            end
            H5F.close(fid);
        end
    end
end