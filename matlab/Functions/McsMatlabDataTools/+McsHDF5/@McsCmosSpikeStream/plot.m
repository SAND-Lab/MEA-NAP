function plot(spikeStream, cfg, varargin)
% Plot the contents of a McsCmosSpikeStream object
%
% function plot(str, cfg, varargin)
%
% Shows a raster plot of the spike timestamps. If only a single channel is
% selected, produces an overlay of the spike cutouts for this channel.
%
% Input:
%
%   spikeStream     -   A McsCmosSpikeStream object
%
%   cfg             -   Either empty (for default parameters) or a
%                       structure with (some of) the following fields:
%                       'channel': empty for all channels, otherwise a
%                           vector of sensor IDs (default: all)
%                       'window': empty for the whole time range, otherwise
%                           a vector with two entries: [start end] of the 
%                           time range, both in seconds.
%                       
%   Optional inputs in varargin are passed to the line and patch function
%   of the raster plot.
%
% Usage:
%   plot(spikeStream, cfg)
%   plot(spikeStream, cfg, ...)
%   spikeStream.plot(cfg)
%   spikeStream.plot(cfg, ...)
%
% (c) 2017 by Multi Channel Systems MCS GmbH

    clf
    
    cfg = McsHDF5.checkParameter(cfg, 'window', McsHDF5.TickToSec([spikeStream.Info.From spikeStream.Info.To]));
    cfg = McsHDF5.checkParameter(cfg, 'channel', sort(unique(spikeStream.SpikeData.SensorID)));

    idx = McsHDF5.TickToSec(spikeStream.SpikeData.TimeStamp) >= cfg.window(1);
    idx = idx & McsHDF5.TickToSec(spikeStream.SpikeData.TimeStamp) < cfg.window(2);
    
    if numel(cfg.channel) == 1 && isfield(spikeStream.SpikeData, 'Cutout')
        subplot(2,1,1)
        idx = idx & spikeStream.SpikeData.SensorID == cfg.channel;
        time = -spikeStream.Info.PreInterval : spikeStream.Info.Tick : (spikeStream.Info.PostInterval - 1);
        data_to_plot = spikeStream.SpikeData.Cutout(idx, :)';
        orig_exp = log10(max(abs(data_to_plot(:))));
        unit_exp = double(spikeStream.Info.Exponent(1));

        [fact,unit_string] = McsHDF5.ExponentToUnit(orig_exp+unit_exp,orig_exp);
        if ~isnan(fact)
            data_to_plot = data_to_plot * fact;
        end
        plot(time, data_to_plot);
        title([spikeStream.Label ' Cutouts Channel ' num2str(cfg.channel(1))]);
        xlabel('Time [µs]');
        ylabel([unit_string spikeStream.Info.Unit{1}],'Interpreter','tex');
        subplot(2,1,2)
    end
        
    lineLength = 0.3;
    for ci = 1:length(cfg.channel)
        ts = spikeStream.SpikeData.TimeStamp(idx & spikeStream.SpikeData.SensorID == cfg.channel(ci));
        timestamps = McsHDF5.TickToSec(ts);
        if size(timestamps,1) == 1
            M{1} = [timestamps ; timestamps];
            M{2} = [ci-lineLength ; ci+lineLength];
            if isempty(varargin)
                line(M{1},M{2},'Color','k')
            else
                line(M{1},M{2},varargin{:})
            end
        else
            M{1} = repmat(timestamps',4,1);
            M{2} = repmat([ci-lineLength ; ci+lineLength],1,size(M{1},2));
            if isempty(varargin)
                patch(M{1},repmat(M{2},2,1),'k')
            else
                patch(M{1},repmat(M{2},2,1),varargin{:})
            end
        end
    end
    set(gca,'YTick',1:length(cfg.channel));
    set(gca,'YTickLabel',arrayfun(@num2str, cfg.channel, 'UniformOutput', false));
    ylabel('Sensor ID');
    xlabel('Time [s]');
end