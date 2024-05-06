function plot(segStream, cfg, varargin)
% Plot the contents of a McsSegmentStream object with averages.
%
% function plot(segStream,cfg,varargin)
%
% Produces for each average object on overlay plot of the averages
%
% Input:
%
%   segStream     -   A McsSegmentStream object
%
%   cfg           -   Either empty (for default parameters) or a
%                     structure with (some of) the following fields:
%                     'segment': empty for all segments, otherwise a
%                       vector of segment indices (default: all)
%                     'window': empty for all averages within a segment,
%                       otherwise a vector [from to] in seconds. All
%                       averages within a segment are displayed for which
%                       the AverageDataTimeStamps are between from and to
%                     'type': either 'mean' (only mean is displayed),
%                       'stddev' (only standard deviations are displayed)
%                       or 'both' (default, mean+-stddev is displayed)
%                     'legend': true (default) or false, enables or
%                       disables plotting of the legend.
%                     'mode': determines how the individual segments are shown. 
%                       This can be either: 
%                       'subplot', which plots all segments in a single figure
%                       'figure', which plots one figure per segment
%                       'iterative', which loops through all segments and
%                       plots them one by one, prompting for input to move
%                       to the next figure.
%                       (default: 'subplot')
%                     If fields are missing, their default values are used.
%
%   Optional inputs in varargin are passed to the plot function.
%
% Usage:
%
%   plot(segStream, cfg);
%   plot(segStream, cfg, ...);
%   segStream.plot(cfg);
%   segStream.plot(cfg, ...);
%
% (c) 2016 by Multi Channel Systems MCS GmbH

    clf
    
    [cfg, isDefault] = McsHDF5.checkParameter(cfg, 'mode', 'subplot');
    [cfg, isDefault] = McsHDF5.checkParameter(cfg, 'segment', 1:length(segStream.AverageDataMean));
    if ~isDefault
        if any(cfg.segment < 1 | cfg.segment > length(segStream.AverageDataMean))
            warning(['Using only segment indices between 1 and ' num2str(length(segStream.AverageDataMean)) '!'])
            cfg.segment = cfg.segment(cfg.segment >= 1 & cfg.segment <= length(segStream.AverageDataMean));
        end
    end
    cfg = McsHDF5.checkParameter(cfg, 'type', 'both');
    validIndex = cellfun(@(x)(~isempty(x)), segStream.AverageDataMean);
    firstFrom = min(cellfun(@(x)(min(x(1,:))),segStream.AverageDataTimeStamps(validIndex)));
    lastTo = max(cellfun(@(x)(max(x(2,:))),segStream.AverageDataTimeStamps(validIndex)));
    cfg = McsHDF5.checkParameter(cfg, 'window', McsHDF5.TickToSec([firstFrom lastTo]));
    cfg = McsHDF5.checkParameter(cfg, 'legend', true);
    
    if strcmp(cfg.mode, 'figure') || strcmp(cfg.mode, 'iterative')
        plotcfg = [];
        for fn = fieldnames(cfg)'
           plotcfg.(fn{1}) = cfg.(fn{1});
        end
        plotcfg.mode = 'subplot';
        first = true;
        for segi = 1:length(cfg.segment)
            id = cfg.segment(segi);
            if isempty(segStream.AverageDataMean{id})
                continue
            end
            plotcfg.segment = id;
            if strcmp(cfg.mode, 'figure') && ~first
                figure
            end
            first = false;
            plot(segStream, plotcfg, varargin{:});    
            if strcmp(cfg.mode, 'iterative')
                input(['Plotting segment ' num2str(id) '. Press RETURN for next segment']);
            end
        end
    elseif strcmp(cfg.mode, 'subplot')
        for segi = 1:length(cfg.segment)
            id = cfg.segment(segi);
            if isempty(segStream.AverageDataMean{id})
                continue
            end

            subplot(1,length(cfg.segment),segi);

            if strcmp(segStream.DataType,'double')
                if strcmp(cfg.type,'mean')
                    data_to_plot = segStream.AverageDataMean{id};
                elseif strcmp(cfg.type,'stddev')   
                    data_to_plot = segStream.AverageDataStdDev{id};
                elseif strcmp(cfg.type,'both')
                    data_to_plot{1} = segStream.AverageDataMean{id};
                    data_to_plot{2} = segStream.AverageDataMean{id} + segStream.AverageDataStdDev{id};
                    data_to_plot{3} = segStream.AverageDataMean{id} - segStream.AverageDataStdDev{id};
                else
                    error(['type ' cfg.type ' is not defined!']);
                end
            else
                conv_cfg = [];
                conv_cfg.dataType = 'double';
                if strcmp(cfg.type,'mean')
                    data_to_plot = segStream.getConvertedData(id,conv_cfg);
                elseif strcmp(cfg.type,'stddev') 
                    data_to_plot = segStream.getConvertedStdDev(id,conv_cfg);
                elseif strcmp(cfg.type,'both')
                    mn = segStream.getConvertedData(id,conv_cfg);
                    sd = segStream.getConvertedStdDev(id,conv_cfg);
                    data_to_plot{1} = mn;
                    data_to_plot{2} = mn + sd;
                    data_to_plot{3} = mn - sd;
                else
                    error(['type ' cfg.type ' is not defined!']);
                end
            end

            if ~iscell(data_to_plot)
                orig_exp = log10(max(abs(data_to_plot(:))));
            else
                orig_exp = log10(max(cellfun(@(x)(max(abs(x(:)))),data_to_plot)));
            end
            sourceChan = str2double(segStream.Info.SourceChannelIDs{id});

            channel_idx = find(segStream.SourceInfoChannel.ChannelID == sourceChan);
            unit_exp = double(segStream.SourceInfoChannel.Exponent(channel_idx));

            [fact,unit_string] = McsHDF5.ExponentToUnit(orig_exp+unit_exp,orig_exp);

            if ~iscell(data_to_plot)
                data_to_plot = data_to_plot' * fact;
            else
                data_to_plot = cellfun(@(x)(x' * fact), data_to_plot, 'UniformOutput', false);
            end

            tsFrom = McsHDF5.TickToSec(segStream.AverageDataTimeStamps{id}(1,:));
            tsTo = McsHDF5.TickToSec(segStream.AverageDataTimeStamps{id}(2,:));

            avgIndex = (tsFrom >= cfg.window(1) & tsFrom <= cfg.window(2)) &...
                        (tsTo >= cfg.window(1) & tsTo <= cfg.window(2));

            pre = -segStream.Info.PreInterval(id);
            post = segStream.Info.PostInterval(id);
            ts = McsHDF5.TickToSec(pre : segStream.SourceInfoChannel.Tick(id) : post);
            ts = ts(1:end-1);

            chan_names = arrayfun(@(from, to)([num2str(from) ' - ' num2str(to) 's']) ,...
                tsFrom(avgIndex), tsTo(avgIndex), 'UniformOutput', false);


            if strcmp(cfg.type,'mean')
                if isempty([varargin{:}])
                    plot(ts, data_to_plot(avgIndex,:));
                else
                    plot(ts, data_to_plot(avgIndex,:),varargin{:});
                end
                if cfg.legend
                    legend(chan_names);
                end
            elseif strcmp(cfg.type,'stddev')
                if isempty([varargin{:}])
                    plot(ts, data_to_plot(avgIndex,:));
                else
                    plot(ts, data_to_plot(avgIndex,:),varargin{:});
                end
                if cfg.legend
                    legend(chan_names);
                end
            elseif strcmp(cfg.type,'both')
                if isempty([varargin{:}])
                    plot(ts, data_to_plot{1}(avgIndex,:), 'LineWidth', 2);
                    if cfg.legend
                        legend(chan_names);
                    end
                    hold on
                    plot(ts, data_to_plot{2}(avgIndex,:),':');
                    plot(ts, data_to_plot{3}(avgIndex,:),':');
                    hold off
                else
                    plot(ts, data_to_plot{1}(avgIndex,:), 'LineWidth', 2, varargin{:});
                    if cfg.legend
                        legend(chan_names);
                    end
                    hold on
                    plot(ts, data_to_plot{2}(avgIndex,:),':', varargin{:});
                    plot(ts, data_to_plot{3}(avgIndex,:),':', varargin{:});
                    hold off
                end
            end
            xlabel('Time [s]');
            unit = segStream.SourceInfoChannel.Unit{channel_idx};
            ylabel([unit_string unit],'Interpreter','tex')
            label = segStream.Info.Label{id};
            if isempty(label)
                title(['Average ID ' num2str(segStream.Info.SegmentID(id))]);
            else
                title(['Average label ' label])
            end
        end
    end
end