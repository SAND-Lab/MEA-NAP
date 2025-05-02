function NetMet = getNodeCartGroup(NetMet, Params)
%GETNODECARTGROUP Summary of this function goes here
%   Detailed explanation goes here



lagval = Params.FuncConLagval;     

lagFields = fieldnames(NetMet);

for lagFindex = 1:length(lagFields) 
    
    netMetGivenLag = NetMet.(lagFields{lagFindex});
    PC = netMetGivenLag.PC;
    Z = netMetGivenLag.Z;


    % Determine whether we need a specific boundary per lag 
    if Params.autoSetCartographyBoudariesPerLag
        hubBoundaryWMdDeg = Params.(strcat('hubBoundaryWMdDeg', sprintf('_%.fmsLag', lagval(lagFindex))));
        periPartCoef = Params.(strcat('periPartCoef', sprintf('_%.fmsLag', lagval(lagFindex))));
        proHubpartCoef = Params.(strcat('proHubpartCoef', sprintf('_%.fmsLag', lagval(lagFindex))));
        nonHubconnectorPartCoef = Params.(strcat('nonHubconnectorPartCoef', sprintf('_%.fmsLag', lagval(lagFindex))));
        connectorHubPartCoef = Params.(strcat('connectorHubPartCoef', sprintf('_%.fmsLag', lagval(lagFindex))));
    else
        hubBoundaryWMdDeg = Params.hubBoundaryWMdDeg;
        periPartCoef = Params.periPartCoef;
        proHubpartCoef = Params.proHubpartCoef;
        nonHubconnectorPartCoef = Params.nonHubconnectorPartCoef;
        connectorHubPartCoef = Params.connectorHubPartCoef;
    end 
    
    numNodes = length(PC);
    nodeCartGrp = zeros(numNodes, 1);  % equivalent to NdCartDiv
    

    for nodeIndex = 1:numNodes
        
        if (Z(nodeIndex) <= hubBoundaryWMdDeg) && (PC(nodeIndex) <= periPartCoef)
            nodeCartGrp(nodeIndex) = 1;
        elseif (Z(nodeIndex) <= hubBoundaryWMdDeg) && (PC(nodeIndex) >= periPartCoef) && (PC(nodeIndex) <= nonHubconnectorPartCoef)
            nodeCartGrp(nodeIndex) = 2;
        elseif (Z(nodeIndex) <= hubBoundaryWMdDeg) && (PC(nodeIndex) >= nonHubconnectorPartCoef)
            nodeCartGrp(nodeIndex) = 3;
        elseif (Z(nodeIndex) >= hubBoundaryWMdDeg) && (PC(nodeIndex) <= proHubpartCoef)
            nodeCartGrp(nodeIndex) = 4;
        elseif (Z(nodeIndex) >= hubBoundaryWMdDeg) && (PC(nodeIndex) >= proHubpartCoef) && (PC(nodeIndex) <= connectorHubPartCoef)
            nodeCartGrp(nodeIndex) = 5;
        elseif (Z(nodeIndex) >= hubBoundaryWMdDeg) && (PC(nodeIndex) >= connectorHubPartCoef)
            nodeCartGrp(nodeIndex) = 6;
        end

    end

    NetMet.(lagFields{lagFindex}).nodeCartGrp = nodeCartGrp;

end



end

