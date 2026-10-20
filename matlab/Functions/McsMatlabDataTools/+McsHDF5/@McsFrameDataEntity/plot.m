function plot(frame,cfg,varargin)
% Plot the contents of a McsFrameDataEntity object.
%
% function plot(frame,cfg,varargin)
%
% Will either produce a 3D figure of the channel amplitudes at a single
% time point, or a 2D matrix of plots, each showing the signal of a single
% channel for a given time range.
%
% Input:
%
%   frame       - A McsFrameDataEntity object.
%
%   cfg         -   Either empty (for default parameters) or a
%                   structure with (some of) the following fields:
%                   'channelMatrix': empty for all channels, otherwise a
%                       matrix of bools with size channels_x x channels_y.
%                       All channels with 'true' entries in this matrix are
%                       used in the plots. (default: all channels)
%                   'window': empty for the whole time range, otherwise
%                       either a vector with two entries: [start end] of
%                       the time range, both in seconds, or a scalar: a
%                       time point in seconds. If a range is given, the
%                       signal of each channel in this range is plotted
%                       individually. For a single time plot, a 2D/3D image
%                       over all channels is generated.
%               If fields are missing, their default values are used.
%
%   Optional inputs in varargin are passed to the plot function.
%
% Usage:
%
%   plot(frame, cfg);
%   plot(frame, cfg, ...);
%   frame.plot(cfg);
%   frame.plot(cfg, ...);
%
% (c) 2016 by Multi Channel Systems MCS GmbH

    clf
    
    cfg = McsHDF5.checkParameter(cfg, 'window', ...
        McsHDF5.TickToSec([frame.FrameDataTimeStamps(1) frame.FrameDataTimeStamps(end)]));
    [cfg, isDefault] = McsHDF5.checkParameter(cfg, 'channelMatrix', true(size(frame.FrameData,1),size(frame.FrameData,2)));
    if ~isDefault
        if size(cfg.channelMatrix,1) ~= size(frame.FrameData,1) || size(cfg.channelMatrix,2) ~= size(frame.FrameData,2)
            error('Size of cfg.channelMatrix does not match the number of channels in the file!');
        end
    end
    
    if numel(cfg.window) == 1 || cfg.window(1) == cfg.window(2)
        % plot single time point as a 3D visualization
        
        idx = find(abs(frame.FrameDataTimeStamps - McsHDF5.SecToTick(cfg.window(1))) <= frame.Info.Tick);
        if isempty(idx)
            warning('No data point found!')
            return;
        elseif numel(idx) > 1
            [ignore,tmp] = min(abs(frame.FrameDataTimeStamps(idx) - McsHDF5.SecToTick(cfg.window(1))));
            idx = idx(tmp);
        end
        
        if strcmp(frame.DataType,'raw')
            cfg_part = [];
            cfg_part.window = McsHDF5.TickToSec([frame.FrameDataTimeStamps(idx) frame.FrameDataTimeStamps(idx) + frame.Info.Tick - 1]);
            tmp_frame = frame.readPartialFrameData(cfg_part);
            cfg_conv = [];
            cfg_conv.dataType = 'double';
            data_to_plot = tmp_frame.getConvertedData(cfg_conv);
        elseif strcmp(frame.DataType,'single')
            data_to_plot = cast(frame.FrameData(:,:,idx),'double');
        else
            data_to_plot = frame.FrameData(:,:,idx);
        end
        
        orig_exp = log10(max(abs(data_to_plot(cfg.channelMatrix(:)))));
        unit_exp = double(frame.Info.Exponent);

        [fact,unit_string] = McsHDF5.ExponentToUnit(orig_exp+unit_exp,orig_exp);

        data_to_plot = squeeze(data_to_plot * fact);
        data_to_plot(~cfg.channelMatrix) = NaN;

        [X,Y] = meshgrid(1:size(data_to_plot,2),1:size(data_to_plot,1));
        if isempty([varargin{:}])
            surf(X,Y,data_to_plot);
        else
            surf(X,Y,data_to_plot,varargin{:});
        end
        xlabel('y channels')
        ylabel('x channels')
        zlabel([unit_string frame.Info.Unit{1}],'Interpreter','tex')
        title(['Time: ' num2str(cfg.window(1)) ' [s]'])
    else
        % plot time range with a 2D array of plots, each plot showing the
        % time series in the time range for a specific channel.
        start_index = find(frame.FrameDataTimeStamps >= McsHDF5.SecToTick(cfg.window(1)),1,'first');
        end_index = find(frame.FrameDataTimeStamps <= McsHDF5.SecToTick(cfg.window(2)),1,'last');

        if end_index < start_index
            warning('No time range found')
            return
        end

        timestamps = McsHDF5.TickToSec(frame.FrameDataTimeStamps(start_index:end_index));
        
        if ~strcmp(frame.DataType,'raw')

            num_x = size(frame.FrameData,1);
            num_y = size(frame.FrameData,2);

            left = 0.08;
            bottom = 0.08;

            width = (1-left)/(1.1*num_x+0.1);
            spacing_x = 0.1*width;
            height = (1-bottom)/(1.1*num_y+0.1);
            spacing_y = 0.1*height;
            
            range_y = [Inf -Inf];
            % this is slower but more memory efficient than indexing the
            % cube
            for xi = 1:num_x
                for yi = 1:num_y
                    if cfg.channelMatrix(xi,yi)
                        vals = squeeze(frame.FrameData(xi,yi,start_index:end_index));
                        if min(vals) < range_y(1)
                            range_y(1) = min(vals);
                        end
                        if max(vals) > range_y(2)
                            range_y(2) = max(vals);
                        end
                    end
                end
            end
            
            orig_exp = log10(range_y(2));
            unit_exp = double(frame.Info.Exponent);

            [fact,unit_string] = McsHDF5.ExponentToUnit(orig_exp+unit_exp,orig_exp);
            range_y = range_y * fact;

            for xi = 1:num_x
                for yi = 1:num_y
                    if cfg.channelMatrix(xi,yi)
                        axes('position',[left+xi*spacing_x+(xi-1)*width,...
                                        1-(yi*spacing_y+yi*height),...
                                        width,height]);
                        if isempty([varargin{:}])
                            plot(timestamps,squeeze(frame.FrameData(xi,yi,start_index:end_index))*fact);
                        else
                            plot(timestamps,squeeze(frame.FrameData(xi,yi,start_index:end_index))*fact,varargin{:});
                        end
                        axis([timestamps(1) timestamps(end) range_y(1) range_y(2)]);
                        if xi > 1 && yi < num_y
                            axis off
                        else
                            set(gca,'Box','off');
                            set(gca,'color',get(gcf,'Color'))
                        end
                        if yi == num_y
                            xlabel('Time [s]')
                            if xi ~= 1
                                set(gca,'YTick',[])
                                set(gca,'YColor',get(gcf,'Color'))
                            end
                        end
                        if xi == 1
                            ylabel([unit_string frame.Info.Unit{1}],'Interpreter','tex')
                            if yi ~= num_y
                                set(gca,'XTick',[])
                                set(gca,'XColor',get(gcf,'Color'))
                            end
                        end
                    end
                end
            end
        else
            cfg_conv = [];
            cfg_conv.dataType = 'double';
            data_to_plot = frame.getConvertedData(cfg_conv);
            orig_exp = log10(max(max(max(abs(data_to_plot(:,:,start_index:end_index))))));
            unit_exp = double(frame.Info.Exponent);

            [fact,unit_string] = McsHDF5.ExponentToUnit(orig_exp+unit_exp,orig_exp);

            num_x = size(frame.FrameData,1);
            num_y = size(frame.FrameData,2);

            left = 0.08;
            bottom = 0.08;

            width = (1-left)/(1.1*num_x+0.1);
            spacing_x = 0.1*width;
            height = (1-bottom)/(1.1*num_y+0.1);
            spacing_y = 0.1*height;

            idx = repmat(find(cfg.channelMatrix),1,length(start_index:end_index));
            offs = ((start_index:end_index) - 1) * numel(cfg.channelMatrix);
            idx = bsxfun(@plus,idx,offs);
            range_y = [min(data_to_plot(idx(:))), max(data_to_plot(idx(:)))]*fact;

            for xi = 1:num_x
                for yi = 1:num_y
                    if cfg.channelMatrix(xi,yi)
                        axes('position',[left+xi*spacing_x+(xi-1)*width,...
                                        1-(yi*spacing_y+yi*height),...
                                        width,height]);
                        if isempty([varargin{:}])
                            plot(timestamps,squeeze(data_to_plot(xi,yi,start_index:end_index))*fact);
                        else
                            plot(timestamps,squeeze(data_to_plot(xi,yi,start_index:end_index))*fact,varargin{:});
                        end
                        axis([timestamps(1) timestamps(end) range_y(1) range_y(2)]);
                        if xi > 1 && yi < num_y
                            axis off
                        else
                            set(gca,'Box','off');
                            set(gca,'color',get(gcf,'Color'))
                        end
                        if yi == num_y
                            xlabel('Time [s]')
                            if xi ~= 1
                                set(gca,'YTick',[])
                                set(gca,'YColor',get(gcf,'Color'))
                            end
                        end
                        if xi == 1
                            ylabel([unit_string frame.Info.Unit{1}],'Interpreter','tex')
                            if yi ~= num_y
                                set(gca,'XTick',[])
                                set(gca,'XColor',get(gcf,'Color'))
                            end
                        end
                    end
                end
            end
        end
    end

end