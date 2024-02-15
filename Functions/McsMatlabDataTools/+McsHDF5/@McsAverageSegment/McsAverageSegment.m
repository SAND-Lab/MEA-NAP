classdef McsAverageSegment < McsHDF5.McsSegmentStream
% Holds the contents of a SegmentStream with spike data
%
% Important fields:
%   AverageDataMean     -   (1xn) cell array, each cell holding arrays of
%                           (samples x averages) values, where 'samples' is
%                           the time range between Pre- and PostInterval of
%                           the average. The values contain the mean values
%                           of the individual averages.
%
%   AverageDataStdDev   -   (1xn) cell array, each cell holding arrays of
%                           (samples x averages) values, where 'samples' is
%                           the time range between Pre- and PostInterval of
%                           the average. Each value is one standard
%                           deviation of the sample point in the average.
%                           If only a single segment was used to compute
%                           the average, this value is 0.
%
%   AverageDataTimeStamps-  (1xn) cell array, each cell holding a (2 x
%                           averages) matrix of time stamps. These denote
%                           the start and end time stamps of the time range
%                           in which the averaging took place. The first
%                           row contains the start time stamp, the second
%                           row the end time stamp.
%
%   AverageDataCount    -   (1xn) cell array, each cell holding a (1 x
%                           averages) vector of sample counts, i.e. the
%                           number of segments used to compute the average.
%
%   Info                -   Structure containing information about the
%                           segments. Particularly interesting is the
%                           'SourceChannelIDs' field with a list of channel
%                           IDs. Information about these channels can be found
%                           in the 'SourceInfoChannel' field for their
%                           corresponding IDs. In addition, the 'PreInterval'
%                           and 'PostInterval' fields contain the time interval
%                           before and after the segment defining event in
%                           microseconds.
%
%   SourceInfoChannel   -   Structure containing information about the source
%                           channels. It has the same format as the Info
%                           structure of AnalogStreams.
%
%   The other attributes provide information about the data types and the
%   data dimensions.
%
% (c) 2016 by Multi Channel Systems MCS GmbH

    properties (SetAccess = private)
        AverageDataMean = {}; % (cell array) Each cell holds a (samples x averages) data matrix with mean values
        AverageDataStdDev = {}; % (cell array) Each cell holds a (samples x averages) data matrix with standard deviations
        AverageDataTimeStamps = {}; % (cell array) Each cell holds a (2 x averages) matrix with start and stop time stamps in microseconds
        AverageDataCount = {}; % (cell array) Each cell holds a (1 x averages) vector of sample counts
    end
    
    properties (Access = private)
        MeanLoaded = false;
        StdDevLoaded = false;
    end
    
    methods
        function str = McsAverageSegment(filename, strStruct, varargin)
        % Constructs a McsAverageSegment object for averages
        %
        % function str = McsAverageSegment(filename, strStruct)
        % function str = McsAverageSegment(filename, strStruct, cfg)
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
            averages = str.Info.SegmentID;
            str.AverageDataMean = cell(1,length(averages));
            str.AverageDataStdDev = cell(1,length(averages));
            str.AverageDataTimeStamps = cell(1,length(averages));
            str.AverageDataCount = cell(1,length(averages));
            
            if strcmpi(cfg.timeStampDataType,'int64')
                for segi = 1:length(averages)
                    try
                        if strcmp(mode,'h5')
                            vals = h5read(filename,[strStruct.Name '/AverageData_Range_' num2str(averages(segi))])';
                        else
                            vals = hdf5read(filename,[strStruct.Name '/AverageData_Range_' num2str(averages(segi))])';
                        end
                        str.AverageDataTimeStamps{segi} = vals(1:2,:);
                        str.AverageDataCount{segi} = vals(3,:);
                    end
                end
                str.TimeStampDataType = 'int64';
            else
                type = cfg.timeStampDataType;
                if ~strcmp(type,'double')
                    error('Only int64 and double are supported for timeStampDataType!');
                end
                for segi = 1:length(averages)
                    try
                        if strcmp(mode,'h5')
                            vals = h5read(filename,[strStruct.Name '/AverageData_Range_' num2str(averages(segi))])';
                        else
                            vals = hdf5read(filename,[strStruct.Name '/AverageData_Range_' num2str(averages(segi))])';
                        end
                        str.AverageDataTimeStamps{segi} = cast(vals(1:2,:),type);
                        str.AverageDataCount{segi} = vals(3,:);
                    end
                end
                str.TimeStampDataType = type;
            end
        end
        
        function data = get.AverageDataMean(str)
        % Accessor function for the AverageDataMean field.
        %
        % function data = get.AverageDataMean(str)
        %
        % Reads the average mean data from the file the first time that the
        % AverageDataMean field is accessed.
            if ~str.Internal && ~str.MeanLoaded
                fprintf('Reading segment data...');
                emptySegments = false(1,length(str.Info.SegmentID));
                fid = H5F.open(str.FileName, 'H5F_ACC_RDONLY', []);
                gid = H5G.open(fid,str.StructName);
                
                for segi = 1:length(str.Info.SegmentID)
                    try
                        read_mean_data(str, segi, segi, gid);
                    catch
                        str.Internal = false;
                        emptySegments(segi) = true;
                    end
                end 
                H5G.close(gid);
                H5F.close(fid);
                fprintf('done!\n');
                str.MeanLoaded = true;
                if ~str.StdDevLoaded
                    str.set_data_unit_dimension(emptySegments);
                end
            end
            data = str.AverageDataMean;
        end
        
        function data = get.AverageDataStdDev(str)
        % Accessor function for the AverageDataStdDev field.
        %
        % function data = get.AverageDataStdDev(str)
        %
        % Reads the standard deviation data from the file the first time
        % that the AverageDataStdDev field is accessed.
            if ~str.Internal && ~str.StdDevLoaded
                fprintf('Reading segment data...');
                emptySegments = false(1,length(str.Info.SegmentID));
                fid = H5F.open(str.FileName);
                gid = H5G.open(fid,str.StructName);
                
                for segi = 1:length(str.Info.SegmentID)
                    try
                        read_stddev_data(str, segi, segi, gid);
                    catch
                        str.Internal = false;
                        emptySegments(segi) = true;
                    end
                end 
                H5G.close(gid);
                H5F.close(fid);
                fprintf('done!\n');
                str.StdDevLoaded = true;
                if ~str.MeanLoaded
                    str.set_data_unit_dimension(emptySegments);
                end
            end
            data = str.AverageDataStdDev;
        end
        
        function s = disp(str)
            s = 'McsSegmentStream object\n\n';
            s = [s 'Properties:\n'];
            s = [s '\tStream Label:\t\t\t ' strtrim(str.Label) '\n'];
            s = [s '\tStream Data Type:\t\t ' str.DataSubType '\n'];
            s = [s '\tNumber of Averages:\t\t ' num2str(length(str.Info.SegmentID)) '\n'];
            s = [s '\tMean Loaded:\t\t\t '];
            if str.MeanLoaded
                s = [s 'true\n'];
            else
                s = [s 'false\n'];
            end
            s = [s '\tStdDev Loaded:\t\t\t '];
            if str.StdDevLoaded
                s = [s 'true\n'];
            else
                s = [s 'false\n'];
            end
            s = [s '\n'];
            
            s = [s 'Available Fields:\n'];
            s = [s '\tAverageDataMean:\t\t {1x' num2str(length(str.Info.SegmentID))];
            if str.MeanLoaded
                s = [s ' ' class(str.AverageDataMean) '}'];
            else
                s = [s ', not loaded}'];
            end
            s = [s '\n'];
            s = [s '\tAverageDataStdDev:\t\t {1x' num2str(length(str.Info.SegmentID))];
            if str.StdDevLoaded
                s = [s ' ' class(str.AverageDataStdDev) '}'];
            else
                s = [s ', not loaded}'];
            end
            s = [s '\n'];
            s = [s '\tAverageDataTimeStamps:\t {' num2str(size(str.AverageDataTimeStamps,1))...
                'x' num2str(size(str.AverageDataTimeStamps,2)) ' cell}'];
            s = [s '\n'];
            s = [s '\tAverageDataCount:\t\t {' num2str(size(str.AverageDataCount,1))...
                'x' num2str(size(str.AverageDataCount,2)) ' cell}'];
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
        % Returns the converted mean data
        %
        % function data = getConvertedData(str,cfg)
        %
        % If the DataType is 'raw', this will convert the data to
        % meaningful units and return it, but not change the internal
        % AverageDataMean field. If the DataType is 'single' or 'double'
        % this will either return the AverageDataMean field (if
        % cfg.dataType equals the DataType) or cast the AverageDataMean
        % entry to the requested data type in cfg.dataType.
        %
        % Input:
        %   cfg     -   A configuration structure. Can contain the field
        %               'dataType' which describes the requested data type.
        %               The default is 'double'. cfg.dataType has to be one
        %               of the built-in types.
        %
        % Output:
        %   data    -   The AverageDataMean converted to cfg.dataType. If the
        %               original DataType is 'raw', this includes the
        %               conversion from ADC units to units of 10 ^
        %               Info.Exponent [Info.Unit]
            cfg = McsHDF5.checkParameter(cfg, 'dataType', 'double');
            
            if ~strcmp(seg.DataType,'raw')
                if ~strcmp(seg.DataType,cfg.dataType)
                    data = cast(seg.AverageDataMean{idx},cfg.dataType);
                else
                    data = seg.AverageDataMean{idx};
                end
            else
                sourceChan = str2double(seg.Info.SourceChannelIDs{idx});
                chanidx = seg.SourceInfoChannel.ChannelID == sourceChan;
                conv_factor = cast(seg.SourceInfoChannel.ConversionFactor(chanidx),cfg.dataType);
                adzero = cast(seg.SourceInfoChannel.ADZero(chanidx),cfg.dataType);
                data = cast(seg.AverageDataMean{idx},cfg.dataType);
                data = bsxfun(@minus,data,adzero);
                data = bsxfun(@times,data,conv_factor);
            end
        end
        
        function data = getConvertedStdDev(seg,idx,cfg)
        % Returns the converted standard deviation data
        %
        % function data = getConvertedStdDev(str,cfg)
        %
        % If the DataType is 'raw', this will convert the data to
        % meaningful units and return it, but not change the internal
        % AverageDataStdDev field. If the DataType is 'single' or 'double'
        % this will either return the AverageDataStdDev field (if
        % cfg.dataType equals the DataType) or cast the AverageDataStdDev
        % entry to the requested data type in cfg.dataType.
        %
        % Input:
        %   cfg     -   A configuration structure. Can contain the field
        %               'dataType' which describes the requested data type.
        %               The default is 'double'. cfg.dataType has to be one
        %               of the built-in types.
        %
        % Output:
        %   data    -   The AverageDataStdDev converted to cfg.dataType. If the
        %               original DataType is 'raw', this includes the
        %               conversion from ADC units to units of 10 ^
        %               Info.Exponent [Info.Unit]
            cfg = McsHDF5.checkParameter(cfg, 'dataType', 'double');
            
            if ~strcmp(seg.DataType,'raw')
                if ~strcmp(seg.DataType,cfg.dataType)
                    data = cast(seg.AverageDataStdDev{idx},cfg.dataType);
                else
                    data = seg.AverageDataStdDev{idx};
                end
            else
                sourceChan = str2double(seg.Info.SourceChannelIDs{idx});
                chanidx = arrayfun(@(x)(find(seg.SourceInfoChannel.ChannelID == x)),sourceChan);
                conv_factor = cast(seg.SourceInfoChannel.ConversionFactor(chanidx),cfg.dataType);
                adzero = cast(seg.SourceInfoChannel.ADZero(chanidx),cfg.dataType);
                data = cast(seg.AverageDataStdDev{idx},cfg.dataType);
                data = bsxfun(@minus,data,adzero);
                data = bsxfun(@times,data,conv_factor);
            end
        end
        
        function out_str = readPartialSegmentData(str, cfg)
        % Read a subset of the average entities from the stream.
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
            out_str = McsHDF5.McsAverageSegment(str.FileName, tmpStruct);
            out_str.Internal = true;
            
            readNecessary = ~str.MeanLoaded || ~str.StdDevLoaded;
            if readNecessary
                fprintf('Reading partial segment data...')
            end
            
            out_str.AverageDataTimeStamps = out_str.AverageDataTimeStamps(cfg.segment);
            out_str.AverageDataCount = out_str.AverageDataCount(cfg.segment);
            out_str.DataType = str.DataType;
            
            if str.MeanLoaded
                out_str.AverageDataMean = str.AverageDataMean(cfg.segment);
            else 
                out_str.AverageDataMean = out_str.AverageDataMean(cfg.segment);
                fid = H5F.open(str.FileName, 'H5F_ACC_RDONLY', []);
                gid = H5G.open(fid,str.StructName);
                for gidx = 1:length(cfg.segment)
                    try
                        read_mean_data(out_str, cfg.segment(gidx), gidx, gid);
                    catch
                        out_str.Internal = false;
                    end
                end
                H5G.close(gid);
                H5F.close(fid);
            end
            out_str.Internal = true;
            
            if str.StdDevLoaded
                out_str.AverageDataStdDev = str.AverageDataStdDev(cfg.segment);
                emptySegments = cellfun(@isempty, str.AverageDataStdDev);
            else 
                out_str.AverageDataStdDev = out_str.AverageDataStdDev(cfg.segment);
                emptySegments = false(1,length(cfg.segment));
                fid = H5F.open(str.FileName, 'H5F_ACC_RDONLY', []);
                gid = H5G.open(fid,str.StructName);
                for gidx = 1:length(cfg.segment)
                    try
                        read_stddev_data(out_str, cfg.segment(gidx), gidx, gid);
                    catch
                        out_str.Internal = false;
                        emptySegments(gidx) = true;
                    end
                end
                H5G.close(gid);
                H5F.close(fid);
            end
            out_str.Internal = true;
            
            if readNecessary
                fprintf('done!\n');
            end
            
            fns = fieldnames(out_str.SourceInfoChannel);
            for fni = 1:length(fns)
                info = out_str.SourceInfoChannel.(fns{fni});
                out_str.SourceInfoChannel.(fns{fni}) = info(cfg.segment);
            end
            out_str.MeanLoaded = true;
            out_str.StdDevLoaded = true;
            out_str.TimeStampDataType = str.TimeStampDataType;
            out_str.copyFields(str, cfg.segment);
            out_str.set_data_unit_dimension(emptySegments);
            out_str.Internal = false;
        end
    end
    
    methods (Access = private)
        function convert_mean_from_raw(seg,idx)
            seg.Internal = true;
            sourceChan = str2double(seg.Info.SourceChannelIDs{idx});
            chanidx = seg.SourceInfoChannel.ChannelID == sourceChan;
            conv_factor = cast(seg.SourceInfoChannel.ConversionFactor(chanidx),seg.DataType);
            adzero = cast(seg.SourceInfoChannel.ADZero(chanidx),seg.DataType);
            seg.AverageDataMean{idx} = cast(seg.AverageDataMean{idx},seg.DataType);
            seg.AverageDataMean{idx} = bsxfun(@minus,seg.AverageDataMean{idx},adzero);
            seg.AverageDataMean{idx} = bsxfun(@times,seg.AverageDataMean{idx},conv_factor);
            seg.Internal = false;
        end
        
        function convert_stddev_from_raw(seg,idx)
            seg.Internal = true;
            sourceChan = str2double(seg.Info.SourceChannelIDs{idx});
            chanidx = seg.SourceInfoChannel.ChannelID == sourceChan;
            conv_factor = cast(seg.SourceInfoChannel.ConversionFactor(chanidx),seg.DataType);
            adzero = cast(seg.SourceInfoChannel.ADZero(chanidx),seg.DataType);
            seg.AverageDataStdDev{idx} = cast(seg.AverageDataStdDev{idx},seg.DataType);
            seg.AverageDataStdDev{idx} = bsxfun(@minus,seg.AverageDataStdDev{idx},adzero);
            seg.AverageDataStdDev{idx} = bsxfun(@times,seg.AverageDataStdDev{idx},conv_factor);
            seg.Internal = false;
        end
        
        function set_data_unit_dimension(str, emptySegments)    
            for segi = 1:length(str.Info.SegmentID)
                if emptySegments(segi)
                    str.DataUnit{segi} = [];
                    str.DataDimensions{segi} = [];
                    continue
                end
                if strcmp(str.DataType,'raw')
                    str.DataUnit{segi} = 'ADC';
                    str.DataDimensions{segi} = 'samples x averages';
                else
                    sourceChan = str2double(str.Info.SourceChannelIDs{segi});

                    chanidx = str.SourceInfoChannel.ChannelID == sourceChan;
                    [ignore,unit_prefix] = McsHDF5.ExponentToUnit(str.SourceInfoChannel.Exponent(chanidx),0);
                    str.DataUnit{segi} = [unit_prefix str.SourceInfoChannel.Unit{chanidx}];
                    str.DataDimensions{segi} = 'samples x averages';
                end
            end
        end
        
        function read_mean_data(str, index, storageIndex, gid)
            str.Internal = true;
            did = H5D.open(gid, ['AverageData_' num2str(str.Info.SegmentID(index))]);
            dataspace = H5D.get_space(did);
            [r, dims, m] = H5S.get_simple_extent_dims(dataspace);
            dims(1) = 1;
            offset = [0 0 0];
            mem_space_id = H5S.create_simple(3,dims,[]);
            file_space_id = H5D.get_space(did);
            H5S.select_hyperslab(file_space_id,'H5S_SELECT_SET',offset,[1 1 1],[1 1 1],dims);
            str.AverageDataMean{storageIndex} = H5D.read(did,'H5ML_DEFAULT',mem_space_id,file_space_id,'H5P_DEFAULT');
            str.AverageDataMean{storageIndex} = reshape(str.AverageDataMean{storageIndex}, fliplr(dims(2:3)))';
            if ~strcmp(str.DataType,'raw')
                convert_mean_from_raw(str,storageIndex);
            end
            H5D.close(did);
            str.Internal = false;
        end
        
        function read_stddev_data(str, index, storageIndex, gid)
            str.Internal = true;
            did = H5D.open(gid, ['AverageData_' num2str(str.Info.SegmentID(index))]);
            dataspace = H5D.get_space(did);
            [r, dims, m] = H5S.get_simple_extent_dims(dataspace);
            dims(1) = 1;
            offset = [1 0 0];
            mem_space_id = H5S.create_simple(3,dims,[]);
            file_space_id = H5D.get_space(did);
            H5S.select_hyperslab(file_space_id,'H5S_SELECT_SET',offset,[1 1 1],[1 1 1],dims);
            str.AverageDataStdDev{storageIndex} = H5D.read(did,'H5ML_DEFAULT',mem_space_id,file_space_id,'H5P_DEFAULT');
            str.AverageDataStdDev{storageIndex} = reshape(str.AverageDataStdDev{storageIndex}, fliplr(dims(2:3)))';
            if ~strcmp(str.DataType,'raw')
                convert_stddev_from_raw(str,storageIndex);
            end
            H5D.close(did);
            str.Internal = false;
        end
    end
end