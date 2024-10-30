function nodeSize = getNodeSize(z_i, nodeScaleF, Params)
%GETNODESIZE Summary of this function goes here
%   Detailed explanation goes here
if isfield(Params, 'nodeScalingMethod')
    if strcmp(Params.nodeScalingMethod, 'Linear')
        nodeSize = max(Params.minNodeSize, z_i/nodeScaleF);
    elseif strcmp(Params.nodeScalingMethod, 'Log2')
        nodeSize = max(Params.minNodeSize, log2(z_i+1)/log2(nodeScaleF +1));
    elseif strcmp(Params.nodeScalingMethod, 'Log10')
        nodeSize = max(Params.minNodeSize, log10(z_i+1)/log10(nodeScaleF +1));
    elseif strcmp(Params.nodeScalingMethod, 'Square')
        nodeSize = max(Params.minNodeSize, z_i^2/nodeScaleF^2);
    elseif strcmp(Params.nodeScalingMethod, 'Cube')
        nodeSize = max(Params.minNodeSize, z_i^3/nodeScaleF^3);
    elseif strcmp(Params.nodeScalingMethod, 'Power')
        nodeSize = max(Params.minNodeSize, z_i^Params.nodeScalingPower/nodeScaleF^Params.nodeScalingPower);
    end 
else 
    % This here means that the max node size is 1
    nodeSize = max(Params.minNodeSize,  z_i/nodeScaleF);
end 

if isfield(Params, 'maxNodeSize')
    nodeSize = max(Params.minNodeSize, nodeSize * Params.maxNodeSize);
end 

end

