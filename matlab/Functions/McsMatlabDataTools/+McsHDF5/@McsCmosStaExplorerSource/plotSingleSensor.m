function fig = plotSingleSensor(parentFIG,UOI,coordinates)
%Plots a figure with 3 axes
%   (1) The signal of all direct neighboor of a UOI within a neighborhood
%       specified by the user
%   (2) The signal of the UOI itself in large
%   (3) STA Video corresponding to that unit of the entire chip
%
% INPUT:
%
%   parentFIG       -   figure from which the function is called by 
%                       clicking
%
%   UOI             -   ID or index of the sensor/unit of interest
%
%   coordinates     -   coordinates of the sensor of interest
%
%
% OUTPUT:
%
%   fig             - handle to the figure newly created
%
%
%
% (c) 2018 by Multi Channel Systems MCS GmbH

%%  PARAMETERS
    data = guidata(parentFIG);
    inX             = data.neighborhood(1);
    inY             = data.neighborhood(2);
%
%%  INIT FIGURE
    fig = figure('NumberTitle', 'off', 'Name', sprintf('Sensor (%d,%d)',coordinates(1),coordinates(2)), 'Tag','Unit', 'WindowButtonDownFcn', @McsHDF5.McsCmosStaExplorerSource.mouseSingleSensor);
    set(fig, 'WindowButtonDownFcn',@McsHDF5.McsCmosStaExplorerSource.mouseSingleSensor);
%
%%  CREATE LAYOUT
%compute spacing and positions
    posFIG      = get(fig,'Position');
    spacing     = 0.03;%convert to relative coordinates
    newWidth    = 1/3;
    posFIG(3)   = 2.5*560; %triple (hopefully) standard figure width
    set(fig,'Position',posFIG);
    startingX   = spacing;
    newWidth    = newWidth-4/3*spacing; %adjusted to neighborhood
    posAX1      = [startingX                              0.1100    newWidth    0.8150]; %set modified standard axes position for neighborhood plot
    posAX2      = [(startingX+(spacing+newWidth))         0.1100    newWidth    0.8150]; %set modified standard axes position for single unit plot
    posAX3      = [(startingX+2*(spacing+newWidth))       0.1100    newWidth    0.8150]; %set modified standard axes position for video
%visualization.unitFigs(unit) = fig; %visualization.unitFigs(find(cfg.units == SourceIDs(unit)))
%%  PLOT UNIT NEIGHBORHOOD

    base_coordinate = coordinates - abs([ floor(inX/2) ; floor(inY/2)] );%oben links
    windowX         = base_coordinate(1):1:base_coordinate(1)+inX-1;
    windowX         = windowX( windowX>=1 & windowX<=data.sensorDimension(2) );
    inX             = length(windowX);
    windowY         = base_coordinate(2):1:base_coordinate(2)+inY-1;
    windowY         = windowY( windowY>=1 & windowY<=data.sensorDimension(1) );
    inY             = length(windowY);
    ROI             = data.STAData{UOI};
    ROI             = ROI(windowY, windowX,:);
    ROI             = ROI / double(data.sweeps(UOI));
    
    orig_exp = log10(max(abs(ROI(:))));
    unit_exp = -9;
    [fact,unit_string] = McsHDF5.ExponentToUnit(orig_exp+unit_exp,orig_exp);
    ROI = ROI * fact;
    
    maxValue        = max(max(max(ROI)));
    minValue        = min(min(min(ROI)));
    
    left        = posAX1(1);
    bottom      = posAX1(2);

    width = posAX1(3)/(1.1*inX+0.1);
    spacing_x = 0.1*width;
    height = posAX1(4)/(1.1*inY+0.1);
    spacing_y = 0.17*height;
    plot_num        = 1;
    for yi=1:1:inY
        for xi=1:inX
            ax = axes();
            set(ax,'Units','normalized',...
                                'Parent',fig,...
                                'Position',[left+xi*spacing_x+(xi-1)*width,...
                                    (1-0.2*bottom)-(yi*spacing_y+yi*height),...
                                    width,...
                                    height]);
            plot_num = plot_num+1;
            plot(ax,squeeze(ROI(yi,xi,:)));
            axis([0 size(ROI,3) minValue-abs(maxValue-minValue)*0.1 maxValue+ abs(maxValue-minValue)*0.1])
            title(['(' num2str(base_coordinate(1)+xi-1) ',' num2str(base_coordinate(2)+yi-1) ')'],'Fontweight','normal','FontSize',10);
            set(ax,'Tag','neighborhood');
            if xi > 1 && yi < inY
                set(ax,'color',get(gcf,'Color'),...
                        'XColor',get(gcf,'Color'),...
                        'YColor',get(gcf,'Color'),...
                        'xticklabel',{[]},...
                        'yticklabel',{[]});
                 box(ax,'off');
                %set(ax,'Visible','off')
                 %axis off;
            else
                set(gca,'Box','off');
                set(gca,'color',get(gcf,'Color'))
            end
            if xi==coordinates(1)-base_coordinate(1)+1 && yi==coordinates(2)-base_coordinate(2)+1
                color = get(gcf,'Color');
            	set(ax,'color',0.85*color);
            end
            if yi == inY
                xlabel('Time [µs]')
                if xi ~= 1
                    set(gca,'YTick',[])
                    set(gca,'YColor',get(gcf,'Color'))
                end
            end
            if xi == 1
                ylabel(['Voltage [' unit_string 'V]'])
                if yi ~= inY
                    set(gca,'XTick',[])
                    set(gca,'XColor',get(gcf,'Color'))
                end
            end
        end
    end
%
%%  PLOT UNIT ACTIVITY
    STAData     = data.STAData{UOI};
    UnitOIData  = reshape(STAData(coordinates(2),coordinates(1),:),[1,size(STAData,3)]);
    UnitOIData  = UnitOIData / double(data.sweeps(UOI));
    orig_exp = log10(max(abs(UnitOIData(:))));
    unit_exp = -9;
    [fact,unit_string] = McsHDF5.ExponentToUnit(orig_exp+unit_exp,orig_exp);
    UnitOIData = UnitOIData * fact;
    AX2         = axes();
    set(AX2,'Parent',fig,'OuterPosition',posAX2,'Units','normalized');
    plot(AX2,UnitOIData)
    xlabel('Time [µs]')
    ylabel(['Voltage [' unit_string 'V]'])
    title(sprintf('Sensor Signal (%d,%d)',coordinates(1),coordinates(2)))
    linehandle = line([1 1],ylim,'LineStyle','--','LineWidth',1,'Color',[0.3333 0.4196 0.1843]);
    set(AX2,'Tag','singleUnitPlot',...
            'Box','off',...
            'color',get(gcf,'Color'));
%
%%  CREATE VIDEO & PLOT FIRST FRAME OF VIDEO
    data.video      = McsHDF5.McsVideo(fig, data.STAData{UOI} / double(data.sweeps(UOI)), linehandle);
    AX3             = axes();
    set(AX3,'Parent',fig,'OuterPosition',posAX3);
    title('Video');
    [data.video,~]  = data.video.loadVideo(AX3);
    set(AX3,'Tag','video','Interruptible','on');
%
%%  STORE DATA WITH FIGURE
    guidata(fig, data);
%
end