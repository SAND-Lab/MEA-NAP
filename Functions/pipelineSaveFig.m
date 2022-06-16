function pipelineSaveFig(figName, figExts, fullSVG, figHandle)
%{
Saves figure with the provided figure extensions 

Parameters
----------
figName : str 
    figure name without extension, provide the full path if needed,
    otherwise the figure will be saved to the current folder 
figExts : cell array 
    cell array containing string denoting the figure extensions to use, 
    such as, '.pdf', '.svg'
fullSVG : bool 
    whether to always save SVG file even if the number of elements is high,
    otherwise will let matlab decide whether to save as pure svg or save
    the figure as an image within an svg file
figHandle : fig handle 
    optional figure handle, if none provided, then use gcf
Returns 
-------
None
%}
if ~exist('figHandle','var')
    figHandle = [];
end 
    
for nFigExt = 1:length(figExts)
    figFileName = strcat([figName, figExts{nFigExt}]);
    if strcmp(figExts{nFigExt}, '.svg') && fullSVG
        if ispc
            if isempty(figHandle)
                fig2svg(figFileName)
            else
                fig2svg(figFileName, figHandle)
            end 
        else
            if isempty(figHandle)
                print('-painters', '-dsvg', figFileName); % note this saves gcf by default
            else 
                print(figHandle, '-painters', '-dsvg', figFileName)
            end 
        end 
    else
        if isempty(figHandle)
            saveas(gcf, figFileName);
        else
            saveas(figHandle, figFileName);
        end 
    end 
end 

end 