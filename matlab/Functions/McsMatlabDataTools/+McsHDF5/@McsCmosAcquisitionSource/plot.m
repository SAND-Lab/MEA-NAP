function plot(source,cfg,varargin)
% Plot the contents of a McsCmosAcquisitionSource object.
%
% function plot(source,cfg,varargin)
%
% Input:
%
%   source   -  A McsCmosAcquisitionSource object
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
%               'spike': Configuration structure for McsCmosSpikeStream.plot
%                   see 'analog' for options
%               'event': Configuration structure for McsEventStream.plot
%                   see 'analog' for options
%               'timestamp': Configuration structure for McsTimeStampStream.plot
%                   see 'analog' for options
%               'analogstreams': empty for all analog streams, otherwise
%                   vector with indices of analog streams (default: all)
%               'framestreams': empty for all frame streams, otherwise
%                   vector with indices of frame streams (default: all)
%               'spikestreams': empty for all spike streams, otherwise
%                   vector with indices of spike streams (default: all)
%               'eventstreams': empty for all event streams, otherwise
%                   vector with indices of event streams (default: all)
%               'timestampstreams': empty for all event streams, otherwise
%                   vector with indices of event streams (default: all)
%               If fields are missing, their default values are used.
%
%   Optional inputs in varargin are passed to the plot functions. Warning: 
%   might produce error if spikes / frames are mixed with analog / event
%   streams.
%
% Usage:
%
%   plot(recording, cfg);
%   plot(recording, cfg, ...);
%   recording.plot(cfg);
%   recording.plot(cfg, ...);
%
% (c) 2017 by Multi Channel Systems MCS GmbH

    if ~isempty(source.ChannelStream)
        
        cfg = doParameterCheck(cfg, 'analog', source.ChannelStream);
        
        for stri = 1:length(cfg.analogstreams)
            figure
            plot(source.ChannelStream{cfg.analogstreams(stri)},cfg.analog{stri},varargin{:});
            set(gcf,'Name',['Channel Stream ' num2str(cfg.analogstreams(stri))]);
        end
    end
    
    if ~isempty(source.SensorStream)
        
        cfg = doParameterCheck(cfg, 'frame', source.SensorStream);
        
        for stri = 1:length(cfg.framestreams)
            figure
            plot(source.SensorStream{cfg.framestreams(stri)},cfg.frame{stri},varargin{:});
            set(gcf,'Name',['Sensor Stream ' num2str(cfg.framestreams(stri))]);
        end
    end
    
    if ~isempty(source.EventStream)
        
        cfg = doParameterCheck(cfg, 'event', source.EventStream);
        
        for stri = 1:length(cfg.eventstreams)
            figure
            plot(source.EventStream{cfg.eventstreams(stri)},cfg.event{stri},varargin{:});
            set(gcf,'Name',['Event Stream ' num2str(cfg.eventstreams(stri))]);
        end
    end
    
    if ~isempty(source.SpikeStream)
        
        cfg = doParameterCheck(cfg, 'spike', source.SpikeStream);
        
        for stri = 1:length(cfg.spikestreams)
            figure
            plot(source.SpikeStream{cfg.spikestreams(stri)},cfg.spike{stri},varargin{:});
            set(gcf,'Name',['Spike Stream ' num2str(cfg.spikestreams(stri))]);
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