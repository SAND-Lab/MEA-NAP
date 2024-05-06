classdef McsCmosLinkedDataSource < handle
% Represents a data source that is an external link to another HDF5 file
%
% (c) 2017 by Multi Channel Systems MCS GmbH
    properties (SetAccess = protected)
        LinkFile      % (string) The file name of the external link
        LinkTarget      % (string) The name of the target in the file
    end
    
    methods
        function ds = McsCmosLinkedDataSource(linkFile, linkTarget)
        % Constructs a McsCmosLinkedDataSource object
        %
        % function ds = McsCmosLinkedDataSource(linkFile, linkTarget)
        %
        % Input:
        %   linkFile        -   (string) The file name of the link
        %   linkTarget      -   (string) The name of the target in the file
            ds.LinkFile = linkFile;
            ds.LinkTarget = linkTarget;
        end
        
        function linkAvailable = isLinkAvailable(ds)
        % Checks if the linked file exists.
        %
        % function linkAvailable = isLinkAvailable(ds)
        %
        % This checks only for the existance of the linked file, not if the
        % file contains the target group.
        %
        % Input:
        %   ds              -   A McsCmosLinkedDataSource object
        %
        % Output:
        %   linkAvailable   -   (bool) True, if the linked file exists
            linkAvailable = exist(ds.LinkFile, 'file') > 0;
        end
    end
end