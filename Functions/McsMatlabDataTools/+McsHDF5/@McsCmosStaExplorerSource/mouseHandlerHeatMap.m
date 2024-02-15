function mouseHandlerHeatMap(src, evt)
% function mouseHandlerHeatMap(src, evt)
%
% Is triggered when the mouse is clicked in the HeatMap figure. Reads
% the current mouse position, translates it to a sensor ID and visualizes
% (if matches unit in sta data) its neighborhood and its activity

%SET PARAMETERS
unit    = [];

%TEST CLICK TYPE
    if strcmp(get(src, 'SelectionType'), 'normal')
        pt = get(get(src,'CurrentAxes'),'CurrentPoint');
        
        x = pt(1,1);
        y = pt(1,2);
        x = round(min(x, 65));
        y = round(min(y, 65));
        
        data = guidata(src);
        
        inY     = data.neighborhood(2);
        inX     = data.neighborhood(1);
        
        sens    = McsHDF5.coordinates2ID([x;y], data.sensorDimension(2), data.sensorDimension(1));
        field   = ['ID' num2str(sens)];
        
        if sens > 0 && sens <= data.sensorDimension(1)*data.sensorDimension(2)
            if find(data.IDs == sens) %check if valid (aka marked in plot) unit is clicked
                unit = find(data.IDs==sens);
                unit = unit(1);
                if isfield(data.visualization,(field)) %check if figure showing that sensor is already openif isgraphics(data.visualization.(field).neighborhood,'figure')
                    if isgraphics(data.visualization.(field),'figure')%check if both figures exist
                        figure(data.visualization.(field).singleUnit);
                    else%plot both graphs
                        data.visualization.(field).singleUnit       = McsHDF5.McsCmosStaExplorerSource.plotSingleSensor(src, unit, [x;y]);
                    end
                else%create (field)s and graphs
                    data.visualization.(field).singleUnit       = McsHDF5.McsCmosStaExplorerSource.plotSingleSensor(src, unit, [x;y]);
                end
                guidata(src, data);
            else
                if strcmp(data.labels,'on')
                    data.labels = 'off';
                else
                    data.labels = 'on';
                end
                AX_markers = findobj(get(src,'Children'),'Tag','markers');
                set(findobj(AX_markers,'Type','Text'),'Visible',data.labels);
                guidata(src, data);
            end
        end
    end
end

