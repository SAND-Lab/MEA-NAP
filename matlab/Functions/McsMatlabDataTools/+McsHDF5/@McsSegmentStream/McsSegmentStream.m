classdef McsSegmentStream < McsHDF5.McsStream
% Holds the contents of a SegmentStream, either spike data or averages
%
% (c) 2016 by Multi Channel Systems MCS GmbH
    
    properties (SetAccess = protected)
        % (struct) Information about the source channel(s) of the segment. 
        % Same as the McsAnalogStream.Info field
        SourceInfoChannel 
        DataDimensions = {}; % (cell array) The data dimensions for each segment entity
        DataUnit = {}; % (cell array) The data unit for each segment entity
        DataType % (string) The data type, e.g. 'double', 'single' or 'raw'
        TimeStampDataType % (string) The type of the time stamps, 'double' or 'int64'
    end
    
    methods (Abstract)
        out_str = readPartialSegmentData(str, cfg);
        s = disp(str);
        data = getConvertedData(seg,idx,cfg);
    end
    
    methods (Access = protected)
        
        function str = McsSegmentStream(filename, strStruct, varargin)
            
            cfg = McsHDF5.McsStream.checkStreamParameter(varargin{:});
            
            if exist('h5info')
                mode = 'h5';
            else
                mode = 'hdf5';
            end
            
            str = str@McsHDF5.McsStream(filename,strStruct,'Segment','DataManager');
            if strcmp(mode,'h5')
                sourceInfo = h5read(filename, [strStruct.Name '/SourceInfoChannel']);
            else
                fid = H5F.open(filename,'H5F_ACC_RDONLY','H5P_DEFAULT');
                did = H5D.open(fid, [strStruct.Name '/SourceInfoChannel']);
                sourceInfo = H5D.read(did,'H5ML_DEFAULT','H5S_ALL','H5S_ALL','H5P_DEFAULT');
            end
            fn = fieldnames(sourceInfo);
            for fni = 1:length(fn)
                str.SourceInfoChannel.(fn{fni}) = sourceInfo.(fn{fni});
                if strcmpi(cfg.timeStampDataType,'double') && strcmpi(class(str.SourceInfoChannel.(fn{fni})), 'int64')
                    str.SourceInfoChannel.(fn{fni}) = double(str.SourceInfoChannel.(fn{fni}));
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
        end
    end
    
    methods (Static)
        function out_str = makeSegmentStream(filename, strStruct, varargin)
            out_str = McsHDF5.McsStream(filename, strStruct, 'Segment', 'DataManager');
            if strcmp(out_str.DataSubType,'Average')
                out_str = McsHDF5.McsAverageSegment(filename, strStruct, varargin{:});
            elseif strcmp(out_str.DataSubType,'Spike') || strcmp(out_str.DataSubType,'Sweep')
                out_str = McsHDF5.McsCutoutSegment(filename, strStruct, varargin{:});
            else 
                error('Unknown DataSubType');
            end
        end
    end
end