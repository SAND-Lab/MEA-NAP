function pipelineSaveFig(figName, figExts, fullSVG, figHandle, renderer)
%
% Saves figure with the provided figure extensions 
%
% Parameters
% ----------
% figName : str 
%     figure name without extension, provide the full path if needed,
%     otherwise the figure will be saved to the current folder 
% figExts : cell array 
%     cell array containing string denoting the figure extensions to use, 
%     such as, '.pdf', '.svg'
% fullSVG : bool 
%     whether to always save SVG file even if the number of elements is high,
%     otherwise will let matlab decide whether to save as pure svg or save
%     the figure as an image within an svg file
% figHandle : fig handle 
%     optional figure handle, if none provided, then use gcf
% Returns 
% -------
% None

if ~exist('figHandle','var')
    fprintf('Figure handle does not exist'); 
    figHandle = [];
end 

if ~exist('renderer', 'var')
    renderer = 'default';
end 
    
for nFigExt = 1:length(figExts)
    figFileName = strcat([figName, figExts{nFigExt}]);
    if strcmp(figExts{nFigExt}, '.svg') && fullSVG
        if isempty(figHandle)
            if strcmp(renderer, 'opengl')
                fprintf('Using opengl renderer \n')
                print('-painters', '-dsvg', figFileName); % note this saves gcf by default
            else
                print('-painters', '-dsvg', '-opengl', figFileName); % note this saves gcf by default
            end
        else 
            if strcmp(renderer, 'opengl')
                fprintf('Using opengl renderer \n')
                print(figHandle, '-painters', '-dsvg',  '-opengl',  figFileName)
            else 
                print(figHandle, '-painters', '-dsvg',  figFileName)
            end 
        end 
    elseif strcmp(figExts{nFigExt}, '.fig')
        
        if isempty(figHandle)
            savefig(figFileName)
        else 
            matlabReleaseName = version('-release');
            versionYear = str2num(matlabReleaseName(1:end-1));
            
            if strcmp(matlabReleaseName, '2024b') || versionYear >= 2025
                savefig(figHandle, figFileName, '-v7.3')  % 
            else
                hgsave(figHandle, figFileName, '-v7.3')  
                % savefig() does not support version 7.3 option in releases
                % before 2024b
            end
        end
        
    else
        if isempty(figHandle)
            saveas(gcf, figFileName);
        else
            %saveas(figHandle, figFileName);
            if strcmp(renderer, 'opengl')
                fprintf('Using opengl renderer \n')
                print(figHandle, '-dpng', '-r300', '-opengl', figFileName);
            else 
                print(figHandle, '-dpng', '-r300', figFileName);
            end
        end 
    end 
end 

end 