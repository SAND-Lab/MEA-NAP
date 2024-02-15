classdef McsCutoutSegment < McsHDF5.McsSegmentStream
% Holds the contents of a SegmentStream with spike data
%
% Important fields:
%   SegmentData     -   (1xn) cell array, each cell holding either arrays of
%                       (samples x segments) values, where 'samples' is the
%                       time range between Pre- and PostInterval of the
%                       cutout, or arrays of (samples x segments x multisegments)
%                       values. The values are in units of 10 ^ Info.Exponent 
%                       [Info.Unit].
%
%   SegmentDataTimeStamps-(1xn) cell array, each cell holding a (1 x samples)
%                       vector of time stamps for each event. The time
%                       stamps are given in microseconds.
%
%   Info            -   Structure containing information about the
%                       segments. Particularly interesting is the
%                       'SourceChannelIDs' field with a list of channel
%                       IDs. Information about these channels can be found
%                       in the 'SourceInfoChannel' field for their
%                       corresponding IDs. In addition, the 'PreInterval'
%                       and 'PostInterval' fields contain the time interval
%                       before and after the segment defining event in
%                       microseconds.
%
%   SourceInfoChannel-  Structure containing information about the source
%                       channels. It has the same format as the Info
%                       structure of AnalogStreams.
%
%   The other attributes provide information about the data types and the
%   data dimensions.
%
% (c) 2016 by Multi Channel Systems MCS GmbH
    
    properties (SetAccess = private)
        % SegmentData - (cell array) Each cell holds either a 
        % (samples x segments) data matrix, or, in the case of multisegments,
        % a (samples x segments x multisegments) data array.
        SegmentData = {}; 
        SegmentDataTimeStamps = {}; % (cell array) Each cell holds a (1 x samples) vector of timestamps in microseconds
    end
    
    methods
        function str = McsCutoutSegment(filename, strStruct, varargin)
        % Constructs a McsCutoutSegment object for spike cutouts
        %
        % function str = McsCutoutSegment(filename, strStruct)
        % function str = McsCutoutSegment(filename, strStruct, cfg)
        %
        % Reads the time stamps and the meta-information but does not read
        % the cutout data. This is done the first time that the cutout
        % data is accessed.
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
            
            str = str@McsHDF5.McsSegmentStream(filename,strStruct, varargin{:});
            segments = str.Info.SegmentID;
            str.SegmentData = cell(1,length(segments));
            str.SegmentDataTimeStamps = cell(1,length(segments));
            
            if strcmpi(cfg.timeStampDataType,'int64')
                for segi = 1:length(segments)
                    try
                        if strcmp(mode,'h5')
                            str.SegmentDataTimeStamps{segi} = ...
                                h5read(filename,[strStruct.Name '/SegmentData_ts_' num2str(segments(segi))])';
                        else
                            str.SegmentDataTimeStamps{segi} = ...
                                hdf5read(filename,[strStruct.Name '/SegmentData_ts_' num2str(segments(segi))])';
                        end
                    end
                end
                str.TimeStampDataType = 'int64';
            else
                type = cfg.timeStampDataType;
                if ~strcmp(type,'double')
                    error('Only int64 and double are supported for timeStampDataType!');
                end
                for segi = 1:length(segments)
                    try
                        if strcmp(mode,'h5')
                            str.SegmentDataTimeStamps{segi} = ...
                                cast(h5read(filename,[strStruct.Name '/SegmentData_ts_' num2str(segments(segi))]),type)';
                        else
                            str.SegmentDataTimeStamps{segi} = ...
                                cast(hdf5read(filename,[strStruct.Name '/SegmentData_ts_' num2str(segments(segi))]),type)';
                        end
                    end
                end
                str.TimeStampDataType = type;
            end
        end
        
        function data = get.SegmentData(str)
        % Accessor function for the SegmentData field.
        %
        % function data = get.SegmentData(str)
        %
        % Reads the segment data from the file the first time that the
        % SegmentData field is accessed.
            if exist('h5info')
                mode = 'h5';
            else
                mode = 'hdf5';
            end
            
            if ~str.Internal && ~str.DataLoaded
                fprintf('Reading segment data...');
                emptySegments = false(1,length(str.Info.SegmentID));
                for segi = 1:length(str.Info.SegmentID)
                    try
                        if strcmp(mode,'h5')
                            str.SegmentData{segi} = ...
                                h5read(str.FileName,[str.StructName '/SegmentData_' num2str(str.Info.SegmentID(segi))]);  
                        else
                            str.SegmentData{segi} = ...
                                hdf5read(str.FileName,[str.StructName '/SegmentData_' num2str(str.Info.SegmentID(segi))]);  
                        end
                        if numel(size(str.SegmentData{segi})) == 2
                            str.SegmentData{segi} = str.SegmentData{segi}';
                        elseif numel(size(str.SegmentData{segi})) == 3
                           str.SegmentData{segi} = permute(str.SegmentData{segi},[3 2 1]); 
                        end
                    catch
                        emptySegments(segi) = true;
                    end
                end 
                fprintf('done!\n');
                str.DataLoaded = true;
                if ~strcmp(str.DataType,'raw')
                    for segi = 1:length(str.Info.SegmentID)
                        convert_from_raw(str, segi);
                    end
                end
                str.set_data_unit_dimension(emptySegments);
            end
            data = str.SegmentData;
        end
        
        function s = disp(str)
            s = 'McsSegmentStream object\n\n';
            s = [s 'Properties:\n'];
            s = [s '\tStream Label:\t\t\t ' strtrim(str.Label) '\n'];
            s = [s '\tStream Data Type:\t\t ' str.DataSubType '\n'];
            s = [s '\tNumber of Segments:\t\t ' num2str(length(str.Info.SegmentID)) '\n'];
            s = [s '\tData Loaded:\t\t\t '];
            if str.DataLoaded
                s = [s 'true\n'];
            else
                s = [s 'false\n'];
            end
            s = [s '\n'];
            
            s = [s 'Available Fields:\n'];
            s = [s '\tSegmentData:\t\t\t {1x' num2str(length(str.Info.SegmentID))];
            if str.DataLoaded
                s = [s ' ' class(str.SegmentData) '}'];
            else
                s = [s ', not loaded}'];
            end
            s = [s '\n'];
            s = [s '\tSegmentDataTimeStamps:\t {' num2str(size(str.SegmentDataTimeStamps,1))...
                'x' num2str(size(str.SegmentDataTimeStamps,2)) ' cell}'];
            s = [s '\n'];
            s = [s '\tSourceInfoChannel:\t\t [1x1 struct]'];
            s = [s '\n'];
            s = [s '\tDataDimensions:\t\t\t {' num2str(size(str.DataDimensions,1)) 'x' num2str(size(str.DataDimensions,2)) ' cell}'];
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
        
        function data = getConvertedData(seg,idx,cfg)
        % Returns the converted data
        %
        % function data = getConvertedData(str,cfg)
        %
        % If the DataType is 'raw', this will convert the data to
        % meaningful units and return it, but not change the internal
        % SegmentData field. If the DataType is 'single' or 'double' this
        % will either return the SegmentData field (if cfg.dataType equals
        % the DataType) or cast the SegmentData entry to the requested data
        % type in cfg.dataType.
        %
        % Input:
        %   cfg     -   A configuration structure. Can contain the field
        %               'dataType' which describes the requested data type.
        %               The default is 'double'. cfg.dataType has to be one
        %               of the built-in types.
        %
        % Output:
        %   data    -   The SegmentData converted to cfg.dataType. If the
        %               original DataType is 'raw', this includes the
        %               conversion from ADC units to units of 10 ^
        %               Info.Exponent [Info.Unit]
            cfg = McsHDF5.checkParameter(cfg, 'dataType', 'double');
            
            if ~strcmp(seg.DataType,'raw')
                if ~strcmp(seg.DataType,cfg.dataType)
                    data = cast(seg.SegmentData{idx},cfg.dataType);
                else
                    data = seg.SegmentData{idx};
                end
            else
                sourceChan = str2double(seg.Info.SourceChannelIDs{idx});
                if length(sourceChan) == 1
                    chanidx = seg.SourceInfoChannel.ChannelID == sourceChan;
                    conv_factor = cast(seg.SourceInfoChannel.ConversionFactor(chanidx),cfg.dataType);
                    adzero = cast(seg.SourceInfoChannel.ADZero(chanidx),cfg.dataType);
                    data = cast(seg.SegmentData{idx},cfg.dataType);
                    data = bsxfun(@minus,data,adzero);
                    data = bsxfun(@times,data,conv_factor);
                else
                    chanidx = arrayfun(@(x)(find(seg.SourceInfoChannel.ChannelID == x)),sourceChan);
                    conv_factor = cast(seg.SourceInfoChannel.ConversionFactor(chanidx),cfg.dataType);
                    adzero = cast(seg.SourceInfoChannel.ADZero(chanidx),cfg.dataType);
                    data = cast(seg.SegmentData{idx},cfg.dataType);
                    data = bsxfun(@minus,data,adzero);
                    data = bsxfun(@times,data,conv_factor);
                end
            end
        end
        
        function out_str = readPartialSegmentData(str, cfg)
        % Read a subset of the segment entities from the stream.
        %
        % function out_str = readPartialSegmentData(str, cfg)
        %
        % Reads a subset of the segment entities from the HDF5 file and
        % returns the McsSegmentStream object containing only the specific
        % segments. Useful, if the data has not yet been read from the file
        % and the user is only interested in a few segments.
        %
        % Input:
        %   str       -   A McsSegmentStream object
        %
        %   cfg       -   Either empty (for default parameters) or a
        %                 structure with the field:
        %                 'segment': Vector of segment entity indices
        %
        % Output:
        %   out_str     -   The McsSegmentStream with the requested segment
        %                   entities
            if exist('h5info')
                mode = 'h5';
            else
                mode = 'hdf5';
            end
            
            defaultSegment = 1:length(str.Info.SegmentID);
            [cfg, isDefault] = McsHDF5.checkParameter(cfg, 'segment', defaultSegment);
            if ~isDefault
                if any(cfg.segment < 1 | cfg.segment > length(defaultSegment) )
                    cfg.segment = cfg.segment(cfg.segment >= 1 & cfg.segment <= length(defaultSegment));
                    if isempty(cfg.segment)
                        error('No segment indices found!');
                    else
                        warning(['Using only segment indices between ' num2str(cfg.segment(1)) ' and ' num2str(cfg.segment(end)) '!']);
                    end
                end
            end
            
            tmpStruct.Name = str.StructName;
            out_str = McsHDF5.McsCutoutSegment(str.FileName, tmpStruct);
            out_str.Internal = true;
            if str.DataLoaded
                out_str.SegmentData = str.SegmentData(cfg.segment);
                out_str.SegmentDataTimeStamps = str.SegmentDataTimeStamps(cfg.segment);
                emptySegments = cellfun(@isempty, str.SegmentData);
            else
                out_str.SegmentData = out_str.SegmentData(cfg.segment);
                out_str.SegmentDataTimeStamps = out_str.SegmentDataTimeStamps(cfg.segment);
                fprintf('Reading partial segment data...')
                emptySegments = false(1,length(cfg.segment));
                for gidx = 1:length(cfg.segment)
                    try
                        if strcmp(mode,'h5')
                            out_str.SegmentData{gidx} = ...
                                h5read(out_str.FileName,[out_str.StructName '/SegmentData_' num2str(str.Info.SegmentID(cfg.segment(gidx)))]);
                        else
                            out_str.SegmentData{gidx} = ...
                                hdf5read(out_str.FileName,[out_str.StructName '/SegmentData_' num2str(str.Info.SegmentID(cfg.segment(gidx)))]);
                        end
                        if numel(size(out_str.SegmentData{gidx})) == 2
                            out_str.SegmentData{gidx} = out_str.SegmentData{gidx}';
                        elseif numel(size(out_str.SegmentData{gidx})) == 3
                           out_str.SegmentData{gidx} = permute(out_str.SegmentData{gidx},[3 2 1]); 
                        end
                    catch
                        emptySegments(gidx) = true;
                    end
                end
                fprintf('done!\n');
            end
            fns = fieldnames(out_str.SourceInfoChannel);
            for fni = 1:length(fns)
                info = out_str.SourceInfoChannel.(fns{fni});
                out_str.SourceInfoChannel.(fns{fni}) = info(cfg.segment);
            end
            out_str.DataLoaded = true;
            out_str.DataType = str.DataType;
            out_str.TimeStampDataType = str.TimeStampDataType;
            out_str.copyFields(str, cfg.segment);
            if ~strcmp(str.DataType,'raw') && ~str.DataLoaded
                for segi = 1:length(out_str.Info.SegmentID)
                    convert_from_raw(out_str, segi);
                end
            end
            out_str.set_data_unit_dimension(emptySegments);
            out_str.Internal = false;
        end
    end
    
    methods (Access = private)
        function convert_from_raw(seg,idx)
        % Converts the raw segment data to useful units.
        %
        % function out = convert_from_raw(seg,idx)
        %
        % This is done already the first time that the data is loaded
            sourceChan = str2double(seg.Info.SourceChannelIDs{idx});
            if length(sourceChan) == 1
                chanidx = seg.SourceInfoChannel.ChannelID == sourceChan;
                conv_factor = cast(seg.SourceInfoChannel.ConversionFactor(chanidx),seg.DataType);
                adzero = cast(seg.SourceInfoChannel.ADZero(chanidx),seg.DataType);
                seg.SegmentData{idx} = cast(seg.SegmentData{idx},seg.DataType);
                seg.SegmentData{idx} = bsxfun(@minus,seg.SegmentData{idx},adzero);
                seg.SegmentData{idx} = bsxfun(@times,seg.SegmentData{idx},conv_factor);
            else
                chanidx = arrayfun(@(x)(find(seg.SourceInfoChannel.ChannelID == x)),sourceChan);
                conv_factor = cast(seg.SourceInfoChannel.ConversionFactor(chanidx),seg.DataType);
                adzero = cast(seg.SourceInfoChannel.ADZero(chanidx),seg.DataType);
                seg.SegmentData{idx} = cast(seg.SegmentData{idx},seg.DataType);
                seg.SegmentData{idx} = bsxfun(@minus,seg.SegmentData{idx},adzero);
                seg.SegmentData{idx} = bsxfun(@times,seg.SegmentData{idx},conv_factor);
            end
        end
        
        function set_data_unit_dimension(str, emptySegments)    
            for segi = 1:length(str.Info.SegmentID)
                if emptySegments(segi)
                    str.DataUnit{segi} = [];
                    str.DataDimensions{segi} = [];
                    continue
                end
                if strcmp(str.DataType,'raw')
                    sourceChan = str2double(str.Info.SourceChannelIDs{segi});
                    if length(sourceChan) == 1
                        str.DataUnit{segi} = 'ADC';
                        str.DataDimensions{segi} = 'samples x segments';
                    else
                        str.DataUnit{segi} = repmat({'ADC'},length(sourceChan),1);
                        str.DataDimensions{segi} = 'samples x segments x multisegments';
                    end
                else
                    sourceChan = str2double(str.Info.SourceChannelIDs{segi});
                    if length(sourceChan) == 1
                        chanidx = str.SourceInfoChannel.ChannelID == sourceChan;
                        [ignore,unit_prefix] = McsHDF5.ExponentToUnit(str.SourceInfoChannel.Exponent(chanidx),0);
                        str.DataUnit{segi} = [unit_prefix str.SourceInfoChannel.Unit{chanidx}];
                        str.DataDimensions{segi} = 'samples x segments';
                    else
                        chanidx = arrayfun(@(x)(find(str.SourceInfoChannel.ChannelID == x)),sourceChan);
                        str.DataUnit{segi} = [];
                        for ch = chanidx
                            [ignore,unit_prefix] = McsHDF5.ExponentToUnit(str.SourceInfoChannel.Exponent(ch),0);
                            str.DataUnit{segi} = [str.DataUnit{segi} {unit_prefix str.SourceInfoChannel.Unit{ch}}];
                        end
                        str.DataDimensions{segi} = 'samples x segments x multisegments';
                    end

                end
            end
        end
    end
end