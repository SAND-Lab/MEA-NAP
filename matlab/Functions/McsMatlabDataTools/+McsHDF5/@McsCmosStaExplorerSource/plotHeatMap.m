function plotHeatMap(fig, coordinates, heat, sensorDimension)
%plot all rectangles into fig onto all coordinates and sets face color to
%the value specified in heat
    fig;
    clf(fig);
    data = guidata(fig);
    %create custom grid
    g_y             = 0:1:sensorDimension(1)+1; % user defined grid Y [start:spaces:end]
    g_x             = 0:1:sensorDimension(1)+1; % user defined grid X [start:spaces:end]
    for i=1:length(g_x)
        plot([g_x(i) g_x(i)]-0.5,[g_y(1) g_y(end)]-0.5,'LineWidth',0.1,'Color',[ 0.8 0.8 0.8 ]) %y grid lines
        hold on
    end
    for i=1:length(g_y)
        plot([g_x(1) g_x(end)],[g_y(i) g_y(i)]-0.5,'LineWidth',0.1,'Color',[ 0.8 0.8 0.8 ]) %x grid lines
        hold on
    end
    axis(([1 (sensorDimension(2)+1) 1 (sensorDimension(1)+1)]-0.5));
    AX_OuterPosition    = [ 0.08 0 1 1 ];
    set(gca, 'xtick', 0:10:sensorDimension(2),...
                'ytick', 0:10:sensorDimension(1),...
                'YDir','reverse',...
                'Color',[ 1 1 1 ],...
                'PlotBoxAspectRatioMode','manual', ...
                'PlotBoxAspectRatio',[1 1 1],...
                'OuterPosition', AX_OuterPosition);
    xlabel('x')
    ylabel('y')
    
    %compute colors that signify number of sweeps that contributed to sta
    %data
    relativeSpikeCount  = heat/max(heat);
    redValue            = [ relativeSpikeCount ; zeros(size(relativeSpikeCount)) ; zeros(size(relativeSpikeCount)) ].';
	grayValue           = get(gca,'Color');
    scaledRedValue      = bsxfun(@times,grayValue./max(grayValue,1),redValue);
    shiftedGrayValue    = bsxfun(@minus,grayValue,repmat(scaledRedValue(:,1),1,3));
    colors              = bsxfun(@plus,shiftedGrayValue,scaledRedValue);
    
    %mark active sites
    txt = cell(1,length(data.sourceIDs));
    for i=1:length(data.sourceIDs)
        rectangle('Position',[coordinates(1,i)-0.5,coordinates(2,i)-0.5,1,1] ,...
                    'FaceColor', colors(i,:),...
                    'EdgeColor',[ 0.8 0.8 0.8 ]*0.68,...
                    'LineWidth',1);
        hold on
        switch data.labelType
            case 'sensorID'
                txt{i}  = num2str(data.IDs(i));
            case 'storageIdx'
                txt{i}  = i;
            otherwise %default use sourceID
                txt{i}  = num2str(data.sourceIDs(i));
        end
    end
    
    [A,I]   = sort(redValue(:,1));
    colors  = colors(I,:); 
    colormap(gca,colors);
    c                       = colorbar('Location','manual',...
                                'Position',[0.12 0.115 0.05 0.8],...
                                'Visible','on',...
                                'Tag','colbarSweeps',...
                                'ytickmode','manual',...
                                'yticklabelmode','manual');
                            
    lim                     = get(c,'YLim');
    offset                  = lim(1);
    ticks                   = [0:0.1:1]*(lim(2)-lim(1))+offset;
    ticklabels              = [0:0.1:1]*max(heat);
    n                       = floor(log10(max(heat)))-1;
    ticklabels           	= round(ticklabels*10^(-n))*10^n;
    ticklabels              = arrayfun(@num2str,ticklabels,'UniformOutput',false);
  	set(c,'YTick',ticks,'YTickLabel',ticklabels);
    ylabel(c,'Number of Sweeps');
    
    %mark labels
    position = get(gca,'OuterPosition');
    ax = axes('OuterPosition',position,...
                'Parent',fig,...
                'YDir','reverse',...
                'PlotBoxAspectRatioMode','manual', ...
                'PlotBoxAspectRatio',[1 1 1],...
                'OuterPosition', AX_OuterPosition);
    axis(([1 (sensorDimension(2)+1) 1 (sensorDimension(1)+1)]-0.5));
    text(coordinates(1,:), coordinates(2,:), txt, 'HorizontalAlignment', 'center',...
                                                        'VerticalAlignment', 'middle',...
                                                        'FontUnits', 'normalized',...
                                                        'FontSize', 2/sensorDimension(1),...
                                                        'Visible',data.labels,...
                                                        'Parent',ax);
    set(ax,'Visible','off','Tag','markers')
end