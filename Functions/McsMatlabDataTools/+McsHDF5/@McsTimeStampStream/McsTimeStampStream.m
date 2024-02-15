classdef McsTimeStampStream < McsHDF5.McsStream
% Holds the contents of an TimeStampStream
%
% Fields:
%   TimeStamps -   (1xn) cell array, each cell holding a (1 x timestamps)
%                   vector of time stamps for each time stamp entity.
%
%   The Info field and the other attributes provide general information
%   about the time stamp stream.
    
    properties (SetAccess = private)
        TimeStamps = {}; % (cell array) Each cell holding a vector of time stamps in microseconds
        TimeStampDataType  % (string) The type of the time stamps, 'double' or 'int64'
    end
    
    methods
        function str = McsTimeStampStream(filename, strStruct, varargin)
        % Constructs a McsTimeStampStream object.
        %
        % function str = McsTimeStampStream(filename, strStruct)
        % function str = McsTimeStampStream(filename, strStruct, cfg)
        %
        % Reads the meta-information from the file but does not read the
        % actual time stamp data. This is performed the first time that the
        % TimeStamps field is accessed.
        %
        % % Optional input:
        %   cfg     -   configuration structure, can contain
        %               the following field:
        %               'timeStampDataType': The type of the time stamps,
        %               can be either 'int64' (default) or 'double'. Using
        %               'double' is useful for older Matlab version without
        %               int64 arithmetic.
            cfg = McsHDF5.McsStream.checkStreamParameter(varargin{:});
        
            str = str@McsHDF5.McsStream(filename,strStruct,'TimeStamp','DataManager');
            evts = str.Info.TimeStampEntityID;
            str.TimeStamps = cell(1,length(evts)); 
            if strcmpi(cfg.timeStampDataType,'int64')
                str.TimeStampDataType = 'int64';
            else
                type = cfg.timeStampDataType;
                if ~strcmp(type,'double')
                    error('Only int64 and double are supported for timeStampDataType!');
                end
                str.TimeStampDataType = type;
            end
        end
        
        function data = get.TimeStamps(str)
        % Accessor function for time stamps.
        % 
        % function data = get.TimeStamps(str)
        %
        % Loads the time stamps from the file the first time that the TimeStamps
        % field is requested.
            if exist('h5info')
                mode = 'h5';
            else
                mode = 'hdf5';
            end
            
            if ~str.Internal && ~str.DataLoaded
                fprintf('Reading time stamp data...')
                for gidx = 1:length(str.TimeStamps)
                    try
                        if strcmp(mode,'h5')
                            str.TimeStamps{gidx} = ...
                                h5read(str.FileName,[str.StructName '/TimeStampEntity_' num2str(str.Info.TimeStampEntityID(gidx))])';
                        else
                            str.TimeStamps{gidx} = ...
                                hdf5read(str.FileName,[str.StructName '/TimeStampEntity_' num2str(str.Info.TimeStampEntityID(gidx))])';
                        end
                    end
                    if ~strcmp(str.TimeStampDataType,'int64')
                        str.TimeStamps{gidx} = cast(str.TimeStamps{gidx},str.TimeStampDataType);
                    end
                end
                fprintf('done!\n');
                str.DataLoaded = true;
            end
            data = str.TimeStamps;
        end
        
        function s = disp(str)
            s = 'McsTimeStampStream object\n\n';
            s = [s 'Properties:\n'];
            s = [s '\tStream Label:\t\t\t ' strtrim(str.Label) '\n'];
            s = [s '\tNumber of Entities:\t\t ' num2str(length(str.Info.TimeStampEntityID)) '\n'];
            s = [s '\tData Loaded:\t\t\t '];
            if str.DataLoaded
                s = [s 'true\n'];
            else
                s = [s 'false\n'];
            end
            s = [s '\n'];
            
            s = [s 'Available Fields:\n'];
            s = [s '\tTimeStamps:\t\t\t\t {1x' num2str(length(str.Info.TimeStampEntityID))];
            if str.DataLoaded
                s = [s ' ' class(str.TimeStamps) '}'];
            else
                s = [s ', not loaded}'];
            end
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
        
        function out_str = readPartialTimeStampData(str, cfg)
        % Read a subset of the time stamp entities from the stream.
        %
        % function out_str = readPartialTimeStampData(str, cfg)
        %
        % Reads a subset of the time stamp entities from the HDF5 file and
        % returns the McsTimeStampStream object containing only the
        % specific time stamps. Useful, if the data has not yet been read
        % from the file and the user is only interested in a few time stamp
        % entities.
        %
        % Input:
        %   str       -   A McsTimeStampStream object
        %
        %   cfg       -   Either empty (for default parameters) or a
        %                 structure with the field:
        %                 'timestamp': Vector of timestamp entity indices
        %                 'window': Empty for all timestamps, otherwise a
        %                   vector [start end] in seconds
        %
        % Output:
        %   out_str     -   The McsTimeStampStream with the requested
        %                   time stamp entities
            if exist('h5info')
                mode = 'h5';
            else
                mode = 'hdf5';
            end
            
            defaultTimeStamp = 1:length(str.Info.TimeStampEntityID);
            [cfg, isDefault] = McsHDF5.checkParameter(cfg, 'timestamp', defaultTimeStamp);
            if ~isDefault
                if any(cfg.timestamp < 1 | cfg.timestamp > length(defaultTimeStamp) )
                    cfg.timestamp = cfg.timestamp(cfg.timestamp >= 1 & cfg.timestamp <= length(defaultTimeStamp));
                    if isempty(cfg.timestamp)
                        error('No timestamp indices found!');
                    else
                        warning(['Using only timestamp indices between ' ...
                            num2str(cfg.timestamp(1)) ' and ' num2str(cfg.timestamp(end)) '!']);
                    end
                end
            end
            cfg = McsHDF5.checkParameter(cfg, 'window', [-Inf Inf]);
            
            % read metadata
            tmpStruct.Name = str.StructName;
            out_str = McsHDF5.McsTimeStampStream(str.FileName, tmpStruct);
            out_str.Internal = true;
            if str.DataLoaded
                out_str.TimeStamps = str.TimeStamps(cfg.timestamp);
            else
                out_str.TimeStamps = out_str.TimeStamps(cfg.timestamp);
                fprintf('Reading partial time stamp data...')
                for gidx = 1:length(cfg.timestamp)
                    try
                        if strcmp(mode,'h5')
                            out_str.TimeStamps{gidx} = ...
                                h5read(out_str.FileName,[out_str.StructName '/TimeStampEntity_' num2str(str.Info.TimeStampEntityID(cfg.timestamp(gidx)))])';
                        else
                            out_str.TimeStamps{gidx} = ...
                                hdf5read(out_str.FileName,[out_str.StructName '/TimeStampEntity_' num2str(str.Info.TimeStampEntityID(cfg.timestamp(gidx)))])';
                        end
                    end
                    if ~strcmp(str.TimeStampDataType,'int64')
                        out_str.TimeStamps{gidx} = cast(out_str.TimeStamps{gidx},str.TimeStampDataType);
                    end
                    idx = McsHDF5.TickToSec(out_str.TimeStamps{gidx}) >= cfg.window(1) ...
                        & McsHDF5.TickToSec(out_str.TimeStamps{gidx}) <= cfg.window(2);
                    out_str.TimeStamps{gidx} = out_str.TimeStamps{gidx}(idx);
                end
                fprintf('done!\n');
            end
            out_str.DataLoaded = true;
            out_str.TimeStampDataType = str.TimeStampDataType;
            out_str.copyFields(str, cfg.timestamp);
            out_str.Internal = false;
        end
    end
end