function plot(str, cfg, varargin)
% plot function for a McsCmosSpikeSorterSource object
%
% function plot(str, cfg, varargin)
%
% Produces an intensity map with colorbar and a list of all units. Units
% can be selected from the list or from the map and detailed Information 
% about them is displayed in a separate figure.
%
% Input:
%
%   str             -   A McsCmosSpikeSorterSource object
%
%   cfg             -   Either empty (for default parameters) or a
%                       structure with (some of) the following fields:
%                       'units': empty for default sensors, otherwise a
%                           vector indices of the detected units in the 
%                           source file. Selected unit information is displayed.
%                           (default: 'none')
%                       'labels': empty for default value, otherwise 
%                           'on' or 'off'. displayes the units with the 
%                           markers in the map.
%                           (default: 'off')
%                       'grid': empty for default value, otherwise 'on' or
%                           'off'. displayes the grid that divides the map into
%                           sensor fields (default: 'on')
%                       'markers': empty for default value, otherwise 
%                           'on' or 'off'. displayes markers in the
%                           location of the units
%                           (default: 'on')
%                       'overlay': empty for default value, otherwise 
%                           'STAImage'  : shows STAImage in the background
%                           'spikeCount': shows Spike counts as a heat map
%                                           in the background
%                           (default: 'STAImage')
%                       If fields are missing, their default values are used.
%
% Usage:
%   plot(str, cfg);
%   plot(str, cfg, ...);
%   str.plot(cfg);
%   str.plot(cfg, ...);
%
% (c) 2018 by Multi Channel Systems MCS GmbH  

%%  CHECK AND SET PROPER CONFIGURATION VALUES
%
    data        = [];
    data.cfg    = [];
    
    %Check whether 'units' configuration is among the allowed
    if isempty(double(str.UnitInfos.UnitID))
        error('No units found in file!');
    end
    [cfg, isDefaultUnits] = McsHDF5.checkParameter(cfg, 'units', []);
    if ~isDefaultUnits
        if ~ismember(cfg.units,double(str.UnitInfos.UnitID)) %any(cfg.units < 1 | cfg.units > size(sta.STAData,2))
            cfg.units = cfg.units(ismember(cfg.units,double(str.UnitInfos.UnitID)));
            if isempty(cfg.units)
                error('No units found!');
            else
                warning(['Using only selected units [ ' num2str(cfg.units) ' ] !']);
            end
        end
    end
    data.cfg.units = cfg.units;
     
    %Check whether 'labels' configuration is default
    [cfg, isDefaultLabels] = McsHDF5.checkParameter(cfg, 'labels', 'off');
    if ~isDefaultLabels && ~strcmp(cfg.labels,'off')
        cfg.labels = 'on';
    end
    data.cfg.labels = cfg.labels;
    
    %Check whether 'grid' configuration is default
    [cfg, isDefaultGrid] = McsHDF5.checkParameter(cfg, 'grid', 'on');
    if ~isDefaultGrid && ~strcmp(cfg.grid,'on')
        cfg.grid = 'off';
    end
    data.cfg.grid = cfg.grid;
    
    %Check whether 'markers' configuration is default
    [cfg, isDefaultMarkers] = McsHDF5.checkParameter(cfg, 'markers', 'on');
    if ~isDefaultMarkers && ~strcmp(cfg.markers,'on')
        cfg.markers = 'off';
    end
    data.cfg.markers = cfg.markers;
    
    %Check whether 'overlay' configuration is default
    [cfg, isDefaultOverlay] = McsHDF5.checkParameter(cfg, 'overlay', 'STAImage');
    if ~strcmp(cfg.overlay,'STAImage') && ~strcmp(cfg.overlay,'ROI') && ~strcmp(cfg.overlay,'spikeCount')
        warning('Configuration of "overlay" is not set to an allowed value. Use of default setting instead.');
        cfg.overlay = 'STAImage';
    end
    data.cfg.overlay = cfg.overlay;

% end section "CHECK AND SET PROPER CONFIGURATION VALUES"
%%  PREPARE FIGURE
%    
    %init figure
    fig   = gcf;
    clf(fig);
    position = get(fig,'Position');
    position(3) = position(3)*1.5;
    set(fig, ...
        'NumberTitle', 'off', ...
        'Name', 'Spike Sorter Results', ...
        'Tag','HeatMap', ...
        'WindowButtonDownFcn', @McsHDF5.McsCmosSpikeSorterSource.mapHandler);
