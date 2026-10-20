function plot(timeStream,cfg,varargin)
% Plot the contents of a McsTimeStampStream object. 
%
% function plot(timeStream,cfg,varargin)
%
% Produces a plot in which the time stamp of each event is shown as a line
% on a time scale.
%
% Input:
%
%   timeStream    -   A McsTimeStampStream object
%
%   cfg          -   Reserved for future use, currently unused
%
%   Optional inputs in varargin are passed to the plot function.
%
% Usage:
%
%   plot(timeStream, cfg);
%   plot(timeStream, cfg, ...);
%   timeStream.plot(cfg);
%   timeStream.plot(cfg, ...);

    lineLength = 0.3;
    M = cell(length(timeStream.TimeStamps),2);
    emptyTimeStamps = false(1,length(timeStream.TimeStamps));
    for timei = 1:length(timeStream.TimeStamps)
        if isempty(timeStream.TimeStamps{timei})
            emptyTimeStamps(timei) = true;
            continue
        end
        M{timei,1} = McsHDF5.TickToSec([timeStream.TimeStamps{timei} ; timeStream.TimeStamps{timei}]);
        M{timei,2} = repmat([timei-lineLength ; timei+lineLength],1,size(M{timei,1},2));
    end
    if all(emptyTimeStamps)
        return
    end
    for timei = 1:length(timeStream.TimeStamps)
        if emptyTimeStamps(timei)
            continue
        end
        if isempty(varargin)
            line(M{timei,1},M{timei,2},'Color','k')
        else
            line(M{timei,1},M{timei,2},varargin{:})
        end
    end
    set(gca,'YTick',1:length(timeStream.TimeStamps));
    set(gca,'YTickLabel',strtrim(timeStream.Info.SourceChannelLabels));
    ylabel('Source Channel')
    xlabel('Time [s]')
end
