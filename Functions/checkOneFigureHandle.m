function Params = checkOneFigureHandle(Params)
    if Params.showOneFig
        if ~isfield(Params, 'oneFigure')
            Params.oneFigure = figure;
        end 
        if ~isgraphics(Params.oneFigure)
            Params.oneFigure = figure;
        end 
    end 
end 