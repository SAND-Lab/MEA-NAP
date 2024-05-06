classdef McsEventStream < McsHDF5.McsStream
% Holds the contents of an EventStream
%
% Important fields:
%   Events      -   (1xn) cell array, each cell holding either a (1 x events)
%                   vector of time stamps for each event or a (2 x events)
%                   matrix, where the first column are time stamps and
%                   the second column are durations. Both are given in
%                   microseconds.
%
%   The Info field and the other attributes provide general information
%   about the event stream.
%
% (c) 2016 by Multi Channel Systems MCS GmbH
    
    properties (SetAccess = private)
        % Events - (cell array) Each cell holds either a (1 x events)
        % vector of time stamps for each event entity or a (2 x events)
        % matrix, where the first columns are event time stamps and the second
        % column are event durations. Both are given in microseconds.
        Events = {}; 
        TimeStampDataType % (string) The type of the time stamps, 'double' or 'int64'
    end
    properties (Access = private)
        StructInfo;
    end
    
    methods
        function str = McsEventStream(filename, strStruct, source, varargin)
        % Constructs a McsEventStream object.
        %
        % function str = McsEventStream(filename, source, strStruct)
        % function str = McsEventStream(filename, source, strStruct, cfg)
        %
        % Reads the meta-information from the file but does not read the
        % actual event data. This is performed the first time that the
        % Events field is accessed.
        %
        % Optional input:
        %   cfg     -   configuration structure, can contain
        %               the following field:
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
        
            str = str@McsHDF5.McsStream(filename,strStruct,'Event',source);
            str.StructInfo = strStruct;
            evts = str.Info.EventID;
            str.Events = cell(1,length(evts)); 
            if strcmpi(cfg.timeStampDataType,'int64')
                str.TimeStampDataType = 'int64';
            else
                type = cfg.timeStampDataType;
                if ~strcmp(type,'double')
                    error('Only int64 and double are supported for timeStampDataType!');
                end
                str.TimeStampDataType = type;
            end
            if strcmp(source, 'CMOS-MEA')
                str.Info.SourceChannelLabels = str.Info.SourceChannelIDs;
                str.Label = McsHDF5.McsH5Helper.GetFromAttributes(strStruct, 'ID.Instance', mode);
                str.DataSubType = McsHDF5.McsH5Helper.GetFromAttributes(strStruct, 'SubType', mode);
            end
        end
        
        function data = get.Events(str)
        % Accessor function for events.
        % 
        % function data = get.Events(str)
        %
        % Loads the events from the file the first time that the Events
        % field is requested.
            if exist('h5info')
                mode = 'h5';
            else
                mode = 'hdf5';
            end
            
            if ~str.Internal && ~str.DataLoaded
                fprintf('Reading event data...')
                str = LoadEventsFromFile(str, mode, str.Info.EventID);
                fprintf('done!\n');
                str.DataLoaded = true;
            end
            data = str.Events;
        end
        
        function s = disp(str)
            s = 'McsEventStream object\n\n';
            s = [s 'Properties:\n'];
            s = [s '\tStream Label:\t\t\t ' strtrim(str.Label) '\n'];
            s = [s '\tNumber of Events:\t\t ' num2str(length(str.Info.EventID)) '\n'];
            s = [s '\tData Loaded:\t\t\t '];
            if str.DataLoaded
                s = [s 'true\n'];
            else
                s = [s 'false\n'];
            end
            s = [s '\n'];
            
            s = [s 'Available Fields:\n'];
            s = [s '\tEvents:\t\t\t\t\t {1x' num2str(length(str.Info.EventID))];
            if str.DataLoaded
                s = [s ' ' class(str.Events) '}'];
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
        
        function out_str = readPartialEventData(str, cfg)
        % Read a subset of the event entities from the stream.
        %
        % function out_str = readPartialEventData(str, cfg)
        %
        % Reads a subset of the event entities from the HDF5 file and
        % returns the McsEventStream object containing only the specific
        % events. Useful, if the data has not yet been read from the file
        % and the user is only interested in a few events.
        %
        % Input:
        %   str       -   A McsEventStream object
        %
        %   cfg       -   Either empty (for default parameters) or a
        %                 structure with the field:
        %                 'event': Vector of event entity indices
        %                 'window': Empty for all timestamps, otherwise a
        %                   vector [start end] in seconds
        %
        % Output:
        %   out_str     -   The McsEventStream with the requested event
        %                   entities
            if exist('h5info')
                mode = 'h5';
            else
                mode = 'hdf5';
            end
            
            defaultEvent = 1:length(str.Info.EventID);
            [cfg, isDefault] = McsHDF5.checkParameter(cfg, 'event', defaultEvent);
            if ~isDefault
                if any(cfg.event < 1 | cfg.event > length(defaultEvent) )
                    cfg.event = cfg.event(cfg.event >= 1 & cfg.event <= length(defaultEvent));
                    if isempty(cfg.event)
                        error('No event indices found!');
                    else
                        warning(['Using only event indices between ' num2str(cfg.event(1)) ' and ' num2str(cfg.event(end)) '!']);
                    end
                end
            end
            cfg = McsHDF5.checkParameter(cfg, 'window', [-Inf Inf]);
            
            % read metadata
            tmpStruct = str.StructInfo;
            out_str = McsHDF5.McsEventStream(str.FileName, tmpStruct, str.SourceType);
            out_str.Internal = true;
            if str.DataLoaded
                out_str.Events = str.Events(cfg.event);
            else
                out_str.Events = out_str.Events(cfg.event);
                fprintf('Reading partial event data...')
                out_str = LoadEventsFromFile(out_str, mode, str.Info.EventID(cfg.event));
                for gidx = 1:length(cfg.event)
                    if ~isempty(out_str.Events{gidx})
                        idx = McsHDF5.TickToSec(out_str.Events{gidx}(1,:)) >= cfg.window(1) ...
                            & McsHDF5.TickToSec(out_str.Events{gidx}(1,:)) <= cfg.window(2);
                        out_str.Events{gidx} = out_str.Events{gidx}(:,idx);
                    end
                end
                fprintf('done!\n');
            end
            out_str.DataLoaded = true;
            out_str.TimeStampDataType = str.TimeStampDataType;
            out_str.copyFields(str, cfg.event);
            out_str.Internal = false;
        end
    end
    
    methods (Access = private)
        function str = LoadEventsFromFile(str, mode, entities)
            oldInternal = str.Internal;
            str.Internal = true;
            if strcmp(str.SourceType, 'DataManager')
                for gidx = 1:length(entities)
                    try
                        if strcmp(mode,'h5')
                            str.Events{gidx} = ...
                                h5read(str.FileName,[str.StructName '/EventEntity_' num2str(entities(gidx))])';
                        else
                            str.Events{gidx} = ...
                                hdf5read(str.FileName,[str.StructName '/EventEntity_' num2str(entities(gidx))])';
                        end
                    end
                    if ~strcmp(str.TimeStampDataType,'int64')
                        str.Events{gidx} = cast(str.Events{gidx},str.TimeStampDataType);
                    end
                end
            elseif strcmp(str.SourceType, 'CMOS-MEA')
                evts = McsHDF5.McsH5Helper.ReadCompoundDataset(str.FileName, [str.StructName '/EventData'], mode);
                if size(evts, 1) > 0
                    for eidx = 1:length(entities)
                        idx = evts.EventID == entities(eidx);
                        converted = MakeEventSubset(str, evts, idx);
                        if ~isempty(converted)
                            str.Events{eidx} = converted;
                            if ~strcmp(str.TimeStampDataType,'int64')
                                str.Events{eidx} = cast(str.Events{eidx},str.TimeStampDataType);
                            end
                        end
                    end
                end
            end
            str.Internal = oldInternal;
        end
        
        function subset = MakeEventSubset(str, evts, idx)
            if ~isempty(evts) && any(idx)
                subset = zeros(5, sum(idx));
                subset(1,:) = evts.TimeStamp(idx);
                subset(2,:) = evts.Duration(idx);
                subset(3,:) = evts.Info(idx);
            else 
                subset = [];
            end
        end
    end
end