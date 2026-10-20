function frameMovie(fde,cfg,varargin)
% Display animation of the frame data
%
% function frameMovie(fde,cfg,varargin)
%
% This function shows the evolution of FrameStream data over time. It
% visualizes the data at each time point as a surface over the 2D array of
% channels, in the same way as the plot function for FrameDataEntities. It
% animates the flow of time by plotting this visualization for each time
% point.
%
% Input:
%   fde         -   A McsFrameDataEntity object
%
%   cfg         -   Either empty (for default parameters) or a
%                   structure with (some of) the following fields: 
%                   'start': The start time point of the animation in seconds,
%                       or (if empty) the first sample.            
%                   'end':  The end time point of the of the animation in
%                       seconds, or (if empty) the last sample.
%                   'step': The time step between animation frames in
%                       seconds, or (if empty) a step from sample to sample
%                   'fps': The animation update rate in frames per second.
%                       This is not guaranteed and provides just an upper
%                       limit, because the actual maximum animation rate
%                       depends on the speed of the machine.
%
% Further optional inputs in varargin are interpreted as parameters for
% gca. -> set(gca,varargin{:}).
%
% Usage:
%
%   frameMovie(fde, cfg);
%   frameMovie(fde, cfg, ...);
%   fde.frameMovie(cfg);
%   fde.frameMovie(cfg, ...);
%
% (c) 2016 by Multi Channel Systems MCS GmbH

    cfg = McsHDF5.checkParameter(cfg, 'start', McsHDF5.TickToSec(fde.FrameDataTimeStamps(1)));
    cfg = McsHDF5.checkParameter(cfg, 'end', McsHDF5.TickToSec(fde.FrameDataTimeStamps(end)));
    cfg = McsHDF5.checkParameter(cfg, 'step', McsHDF5.TickToSec(fde.Info.Tick));
    cfg = McsHDF5.checkParameter(cfg, 'fps', 10);
    
    cfg.window = cfg.start;
   
    initial = true;
    
    while cfg.window < cfg.end - cfg.step
        cfg.window = cfg.window + cfg.step;
        
        plot(fde,cfg)
        
        if ~isempty(varargin)
            set(gca,varargin{:});
        end
        
        if initial
            input('Set initial position');
            initial = false;
            ax = axis;
            [az,el] = view;
        end
        axis(ax);
        view(az,el);
        pause(1/cfg.fps);
    end
end