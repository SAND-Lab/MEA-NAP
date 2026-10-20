function plot(recording,cfg,varargin)
% Plot the contents of a McsRecording object.
%
% function plot(recording,cfg,varargin)
%
% Input:
%
%   recording-  A McsRecording object
%
%   cfg      -  Either empty (for default parameters) or a structure with
%               (some of) the following fields:
%               'analog': Configuration structure for McsAnalogStream.plot:
%                   []: default parameters
%                   single config struct: replicated for all analog streams
%                   cell array of config structs: each cell contains a
%                   config struct for a specific stream.
%                   See help McsAnalogStream.plot for details on the config
%                   structure
%               'frame': Configuration structure for McsFrameStream.plot
%                   see 'analog' for options
%               'segment': Configuration structure for McsSegmentStream.plot
%                   see 'analog' for options
%               'event': Configuration structure for McsEventStream.plot
%                   see 'analog' for options
%               'timestamp': Configuration structure for McsTimeStampStream.plot
%                   see 'analog' for options
%               'analogstreams': empty for all analog streams, otherwise
%                   vector with indices of analog streams (default: all)
%               'framestreams': empty for all frame streams, otherwise
%                   vector with indices of frame streams (default: all)
%               'segmentstreams': empty for all segment streams, otherwise
%                   vector with indices of segment streams (default: all)
%               'eventstreams': empty for all event streams, otherwise
%                   vector with indices of event streams (default: all)
%               'timestampstreams': empty for all event streams, otherwise
%                   vector with indices of event streams (default: all)
%               If fields are missing, their default values are used.
%
%   Optional inputs in varargin are passed to the plot functions. Warning: 
%   might produce error if segments / frames are mixed with analog / event
%   streams.
%
% Usage:
%
%   plot(recording, cfg);
%   plot(recording, cfg, ...);
%   recording.plot(cfg);
%   recording.plot(cfg, ...);
%
% (c) 2016 by Multi Channel Systems MCS GmbH

    if ~isempty(recording.AnalogStream)
        
        cfg = doParameterCheck(cfg, 'analog', recording.AnalogStream);
        
        for stri = 1:length(cfg.analogstreams)
            figure
            plot(recording.AnalogStream{cfg.analogstreams(stri)},cfg.analog{stri},varargin{:});
            set(gcf,'Name',['Analog Stream ' num2str(cfg.analogstreams(stri))]);
        end
    end
    
    if ~isempty(recording.FrameStream)
        
        cfg = doParameterCheck(cfg, 'frame', recording.FrameStream);
        
        for stri = 1:length(cfg.framestreams)
            figure
            plot(recording.FrameStream{cfg.framestreams(stri)},cfg.frame{stri},varargin{:});
            set(gcf,'Name',['Frame Stream ' num2str(cfg.framestreams(stri))]);
        end
    end
    
    if ~isempty(recording.SegmentStream)
        
        cfg = doParameterCheck(cfg, 'segment', recording.SegmentStream);
        
        for stri = 1:length(cfg.segmentstreams)
            figure
            plot(recording.SegmentStream{cfg.segmentstreams(stri)},cfg.segment{stri},varargin{:});
            set(gcf,'Name',['Segment Stream ' num2str(cfg.segmentstreams(stri))]);
        end
    end
    
    if ~isempty(recording.EventStream)
        
        cfg = doParameterCheck(cfg, 'event', recording.EventStream);
        
        for stri = 1:length(cfg.eventstreams)
            figure
            plot(recording.EventStream{cfg.eventstreams(stri)},cfg.event{stri},varargin{:});
            set(gcf,'Name',['Event Stream ' num2str(cfg.eventstreams(stri))]);
        end
    end
    
    if ~isempty(recording.TimeStampStream)
        
        cfg = doParameterCheck(cfg, 'timestamp', recording.TimeStampStream);
        
        for stri = 1:length(cfg.timestampstreams)
            figure
            plot(recording.TimeStampStream{cfg.timestampstreams(stri)},cfg.timestamp{stri},varargin{:});
            set(gcf,'Name',['Time Stamp Stream ' num2str(cfg.timestampstreams(stri))]);
        end
    end
end

function cfg = doParameterCheck(cfg, streamType, stream)
    [cfg, isDefault] = McsHDF5.checkParameter(cfg, streamType, repmat({[]},1,length(stream)));
    if ~isDefault
        if ~iscell(cfg.(streamType))
            cfg.(streamType) = repmat({cfg.(streamType)},1,length(stream));
        end
    end

    cfg = McsHDF5.checkParameter(cfg, [streamType 'streams'], 1:length(stream));
end