%
%%  PREPARE AXES
    AX1_outerPosition   = [ 0.02 0.05 1 1 ];% for axes grid lines and ticks
    AX2_outerPosition   = AX1_outerPosition;% for axes with HeatMap rectangles
    AX3_outerPosition   = AX1_outerPosition;% for axes eith labels
    AX4_outerPosition   = AX1_outerPosition;% for image
    AX5_outerPosition   = AX1_outerPosition;% for location markers
%
%%  GET PARAMETERS
    sensorXDimension    = 65;
    sensorYDimension    = 65;
    data.SpikeSorterSource = str;
    data.visualizations = struct();
%
%%  CREATE CUSTOM GRIDLINES
    AX1     = axes();
    g_y     = 0:1:sensorYDimension+1; % user defined grid Y [start:spaces:end]
    g_x    	= 0:1:sensorXDimension+1; % user defined grid X [start:spaces:end]
    if strcmp(cfg.grid,'on')
        lineStyle = '-';
    else
        lineStyle = 'none';
    end
    for i=3:length(g_x)-1
        plot(AX1,[g_x(i) g_x(i)]-0.5,[g_y(1) g_y(end)]-0.5,'LineWidth',0.1,'Color',0.681+(1-0.681)*get(gcf,'Color'),'LineStyle',lineStyle) %y grid lines
        hold on
    end
    for i=3:length(g_y)-1
        plot(AX1,[g_x(1) g_x(end)],[g_y(i) g_y(i)]-0.5,'LineWidth',0.1,'Color',0.681+(1-0.681)*get(gcf,'Color'),'LineStyle',lineStyle) %x grid lines
        hold on
    end
%     % SET AXES PROPERTIES
     axis(([1 (sensorYDimension+1) 1 (sensorXDimension+1)]-0.5));
     set(AX1, 'OuterPosition', AX1_outerPosition,...
                'xtick', 0:10:sensorXDimension, ...
                'ytick', 0:10:sensorYDimension,...
              	'PlotBoxAspectRatioMode','manual', ...
              	'PlotBoxAspectRatio',[1 1 1], ...
              	'Color','none',...
              	'Ydir','reverse',...
               	'Tag','axesGridlines');
    xlabel('x')
    ylabel('y')
    
    data.gridlines = AX1;
%
%%  CREATE AXES, MARK SITES & SET UP ACTIVITY MATRIX
    % plot rectangles
    AX2 = axes(); %for HeatMap rectangles
    AX5 = axes(); %for location markers
    markers = 'none';
    if strcmp(cfg.markers,'on')
        markers = 'x';
    end
    
    %fetch coordinates, spike count, and labels and plot markers
    coordinates     = zeros(2,length(data.SpikeSorterSource.UnitInfos.UnitID));
    spikeCount      = zeros(1,length(data.SpikeSorterSource.UnitInfos.UnitID));
    txt             = cell(1,length(data.SpikeSorterSource.UnitInfos.UnitID));
    for i=1:1:length(data.SpikeSorterSource.UnitInfos.UnitID)
        coordinates(:,i) = double([ data.SpikeSorterSource.UnitInfos.Column(i) ; data.SpikeSorterSource.UnitInfos.Row(i) ]);
        spikeCount(i) = sum(data.SpikeSorterSource.UnitEntities{i}.Peaks.IncludePeak);
        txt{i}  = num2str(data.SpikeSorterSource.UnitInfos.UnitID(i));
    end
    %plot markers
    plot(AX5,coordinates(1,:),coordinates(2,:),'LineStyle','none','Color','black','Marker',markers);
    hold on
    set(AX5,'Color','none', ...
            'PlotBoxAspectRatioMode','manual', ...
            'PlotBoxAspectRatio',[1 1 1],...
            'xticklabel',{[]},...
            'yticklabel',{[]},...
            'xtick',[],...
            'ytick',[],...
            'OuterPosition',AX5_outerPosition,...
            'Ydir','reverse',...
            'Visible','off',...
            'Tag','axesHeatmapLocationMarkers');
    axis(([1 (sensorYDimension+1) 1 (sensorXDimension+1)]-0.5))
    
    %compute colors that signify spikeCount
    relativeSpikeCount  = spikeCount/max(spikeCount);
    redValue            = [ relativeSpikeCount ; zeros(size(relativeSpikeCount)) ; zeros(size(relativeSpikeCount)) ].';
	grayValue           = get(gcf,'Color');
    scaledRedValue      = bsxfun(@times,grayValue./max(grayValue,1),redValue);
    shiftedGrayValue    = bsxfun(@minus,grayValue,repmat(scaledRedValue(:,1),1,3));
    colors              = bsxfun(@plus,shiftedGrayValue,scaledRedValue);
    
    %draw activity rectanlges (HeatMap)
    axes(AX2);
    visible = 'off';
    if strcmp(cfg.overlay,'spikeCount')
        visible = 'on';
    end
    for i=1:length(data.SpikeSorterSource.UnitInfos.UnitID)
        %draw activity
        rectangle('Position',[coordinates(1,i)-0.5,coordinates(2,i)-0.5,1,1] ,...
                    'FaceColor', colors(i,:),...
                    'LineStyle','none',...
                    'LineWidth',1,...
                    'Visible',visible);
        hold on
    end
    set(AX2,'Color','none', ...
                'PlotBoxAspectRatioMode','manual', ...
                'PlotBoxAspectRatio',[1 1 1],...
                'OuterPosition',AX2_outerPosition,...
                'Ydir','reverse',...
                'Tag','axesHeatMapRectangles');
    axis(([1 (sensorYDimension+1) 1 (sensorXDimension+1)]-0.5));
    [A,I]   = sort(redValue(:,1));
    colors  = colors(I,:);
    colormap(AX2,colors);
    c                       = colorbar;
    set(c,'Visible',visible,...
                'Location','manual',...
                'Position',[0.1 0.115+AX1_outerPosition(2) 0.05 0.8],...
                'Visible',visible)

    data.markers            = AX5;
    data.activity           = AX2;
    
