function aesthetics() 
set(gca, 'box', 'off') % remove borders
set(gcf,'color','w'); % white background
set(gca, 'TickDir', 'out')
ax = gca;
try
    ax.Colorbar.TickDirection = 'out';
    ax.Colorbar.FontName = 'Arial';
    ax.Colorbar.FontSize = 12;
catch
end
% set(gca, 'Box', 'off', 'TickDir', 'out', 'TickLength', [.02 .02], ...
%     'XMinorTick', 'on', 'YMinorTick', 'on', 'YGrid', 'on', ...
%     'XColor', [.3 .3 .3], 'YColor', [.3 .3 .3], 'YTick', 0:500:2500, ...
%     'LineWidth', 1)

% set(gca, 'Box', 'off', 'TickDir', 'out',  ...
%     'XMinorTick', 'on', 'YMinorTick', 'on', 'YGrid', 'on')
set(gca, 'YGrid','off','XGrid','off')
end 