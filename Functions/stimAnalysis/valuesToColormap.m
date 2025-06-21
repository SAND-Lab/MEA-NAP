function rgbColors = valuesToColormap(values, cmapName, vmin, vmax)
% valuesToColormap: Map numeric values to RGB colors using a colormap.
% Written by chatgpt with the following prompt:
% In matlab, can you write me code to convert a set of values to color
% values specified by a colormap, 
% I will provide the min and max of the set of values available
% Inputs:
%   - values: A vector or matrix of numeric values.
%   - cmapName: Name of a MATLAB colormap, e.g., 'parula', 'jet', 'hot'.
%   - vmin: Minimum value for scaling.
%   - vmax: Maximum value for scaling.
%
% Output:
%   - rgbColors: An Nx3 matrix of RGB color values if input is a vector,
%                or an MxNx3 matrix if input is a matrix.

    % Get the colormap
    cmap = colormap(cmapName);
    nColors = size(cmap, 1);
    
    % Normalize values to range [0, 1]
    normVals = (values - vmin) / (vmax - vmin);
    normVals = max(0, min(1, normVals));  % Clip to [0,1]
    
    % Scale to colormap indices
    idx = round(normVals * (nColors - 1)) + 1;

    % Apply colormap
    if isvector(values)
        rgbColors = cmap(idx, :);
    else
        rgbColors = zeros([size(values), 3]);
        for i = 1:3
            channel = cmap(:, i);
            rgbColors(:,:,i) = reshape(channel(idx), size(values));
        end
    end
end