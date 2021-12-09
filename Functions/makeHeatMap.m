function makeHeatMap(spikeMatrix,option,channels) 

    % outputs a heatmap figure handle for your spikes 
    % Assume numSamp x 60 matrix 
    
    % INTPUT
        % spikeMatrix 
            % number of samples x numChannels binary spike matrix 
            % where 0 means no spike and 1 means spike 
            % current implementation is based on 8 x 8 grid with 60
            % electrodes, and with each corner removed 
        % option 
            % default option is 'count', which shows the spike count 
            % if option is 'rate', then this outputs the firing rate
            % instead 
            % note the current implementation assumes a sampling rate of
            % 25kHz
    
    % Author: Tim Sit 
    % Last Update: 20180607
    
    if ~exist('option')
        option = 'count'; 
    end  
    
    
    spikeCount = sum(spikeMatrix); 
    
        pltOrder=[find(channels==21),find(channels==31),find(channels==41),... %count across columns (subplot index plots across columns, e.g. sublot (4,4,2) the plots in column 2 not row 2
        find(channels==51),find(channels==61),find(channels==71),find(channels==12),...
        find(channels==22),find(channels==32),find(channels==42),find(channels==52),...
        find(channels==62),find(channels==72),find(channels==82),find(channels==13),...
        find(channels==23),find(channels==33),find(channels==43),find(channels==53),...
        find(channels==63),find(channels==73),find(channels==83),find(channels==14),...
        find(channels==24),find(channels==34),find(channels==44),find(channels==54),...
        find(channels==64),find(channels==74),find(channels==84),find(channels==15),...
        find(channels==25),find(channels==35),find(channels==45),find(channels==55),...
        find(channels==65),find(channels==75),find(channels==85),find(channels==16),...
        find(channels==26),find(channels==36),find(channels==46),find(channels==56),...
        find(channels==66),find(channels==76),find(channels==86),find(channels==17),...
        find(channels==27),find(channels==37),find(channels==47),find(channels==57),...
        find(channels==67),find(channels==77),find(channels==87),find(channels==28),...
        find(channels==38),find(channels==48),find(channels==58),find(channels==68),...
        find(channels==78)];
    
    spikeCount = spikeCount(pltOrder);

    
    if strcmp(option,'rate')
        spikeCount = spikeCount / (size(spikeMatrix, 1) / 25000);
    end 

    if strcmp(option,'logc')
        spikeCount = log10(spikeCount);
    end 
    
    if strcmp(option,'logr')
        spikeCount = log10( spikeCount / (size(spikeMatrix,1) / 25000) );
        spikeCount(find(spikeCount == log10(0))) = NaN; % log10(0) = -Inf so set to NaN if fire rate is 0
    end 
    
    % log(spikeCount) % log scale 
    
    % reshape it to display properly 
    % note that this part is quite hard-coded, don't use for general
    % heatmap, only use the imagesc part for non-MEA data
    
    heatMatrix = zeros(8, 8); 
    heatMatrix(1, 1) = NaN; 
    heatMatrix(1, 8) = NaN; 
    heatMatrix(8, 1) = NaN;
    heatMatrix(8, 8) = NaN; 
    
    % this assumes all electrode present
    if length(spikeCount) == 60
        heatMatrix(2:7) = spikeCount(1:6);
        heatMatrix(9:56) = spikeCount(7:54); 
        heatMatrix(58:63) = spikeCount(55:60);
    elseif length(spikeCount) == 59
        % basically, grounded electrode 5
        heatMatrix(5) = NaN; 
        heatMatrix(2:4) = spikeCount(1:3); 
        heatMatrix(6:7) = spikeCount(4:5); 
        heatMatrix(9:56) = spikeCount(6:53);
        heatMatrix(58:63) = spikeCount(54:59);
    elseif length(spikeCount) == 58
        % basically, grounded electrode 5 and 16
        heatMatrix(5) = NaN;
        heatMatrix(16) = NaN;
        heatMatrix(2:4) = spikeCount(1:3); 
        heatMatrix(6:7) = spikeCount(4:5);
        heatMatrix(9:15) = spikeCount(6:12); 
        heatMatrix(17:56) = spikeCount(13:52); 
        heatMatrix(58:63) = spikeCount(53:58);
    end 
    
    % flip things (organoid project)
    heatMatrix = heatMatrix'; 
    
    % make heatmap, whilst setting NA values to white
    h = imagesc(heatMatrix); 
    set(h, 'AlphaData', ~isnan(heatMatrix))
    text(0.9,5,'R','FontName','Arial','FontSize',18)
    
    % colormap(viridis)
    
    % attempt to make electrode with 0 spike (excluded) 
    % (not the same as NA, which are not recorded)
    % myColorMap = viridis(256); 
    % myColorMap(1, :) = 0; % 0 is black, 1 is white
    % colormap(myColorMap); 
   
    
    cb = colorbar;
    if strcmp(option, 'count') 
        ylabel(cb, 'Spike count')
        %for Andras organoids:
        %caxis([5000 10000])
    elseif strcmp(option, 'rate') 
        ylabel(cb, 'Spike rate (Hz)')
    elseif strcmp(option, 'logc')
        %ylabel(cb, 'Log10 spike count')   
        ylabel(cb, 'Spike count')
        ylimit_cbar = 5;
        caxis([0,ylimit_cbar]) %set colorbar axis limits; also adjusts colour
        cb.Ticks = linspace(0,ylimit_cbar,ylimit_cbar+1);%(start,end,number of numbers)
        cb.TickLabels = 10.^(linspace(0,ylimit_cbar,ylimit_cbar+1));
    elseif strcmp(option, 'logr')
        %ylabel(cb, 'Log10 spike count')   
        ylabel(cb, 'Spike rate (Hz)')
        ylimit_cbar = log10(50); % 20 Hz limit
        ymin_cbar   = log10(0.01);
        caxis([ymin_cbar,ylimit_cbar]) %set colorbar axis limits; also adjusts colour
        cb.Ticks = [log10(0.01) log10(0.1) log10(0.5) log10(1) log10(2) log10(5) log10(10) log10(20) log10(50)];%(start,end,number of numbers)
        cb.TickLabels = 10.^(cb.Ticks);   
    end 
    cb.TickDirection = 'out';
    cb.Location = 'Southoutside';
    cb.Box = 'off';
    
    aesthetics
    removeAxis
    % add outline of MEA 
    hold on
    plot([1.5 7.5] , [0.5 0.5],'LineStyle','-','LineWidth',1,'Color','k')
    plot([1.5 7.5] , [8.5 8.5],'LineStyle','-','LineWidth',1,'Color','k')
    plot([0.5 0.5] , [1.5 7.5] ,'LineStyle','-','LineWidth',1,'Color','k')
    plot([8.5 8.5] , [1.5 7.5] ,'LineStyle','-','LineWidth',1,'Color','k')
    for ycoord = [1.5 2.5 3.5 4.5 5.5 6.5 7.5]
        plot([0.5 8.5] , [ycoord ycoord],'LineStyle','-','LineWidth',1,'Color','k')
    end
    for ycoord = [1.5 2.5 3.5 4.5 5.5 6.5 7.5]
        plot([ycoord ycoord] , [0.5 8.5],'LineStyle','-','LineWidth',1,'Color','k')
    end
    hold off
    
    
    % make it square-ish
    set(gcf, 'Position', [100, 100, 800, 700])
    
    % set font size 
    set(gca, 'FontSize', 16)
    set(gca, 'FontName', 'Arial')

end 