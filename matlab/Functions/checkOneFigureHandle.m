function oneFigureHandle = checkOneFigureHandle(Params, oneFigureHandle)
    if Params.showOneFig
        if ~isgraphics(oneFigureHandle)
            oneFigureHandle = figure;
        end 
    else
        oneFigureHandle = 0;
    end 
end 