% plot labels
    AX3 = axes();
    labels = text(coordinates(1,:), coordinates(2,:), txt, ...
                    'HorizontalAlignment', 'center', ...
                    'VerticalAlignment', 'middle', ...
                    'FontUnits', 'normalized', ...
                    'FontSize', 2/sensorYDimension, ...
                    'FontWeight','bold',...
                    'Parent',AX3,...
                    'Color','black',...
                    'Visible',cfg.labels);
     set(AX3,'OuterPosition',AX2_outerPosition,...
                'Ydir','reverse',...
                'Visible','off',...
                'Tag','axesLabels',...
                'Color','none', ...
               	'PlotBoxAspectRatioMode','manual', ...
               	'PlotBoxAspectRatio',[1 1 1]);
     axis(([1 (sensorYDimension+1) 1 (sensorXDimension+1)]-0.5));
    
    data.labels = AX3;
%
%%  CREATE STA IMAGE
    AX4 = axes();
    visible = 'off';
    if strcmp(cfg.overlay,'STAImage')
        visible = 'on';
    end
    STAimage        = McsHDF5.McsCmosSpikeSorterSource.createSensorSTAImage(data.SpikeSorterSource);
    image           = STAimage.image;
    image           = interp2(image,2);
    colormap(AX4,jet);
    hImage          = imagesc(image,'Parent',AX4);
    axis image;
    set(AX4,'OuterPosition',AX4_outerPosition,...
                'Visible','off',...
                'Tag','axesSTA',...
                'Parent',fig,...
                'Color','none', ...
                'PlotBoxAspectRatioMode','manual', ...
              	'PlotBoxAspectRatio',[1 1 1],....
                'xticklabel',[],...
                'yticklabel',[],...
                'xtick',[],...
                'ytick',[])
    set(hImage,'Visible',visible);
    
    data.shownImage = hImage;
    data.STAImage   = STAimage;
    data.image      = AX4;
%
%end section "PLOT LOCALIZATION (AND ACTIVITY) OF SENSORS (HEATMAP)"
%%  CREATE LIST OF UNITS
    UnitIDs     = num2cell(double(str.UnitInfos.UnitID));
    UnitIDs     = cellfun(@(ID) sprintf('Unit %d',ID), UnitIDs,'UniformOutput',false);

    list        = uicontrol(fig,'Style','listbox',...
                                'Units','normalized', ...
                                'Position',[ 0.86 0.115+AX1_outerPosition(2) 0.12 0.8 ], ...
                                'String', UnitIDs.', ...
                                'FontUnits','normalized', ...
                                'Callback',@McsHDF5.McsCmosSpikeSorterSource.listHandler, ...
                                'Max',5, ...
                                'Min',1);
    data.list   = list;
