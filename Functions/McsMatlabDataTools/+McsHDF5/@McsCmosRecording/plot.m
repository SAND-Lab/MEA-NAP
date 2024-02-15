function plot(recording,cfg,varargin)
% Plot the contents of a McsCmosRecording object
%
% function plot(recording,cfg,varargin)
%
% Input:
%   recording   -   A McsCmosRecording object
%
%   cfg         -   Either empty (for default parameters) or a structure with
%                   (some of) the following fields:
%                   'acq': Configuration structure for McsCmosAcquisitionSource.plot:
%                       []: default parameters
%                       single config struct: replicated for all
%                       Acquisition structures
%                       cell array of config structs: Each cell contains a
%                       config struct for a specific Acquisition object
%                       see help McsCmosAcquisitionSource.plot for details
%                       on the config structure
%                   'spike': Configuration structure for McsCmosSpikeStream.plot
%                       applied to the SpikeExplorer data source of result
%                       files
%                       []: default parameters
%                       single config structure: replicated for all
%                       SpikeExplorer structures
%                       cell array of config structs: Each cell contains a
%                       config struct for a specific SpikeExplorer object
%                       see help McsCmosSpikeStream.plot for details
%                       on the config structure
%
% Optional inputs in varargin are passed to the plot functions.
%
% Usage:
%
%   plot(recording, cfg);
%   plot(recording, cfg, ...);
%   recording.plot(cfg);
%   recording.plot(cfg, ...);
%
% (c) 2017 by Multi Channel Systems MCS GmbH
    
    if ~isempty(recording.Acquisition)
        cfg = doParameterCheck(cfg, 'acq', recording.Acquisition);
        if ~isa(recording.Acquisition,'McsHDF5.McsCmosLinkedDataSource')
            figure
        end
        plot(recording.Acquisition, cfg.acq{1}, varargin{:});
    end
    if ~isempty(recording.SpikeExplorer)
        cfg = doParameterCheck(cfg, 'spike', recording.SpikeExplorer);
        figure
        plot(recording.SpikeExplorer, cfg.spike{1}, varargin{:});
    end
    if ~isempty(recording.STAExplorer)
        cfg = doParameterCheck(cfg, 'sta', recording.STAExplorer);
        figure
        plot(recording.STAExplorer, cfg.sta{1}, varargin{:});
    end
    if ~isempty(recording.SpikeSorter)
        cfg = doParameterCheck(cfg, 'sorter', recording.SpikeSorter);
        figure
        plot(recording.SpikeSorter, cfg.sorter{1}, varargin{:});
    end
end

function cfg = doParameterCheck(cfg, streamType, stream)
    [cfg, isDefault] = McsHDF5.checkParameter(cfg, streamType, repmat({[]},1,length(stream)));
    if ~isDefault
        if ~iscell(cfg.(streamType))
            cfg.(streamType) = repmat({cfg.(streamType)},1,length(stream));
        end
    end
end