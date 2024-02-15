function plot(analogStream,cfg,varargin)
% Plot the contents of a McsAnalogStream object.
%
% function plot(analogStream,cfg,varargin)
%
% Produces a time series plot with the channels overlayed over each other.
%
% Input:
%
%   analogStream    -   A McsAnalogStream object
%
%   cfg             -   Either empty (for default parameters) or a
%                       structure with (some of) the following fields:
%                       'channel': empty for all channels, otherwise a
%                           vector of channel indices (default: all)
%                       'window': empty for the whole time range, otherwise
%                           a vector with two entries: [start end] of the 
%                           time range, both in seconds.
%                       'legend': either true (default) or false. Matlab
%                           can be very inefficient in plotting legends for
%                           many channels and many time segments. In this
%                           case it can be advisable to shut legend
%                           generation off.
%                       'spacing': either true or false (default). If
%                           false, no spacing is used. Otherwise, an offset
%                           is added to each channel to separate them.
%                           Using this option means that the y-axis is only
%                           valid for the first channel
%                       If fields are missing, their default values are used.
%
%   Optional inputs in varargin are passed to the plot function.
%
% Usage:
%   plot(analogStream, cfg);
%   plot(analogStream, cfg, ...);
%   analogStream.plot(cfg);
%   analogStream.plot(cfg, ...);
%
% (c) 2016 by Multi Channel Systems MCS GmbH
    
    clf
    
    cfg = McsHDF5.checkParameter(cfg, 'legend', true);
    cfg = McsHDF5.checkParameter(cfg, 'spacing', false);
    [cfg, isDefault] = McsHDF5.checkParameter(cfg, 'channel', 1:size(analogStream.ChannelData,1));
    if ~isDefault
        if any(cfg.channel < 1 | cfg.channel > size(analogStream.ChannelData,1))
            cfg.channel = cfg.channel(cfg.channel >= 1 & cfg.channel <= size(analogStream.ChannelData,1));
            if isempty(cfg.channel)
                error('No channels found!');
            else
                warning(['Using only channel indices between ' num2str(cfg.channel(1)) ' and ' num2str(cfg.channel(end)) '!']);
            end
        end
    end
    
    cfg = McsHDF5.checkParameter(cfg, 'window', McsHDF5.TickToSec([analogStream.ChannelDataTimeStamps(1) ...
                      analogStream.ChannelDataTimeStamps(end)]));
    start_index = find(analogStream.ChannelDataTimeStamps >= McsHDF5.SecToTick(cfg.window(1)),1,'first');
    end_index = find(analogStream.ChannelDataTimeStamps <= McsHDF5.SecToTick(cfg.window(2)),1,'last');

    if end_index < start_index
        warning('No time range found')
        return
    end
    
    if strcmp(analogStream.DataType,'raw')
        conv_cfg = [];
        conv_cfg.dataType = 'double';
        data_to_plot = analogStream.getConvertedData(conv_cfg);
        data_to_plot = data_to_plot(cfg.channel,start_index:end_index);
    else
        data_to_plot = analogStream.ChannelData(cfg.channel,start_index:end_index);
    end
    
    if strcmp(analogStream.Info.Unit{1}, 'NoUnit')
        fact = 1;
        unit_string = '';
    else
        orig_exp = log10(max(abs(data_to_plot(:))));
        unit_exp = double(analogStream.Info.Exponent(1));
        
        [fact,unit_string] = McsHDF5.ExponentToUnit(orig_exp+unit_exp,orig_exp);
    end
    
    if ~isnan(fact)
        data_to_plot = data_to_plot * fact;
    end
    
    if cfg.spacing
        mi = min(data_to_plot,[],2);
        ma = max(data_to_plot,[],2);
        offset = cumsum(vertcat(0, ma(2:end)-mi(1:end-1)));
        data_to_plot = bsxfun(@minus,data_to_plot,offset);
    end
    
    timestamps = McsHDF5.TickToSec(analogStream.ChannelDataTimeStamps(start_index:end_index));
    
    segstarts = [0 find(diff(timestamps) > 2*McsHDF5.TickToSec(analogStream.Info.Tick(1))) length(timestamps)-1] + 1;
    
    for segi = 1:length(segstarts)-1
        segidx = segstarts(segi):segstarts(segi+1)-1;
        if isempty([varargin{:}])
            plot(timestamps(segidx),data_to_plot(:,segidx));
        else
            plot(timestamps(segidx),data_to_plot(:,segidx),varargin{:});
        end
        hold on
    end
    
    hold off
    chan_names = analogStream.Info.Label(cfg.channel);
    if cfg.legend
        legend(chan_names);
    end
    
    title([analogStream.Label]);
    xlabel('Time [s]')
    ylabel([unit_string analogStream.Info.Unit{1}],'Interpreter','tex')
    
    set(gcf,'Name',[analogStream.Label]);
    
end
