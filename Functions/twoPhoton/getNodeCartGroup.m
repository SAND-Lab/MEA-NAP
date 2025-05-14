function NetMet = getNodeCartGroup(NetMet, Params)
%GETNODECARTGROUP Summary of this function goes here
%   Detailed explanation goes here



% Get lag name string (e.g., 'adjM1000mslag')
targetLagStr = sprintf('adjM%dmslag', Params.FuncConLagval);

% Check if it exists
if isfield(NetMet, targetLagStr)
    netMetGivenLag = NetMet.(targetLagStr);

    if ~isstruct(netMetGivenLag)
        warning('NetMet.%s is not a struct.', targetLagStr);
        return;
    end

    PC = netMetGivenLag.PC;
    Z = netMetGivenLag.Z;

    % Use correct boundaries
    if Params.autoSetCartographyBoudariesPerLag
        suffix = sprintf('_%dmsLag', Params.FuncConLagval);
        hubBoundaryWMdDeg = Params.(['hubBoundaryWMdDeg', suffix]);
        periPartCoef = Params.(['periPartCoef', suffix]);
        proHubpartCoef = Params.(['proHubpartCoef', suffix]);
        nonHubconnectorPartCoef = Params.(['nonHubconnectorPartCoef', suffix]);
        connectorHubPartCoef = Params.(['connectorHubPartCoef', suffix]);
    else
        hubBoundaryWMdDeg = Params.hubBoundaryWMdDeg;
        periPartCoef = Params.periPartCoef;
        proHubpartCoef = Params.proHubpartCoef;
        nonHubconnectorPartCoef = Params.nonHubconnectorPartCoef;
        connectorHubPartCoef = Params.connectorHubPartCoef;
    end

    % Assign nodeCartGrp
    numNodes = length(PC);
    nodeCartGrp = zeros(numNodes, 1);
    for nodeIndex = 1:numNodes
        if (Z(nodeIndex) <= hubBoundaryWMdDeg) && (PC(nodeIndex) <= periPartCoef)
            nodeCartGrp(nodeIndex) = 1;
        elseif (Z(nodeIndex) <= hubBoundaryWMdDeg) && (PC(nodeIndex) <= nonHubconnectorPartCoef)
            nodeCartGrp(nodeIndex) = 2;
        elseif (Z(nodeIndex) <= hubBoundaryWMdDeg)
            nodeCartGrp(nodeIndex) = 3;
        elseif (Z(nodeIndex) >= hubBoundaryWMdDeg) && (PC(nodeIndex) <= proHubpartCoef)
            nodeCartGrp(nodeIndex) = 4;
        elseif (PC(nodeIndex) <= connectorHubPartCoef)
            nodeCartGrp(nodeIndex) = 5;
        else
            nodeCartGrp(nodeIndex) = 6;
        end
    end

    % Store
    NetMet.(targetLagStr).nodeCartGrp = nodeCartGrp;
else
    warning('NetMet does not contain field: %s', targetLagStr);
end