%
%%  CREATE PLOTS OF SELECTED UNITS
    for unit=1:1:length(cfg.units)
        index = find(double(str.UnitInfos.UnitID==cfg.units(unit)));
        figure();
        data.visualizations.(['ID' num2str(double(str.UnitInfos.SensorID(index)))]) = plot(str.UnitEntities{index},[]);
    end
%
%%  CREATE CFG CHECKBOXES & OVERLAY POPUPMENU
    checkboxLabels          = uicontrol(fig,'Style','checkbox',...
                                            'Units','normalized', ...
                                            'Position',[ 0.02 0.01 0.25 0.05 ],...
                                            'String','Sensor Labels',...
                                            'Tag','labels',...
                                            'BackgroundColor',get(fig,'Color'),...
                                            'Callback',@McsHDF5.McsCmosSpikeSorterSource.checkboxHandler);
    if strcmp(cfg.labels,'on')
        set(checkboxLabels,'Value',1)
    end
    data.checkboxLabels = checkboxLabels;
    
    checkboxGrid          = uicontrol(fig,'Style','checkbox',...
                                            'Units','normalized', ...
                                            'Position',[ 0.27 0.01 0.25 0.05 ],...
                                            'String','Grid',...
                                            'Tag','grid',...
                                            'BackgroundColor',get(fig,'Color'),...
                                            'Callback',@McsHDF5.McsCmosSpikeSorterSource.checkboxHandler);
    if strcmp(cfg.grid,'on')
        set(checkboxGrid,'Value',1)
    end
    data.checkboxGrid = checkboxGrid;

    popupmenuOverlay      = uicontrol(fig,'Style','popupmenu',...
                                            'Units','normalized', ...
                                            'Position',[ 0.52 0.01 0.15 0.05 ],...
                                            'String',{'STA Image','Spike Count'},...
                                            'Tag','overlay',...
                                            'Callback',@McsHDF5.McsCmosSpikeSorterSource.checkboxHandler);
    switch cfg.overlay
        case 'STAImage'
            set(popupmenuOverlay,'Value',1)
        case 'spikeCount'
            set(popupmenuOverlay,'Value',2)
        otherwise
            set(popupmenuOverlay,'Value',1)
    end
    data.popupmenuOverlay = popupmenuOverlay;
    
    checkboxMarkers       = uicontrol(fig,'Style','checkbox',...
                                            'Units','normalized', ...
                                            'Position',[ 0.77 0.01 0.25 0.05 ],...
                                            'String','Sensor Markers',...
                                            'Tag','markers',...
                                            'BackgroundColor',get(fig,'Color'),...
                                            'Callback',@McsHDF5.McsCmosSpikeSorterSource.checkboxHandler);
    if strcmp(cfg.markers,'on')
        set(checkboxMarkers,'Value',1)
    end
    data.checkboxMarkers = checkboxMarkers;
%
%%  CREATE STACKING ORDER
    uistack(AX2,'bottom');
    uistack(AX4,'bottom');
    uistack(AX3,'top')
%
%% HANDLE OLD MATLAB COLORMAP ISSUES
    
    if strcmp(cfg.overlay,'spikeCount')
        colormap(AX2,colors);
                            
        lim                     = get(c,'YLim');
        offset                  = lim(1);
        ticks                   = [0:0.1:1]*(lim(2)-lim(1))+offset;
        ticklabels              = [0:0.1:1]*max(spikeCount);
        n                       = floor(log10(max(spikeCount)))-1;
        ticklabels           	= round(ticklabels*10^(-n))*10^n;
        ticklabels              = arrayfun(@num2str,ticklabels,'UniformOutput',false);
       	set(c,'Tag','colbarSpikeCount',...
                'ytickmode','manual',...
                'yticklabelmode','manual',...
                'YTick',ticks,...
                'YTickLabel',ticklabels);
        ylabel(c,'Spike Count');
    else
        colormap(AX4,jet);
    end
    data.colbar             = c;
    data.colormapSTA        = jet;
    data.colormapSpikeCount = colors;
    data.spikeCount         = spikeCount;
    data.colorbarPosition   = [0.1 0.115+AX1_outerPosition(2) 0.05 0.8];
%
%%  STORE RELVANT INFORMATION WITH FIGURE
    guidata(fig,data);
%end section "STORE RELEVANT INFORMATION WITH FIGURE
end