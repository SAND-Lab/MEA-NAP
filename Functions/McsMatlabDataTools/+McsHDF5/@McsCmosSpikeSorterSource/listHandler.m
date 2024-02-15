function listHandler(src, evt)
% function mouseHandlerHeatMap(src, evt)
%
% Is triggered when the mouse is clicked in the HeatMap figure. Reads
% the current mouse position, translates it to a selectedIDsor ID and visualizes
% (if matches unit in sta data) its neighborhood and its activity

%% PARAMETERS
    selection   = get(src,'Value');
    fig      = get(src,'Parent');
    data = guidata(fig);

    selectedIDs    = data.SpikeSorterSource.UnitInfos.UnitID(selection);
    field   = arrayfun(@(ID) ['ID' num2str(ID)], selectedIDs, 'UniformOutput', false);
%
%% PLOT SPIKESORTERUNIT DATA FOR EACH SELECTED UNIT
    for unit=1:1:length(selection)
        if isfield(data.visualizations,(field{unit})) %check if figure showing that selectedIDsor is already open
            if isgraphics(data.visualizations.(field{unit}),'figure')%plot neighborhood graph and save in structure
                figure(data.visualizations.(field{unit}));
            else
                figure();
                data.visualizations.(field{unit})	= plot(data.SpikeSorterSource.UnitEntities{selectedIDs(unit)},[]);
            end
        else%create (field)s and graphs
            figure();
            data.visualizations.(field{unit})	= plot(data.SpikeSorterSource.UnitEntities{selectedIDs(unit)},[]);
        end
    end
%
%% STORE DATA BACK INTO FIGURE
    guidata(fig, data);
%
end

