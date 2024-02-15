function mapHandler(src, evt)
% function mouseHandlerHeatMap(src, evt)
%
% Is triggered when the mouse is clicked in the HeatMap figure. Reads
% the current mouse position, translates it to a sensor ID and plots
% (if matches unit in sta data) its SpikeSorterUnit plot into a separate
% figure

%% PARAMETERS
    sensorXDimension    = 65;
    sensorYDimension    = 65;
    
    data                = guidata(src);
    ID                  = double(data.SpikeSorterSource.UnitInfos.SensorID);
%

%TEST CLICK TYPE
    if strcmp(get(src, 'SelectionType'), 'normal')
        pt = get(get(src,'CurrentAxes'),'CurrentPoint');
        
        x = pt(1,1);
        y = pt(1,2);
        x = round(min(x, 65));
        y = round(min(y, 65));

        sens    = McsHDF5.coordinates2ID([x;y], sensorYDimension, sensorXDimension);
        field   = ['ID' num2str(sens)];
        
        if sens > 0 && sens <= sensorXDimension*sensorYDimension
            if find(ID == sens) %check if valid (aka marked in plot) unit is clicked
                unit = find(ID==sens);
                unit = unit(1);
                if isfield(data.visualizations,(field)) %check if figure showing that sensor is already open
                    if isgraphics(data.visualizations.(field),'figure')
                        figure(data.visualizations.(field));
                    else %plot neighborhood graph and save in structure
                        figure();
                        data.visualizations.(field)	= plot(data.SpikeSorterSource.UnitEntities{unit},[]);
                    end
                else%create (field)s and graphs
                    figure();
                    data.visualizations.(field) = plot(data.SpikeSorterSource.UnitEntities{unit},[]);
                end
                guidata(src, data);
            else
                disp('No unit at this position!');
            end
        end
    end
end

