function [cfg, isDefault] = checkParameter(cfg, fieldname, default)
% Helper function to set default parameters if necessary
%
% function [cfg, isDefault] = checkParameter(cfg, fieldname, default)
%
% Checks if a field with name fieldname exists in structure cfg. If not, or
% if it is empty, sets it to default, otherwise leaves it unchanged.
% isDefault is true if the default settings have been set in cfg, otherwise
% false if the field is unchanged.
%
% (c) 2016 by Multi Channel Systems MCS GmbH

    isDefault = false;

    if isempty(cfg)
        cfg.(fieldname) = [];
        isDefault = true;
    end
    
    if ~isfield(cfg, fieldname) || isempty(cfg.(fieldname))
        cfg.(fieldname) = default;
        isDefault = true;
    end