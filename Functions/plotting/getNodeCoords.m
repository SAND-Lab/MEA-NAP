function coords = getNodeCoords(adjM, Params)
%GETNODECOORDS Summary of this function goes here
%   Detailed explanation goes here
    if strcmp(Params.nodeLayout, 'force')
        % Create a graph object from the adjacency matrix
        G = graph(adjM, 'lower');
        % Use layout to get coordinates without plotting
        % coords = layout(G, 'force');
        tempPlot = plot(G, 'Layout', 'force');

        % Extract the coordinates
        x = tempPlot.XData;
        y = tempPlot.YData;
        coords(:, 1) = x;
        coords(:, 2) = y;

        % Delete the temporary plot
        delete(tempPlot);
    elseif strcmp(Params.nodeLayout, 'layered')
        % Create a graph object from the adjacency matrix
        G = graph(adjM, 'lower');
        % Use layout to get coordinates without plotting
        % coords = layout(G, 'force');
        tempPlot = plot(G, 'Layout', 'layered');

        % Extract the coordinates
        x = tempPlot.XData;
        y = tempPlot.YData;
        coords(:, 1) = x;
        coords(:, 2) = y;

        % Delete the temporary plot
        delete(tempPlot);
    elseif strcmp(Params.nodeLayout, 'subspace')
        % Create a graph object from the adjacency matrix
        G = graph(adjM, 'lower');
        % Use layout to get coordinates without plotting
        % coords = layout(G, 'force');
        tempPlot = plot(G, 'Layout', 'subspace');

        % Extract the coordinates
        x = tempPlot.XData;
        y = tempPlot.YData;
        coords(:, 1) = x;
        coords(:, 2) = y;

        % Delete the temporary plot
        delete(tempPlot);
    elseif strcmp(Params.nodeLayout, 'auto')
        % Create a graph object from the adjacency matrix
        G = graph(adjM, 'lower');
        % Use layout to get coordinates without plotting
        % coords = layout(G, 'force');
        tempPlot = plot(G, 'Layout', 'auto');

        % Extract the coordinates
        x = tempPlot.XData;
        y = tempPlot.YData;
        coords(:, 1) = x;
        coords(:, 2) = y;

        % Delete the temporary plot
        delete(tempPlot);
    end 
    
end

