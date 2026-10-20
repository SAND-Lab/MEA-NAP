function plot(frameStream,cfg,varargin)
% Plot the contents of a McsFrameStream object.
%
% function plot(frameStream,cfg,varargin)
%
% Produces plots of the individual FrameDataEntities (one figure per
% entity).
%
% Input:
%
%   frameStream     -   A McsFrameStream object
%
%   cfg             -   Either empty (for default parameters) or a
%                       structure with (some of) the following fields:
%                       'entities': empty for all frame data entities,
%                           otherwise a vector of entity indices (default:
%                           all)
%                       'window': Specifies the displayed time range:
%                           []: Total time range
%                           single value or [start end]: replicated for all
%                           entities
%                           cell array of single values or [start end]:
%                           each cell is applied for its corresponding
%                           entity (default: [])
%                       'channelMatrix': Specifies the displayed channels:
%                           []: All channels
%                           nxm matrix: replicated for all entities
%                           cell array of matrices: each cell contains a
%                           matrix which is applied for its corresponding
%                           entity. (default: [])
%                       If fields are missing, their default values are
%                       used.
%
%                       See help McsFrameDataEntity.plot for more details
%                       on the 'window' and the 'channelMatrix' parameter
%
%   Optional inputs in varargin are passed to the plot function.
%
% Usage:
%
%   plot(frameStream, cfg);
%   plot(frameStream, cfg, ...);
%   frameStream.plot(cfg);
%   frameStream.plot(cfg, ...);
%
% (c) 2016 by Multi Channel Systems MCS GmbH

    cfg = McsHDF5.checkParameter(cfg, 'entities', 1:length(frameStream.FrameDataEntity));
    [cfg, isDefault] = McsHDF5.checkParameter(cfg, 'window', repmat({[]},1,length(cfg.entities)));
    if ~isDefault
        if length(cfg.window) <= 2 && ~iscell(cfg.window)
            cfg.window = repmat({cfg.window},1,length(cfg.entities));
        end

        if length(cfg.window) ~= length(cfg.entities) && ~iscell(cfg.window)
            error('cfg.window not specified properly');
        end
    end
    
    [cfg, isDefault] = McsHDF5.checkParameter(cfg, 'channelMatrix', repmat({[]},1,length(cfg.entities)));
    if ~isDefault
        if ~iscell(cfg.channelMatrix)
            cfg.channelMatrix = repmat({cfg.channelMatrix},1,length(cfg.entities));
        end

        if length(cfg.channelMatrix) ~= length(cfg.entities) && ~iscell(cfg.channelMatrix)
            error('cfg.channelMatrix not specified properly');
        end
    end
    
    for enti = 1:length(cfg.entities)
        id = cfg.entities(enti);
        figure
        
        cfg_ent = [];
        cfg_ent.window = cfg.window{enti};
        cfg_ent.channelMatrix = cfg.channelMatrix{enti};
        
        plot(frameStream.FrameDataEntity{id},cfg_ent,varargin);
    end

end