function plot(staObject, cfg, varargin)
% Plot the contents of a McsCmosStaExplorerSource object.
%
% function plot(analogStream,cfg,varargin)
%
% Produces a time series plot for each identified unit in the object.
%
% INPUT:
%
%   staObject       -   A McsCmosStaExplorerSource object
%
%   cfg             -   Either empty (for default parameters) or a
%                       structure with (some of) the following fields:
%                       'sta': empty for default sensors, otherwise a
%                           vector of indices of the detected STAs in the HDF5 file(default: no STAs shown)
%                       'neighborhood': empty for default sensors, otherwise a 2x1
%                           vector that defines the size of the
%                           neighborhood that is to be shown around the
%                           unit of interest (default: [3 3])
%                       'labels': empty for default value, otherwise 
%                           'on' or 'off'. Displayes the labels of the specified type.
%                           (default: 'off')
%                       'labelType': empty for default, otherwise
%                           'sourceID' to show source's ID
%                           'sensorID' to show sensor's ID
%                           'storageIdx' to show index of sensor in file
%                           (default: storageIdx)
%                       If fields are missing, their default values are used.
%
%   Optional inputs in varargin are passed to the plot function.
%
% Usage:
%   plot(staObject, cfg);
%   plot(staObject, cfg, ...);
%   staObject.plot(cfg);
%   staObject.plot(cfg, ...);
% 
%
% (c) 2018 by Multi Channel Systems MCS GmbH

    clf
    
    %% CHECK AND SET PROPER CONFIGURATION VALUES
    
    %Check whether 'sta' configuration is default
    defaultSTAs = 1:1:length(staObject.STAData);
    %Check whether 'sta' configuration is among the allowed
    if isempty(defaultSTAs)
        error('No STAs found!');
    end
    [cfg, isDefaultSTAs] = McsHDF5.checkParameter(cfg, 'sta', []);
    if isDefaultSTAs
        cfg.sta = defaultSTAs;
    else
        if any(cfg.sta < 1 | cfg.sta > length(staObject.STAData))
            cfg.sta = cfg.sta(cfg.sta >= 1 & cfg.sta <= length(staObject.STAData));
            if isempty(cfg.sta)
                error('No STAs found!');
            else
                warning(['Using only selected STAs indices between ' num2str(cfg.sta(1)) ' and ' num2str(cfg.sta(end)) '!']);
            end
        end
    end
    
    %trim 'neighborhood' to allowed size
    [cfg] = McsHDF5.checkParameter(cfg, 'neighborhood', [3 3]);
    if cfg.neighborhood(1)<1
        cfg.neighborhood(1) = 1;
    end
    if cfg.neighborhood(1)> size(staObject.STAData{1},2)
        cfg.neighborhood(1)= size(staObject.STAData{1},2);
    end
    if cfg.neighborhood(2)<1
        cfg.neighborhood(2) = 1;
    end
    if cfg.neighborhood(2)> size(staObject.STAData{1},1)
        cfg.neighborhood(2)= size(staObject.STAData{1},1);
    end
    
    %Check whether 'labels' configuration is default
    [cfg, isDefaultLabels] = McsHDF5.checkParameter(cfg, 'labels', 'off');
    if ~strcmp(cfg.labels,'on') || ~strcmp(cfg.labels,'on')
        cfg.labels = 'off';
    end
    data.labels = cfg.labels;
    
    %Check whether 'labelType' configuration is default
    [cfg, isDefaultSensorLabel] = McsHDF5.checkParameter(cfg, 'labelType', 'storageIdx');
    if ~(strcmp(cfg.labelType,'sensorID') || strcmp(cfg.labelType,'storageIdx') || strcmp(cfg.labelType,'sourceID'))
        warning('Default Label (storageIdx) is displayed in HeatMap');
        cfg.labelType = 'storageIdx';
    end
    %end section "CHECK AND SET PROPER CONFIGURATION VALUES"
    %% GET REOCCURING PARAMETERS
    sensorDimension = [ size(staObject.STAData{1},2) ; size(staObject.STAData{1},1) ]; %[ width ; height ] or [ x-direction in plot y-direction in plot ]
    totalUnit_num   = size(staObject.STAData,2);
    coordinates     = zeros(2,totalUnit_num);
    SourceIDs       = zeros(1,totalUnit_num);
    IDs             = zeros(1,totalUnit_num);
    UnitActivity    = zeros(1,totalUnit_num);
    for unit=1:totalUnit_num
        IDs(unit)          = staObject.STAInfos{unit}.SensorID;
        coordinates(:,unit)= McsHDF5.ID2coordinates( IDs(unit) , sensorDimension(1) , sensorDimension(2));
        SourceIDs(unit)    = staObject.STAInfos{unit}.SourceID;
        UnitActivity(unit) = staObject.STAInfos{unit}.Sweeps;
    end
    % end of section "GET REOCCURING PARAMETERS"
    %% DATA VISUALIZATION
    if exist('gobjects')
        visualization = struct('localizationFig', gobjects(1));
    else
        visualization = struct('localizationFig', 0);
    end
    % end of initialization for "DATA VISUALIZATION"
    %% PLOT LOCALIZATION (AND ACTIVITY) OF SENSORS (HEATMAP)
    % plots a HeatMap of the selected accessible sta, which are selected
    % by the user
    
    %create figure
    visualization.localizationFig   = gcf;
    set(visualization.localizationFig, ...
        'NumberTitle', 'off', ...
        'Name', 'HeatMap - Sensor Activity and Location', ...
        'Tag','HeatMap', ...
        'WindowButtonDownFcn', @McsHDF5.McsCmosStaExplorerSource.mouseHandlerHeatMap);
    data.visualization            = visualization;
    data.Function                 = @plotHeatMap;
    data.unitActivity             = UnitActivity;
    data.sensorDimension          = sensorDimension;
    data.IDs                      = IDs;
    data.coordinates              = coordinates;
    data.sourceIDs                = SourceIDs;
    data.STAData                  = staObject.STAData;
    data.sweeps                   = cellfun(@(x)(x.Sweeps),staObject.STAInfos);
    data.neighborhood             = cfg.neighborhood;
    data.labelType                = cfg.labelType;
    data.labels                   = cfg.labels;
    guidata(visualization.localizationFig, data);
    %store current state of data
    McsHDF5.McsCmosStaExplorerSource.plotHeatMap(visualization.localizationFig, coordinates, UnitActivity, sensorDimension);
    %retrieve current state of data
    data = guidata(visualization.localizationFig);
    %end section "PLOT LOCALIZATION (AND ACTIVITY) OF SENSORS (HEATMAP)"
    %% PLOT SELECTED STAs
    if ~isDefaultSTAs
        for unit=1:length(cfg.sta)
            data.visualization.(['ID' num2str(IDs(unit))]).singleUnit       = McsHDF5.McsCmosStaExplorerSource.plotSingleSensor(gcf,cfg.sta(unit), McsHDF5.ID2coordinates(IDs(cfg.sta(unit)), sensorDimension(1), sensorDimension(2)));
        end
    end
%% STORE DATA STRUCT WITH FIGURE
    guidata(visualization.localizationFig, data);
%
end