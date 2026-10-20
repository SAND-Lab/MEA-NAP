function checkboxHandler(src, evt)
% function mouseHandlerHeatMap(src, evt)
%
% Is triggered when the mouse is clicked in the HeatMap figure. Reads
% the current mouse position, translates it to a sensor ID and visualizes
% (if matches unit in sta data) its neighborhood and its activity

%% FETCH PARAMETER
    fig     = get(src,'Parent');
    boxType  = get(src,'Tag');
    data    = guidata(fig);
    value   = get(src,'Value');
%
%% CHANGE VISIBILITY 'visible' -> 'invisible' or 'invisible' -> 'visible'
    if value
        lineStyle   = '-';
        visible     = 'on';
        marker      = 'x';
    else
        lineStyle   = 'none';
        visible     = 'off';
        marker      = 'none';
    end
%
%% TEST CLICK TYPE AND SELECT CONTROLLED AXES
    switch boxType
        case 'labels'
            children	= get(data.labels,'Children');
            set(findobj(children,'Type','Text'),'Visible',visible);
        case 'grid'
            children	= get(data.gridlines,'Children');
            set(findobj(children,'Type','line'),'LineStyle',lineStyle);
        case 'overlay'
            % turn everything invisible
            children                    = get(data.image,'Children');
            set(findobj(children,'Type','image'),'Visible','off');
            set(findobj(get(fig,'Children'),'Type','colorbar','-and','Tag','colbarSpikeCount'),'Visible','off');
            %for older MATLAB Versions
            set(findobj(get(fig,'Children'),'Tag','colbarSpikeCount'),'Visible','off');
            set(data.colbar,'Visible','off');
            %
            children                    = get(data.activity,'Children');
            set(findobj(children,'Type','Rectangle'),'Visible','off');
            % turn selection visible in popupmenu
            selection   = get(src,'String');
            value       = get(src,'Value');
            switch selection{value}
                case 'STA Image'
                    children                    = get(data.image,'Children');
                    set(findobj(children,'Type','image'),'Visible','on');
                    colormap(data.image,data.colormapSTA);
                case'Spike Count'
                    children                    = get(data.activity,'Children');
                    set(findobj(children,'Type','Rectangle'),'Visible','on');
                    set(findobj(get(fig,'Children'),'Type','colorbar','-and','Tag','colbarSpikeCount'),'Visible','on');
                    
                    
                    %for older MATLAB Version
                    set(findobj(get(fig,'Children'),'Tag','colbarSpikeCount'),'Visible','on');
                    set(data.colbar,'Visible','on');
                    colormap(data.activity,data.colormapSpikeCount);

                    lim                     = get(data.colbar,'YLim');
                    offset                  = lim(1);
                    ticks                   = [0:0.1:1]*(lim(2)-lim(1))+offset;
                    ticklabels              = [0:0.1:1]*max(data.spikeCount);
                    n                       = floor(log10(max(data.spikeCount)))-1;
                    ticklabels           	= round(ticklabels*10^(-n))*10^n;
                    ticklabels              = arrayfun(@num2str,ticklabels,'UniformOutput',false);
                    set(data.colbar,'YTick',ticks,'YTickLabel',ticklabels);
                    ylabel(data.colbar,'Spike Count');
                    %
                otherwise
            end
        case 'markers'
            children                    = get(data.markers,'Children');
            set(findobj(children,'Type','line'),'Marker',marker);
    end
%
%% WRITE BACK DATA
    guidata(fig,data);
%
end