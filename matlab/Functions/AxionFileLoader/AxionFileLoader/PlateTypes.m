%{
    Copyright (c) 2024 Axion BioSystems, Inc.
    Contact: support@axion-biosystems.com
    All Rights Reserved
%}
classdef PlateTypes
    %PlateTypes finds dimentions for known plate types
    %   This class has to be modified every time a new plate type is added
    %   to AxIS

    properties(Constant, Access=public)
        % Represents a null set of channels
        Empty = uint32(hex2dec('0000000'));

        % Debug Channel Mapping set for Muse systems
        LinearSingleWell64 = uint32(hex2dec('0400000'));

        % Standard Muse single well
        P200D30S = uint32(hex2dec('0400001'));
        
        %Standard Creator Kit 2 "well"
        MEACreatorKit = uint32(hex2dec('0800000'));

        % Debug Channel Mapping set for Maestro Edge systems
        LinearSixWell = uint32(hex2dec('1800000'));

        % CytoView MEA 24 well plate
        TwentyFourWell = uint32(hex2dec('1800001'));

        % BioCircuit MEA 24 well plate
        TwentyFourWellCircuit = uint32(hex2dec('1800002'));

        % CytoView MEA 6 well plate
        SixWell = uint32(hex2dec('1800003'));

        % Lumos MEA 24 well plate
        TwentyFourWellLumos = uint32(hex2dec('1800004'));

        % Lumos OptiClear 24 (No Electrodes, Never Recorded)
        TwentyFourWellOptiClear =  uint32(hex2dec('1800005'));

        % CytoView-Z 96 (Impedance Product, Never Recorded)
        NinetySixWellImpedance =  uint32(hex2dec('1800006'));
        
        % CytoView-Z 96 well conductive tech (Impedance Product, Never Recorded)
        NinetySixWellImpedanceConductiveTech =  uint32(hex2dec('1800007'));
        
        % Netri DualLink Edge
        NetriDuaLinkEdge =  uint32(hex2dec('1800008'));
        
        % Netri DualLinkShift Edge
        NetriDuaLinkShiftEdge =  uint32(hex2dec('1800009'));
        
        % Netri TrialLink Edge
        NetriTrialLinkEdge =  uint32(hex2dec('180000A'));
        
        % Reserved
        Reserved03 =  uint32(hex2dec('180000B'));

        % Debug Channel Mapping set for Maestro Pro systems
        LinearTwelveWell = uint32(hex2dec('3000000'));

        % CytoView MEA 12 well plate
        TwelveWell = uint32(hex2dec('3000001'));

        % Classic MEA 48 well plate
        FortyEightWell = uint32(hex2dec('3000002'));

        % Classic MEA 96 well plate
        NinetySixWell =    uint32(hex2dec('3000003'));

        % CytoView MEA 48 well plate
        FortyEightWellTransparent =    uint32(hex2dec('3000004'));

        % (Reserved ID, Never Recorded) 
        Reserved01 = uint32(hex2dec('3000005'));

        % Lumos MEA 48 well plate
        FortyEightWellLumos = uint32(hex2dec('3000006'));

        % Classic MEA 48 well plate with E-Stim+
        FortyEightWellEStimPlus =    uint32(hex2dec('3000007'));

        % BioCircuit MEA 96 well plate
        NinetySixWellCircuit = uint32(hex2dec('3000008'));

        % CytoView MEA 96 well plate
        NinetySixWellTransparent = uint32(hex2dec('3000009'));

        % Lumos MEA 96 well plate
        NinetySixWellLumos = uint32(hex2dec('300000A'));

        % BioCircuit MEA 48 well plate
        FortyEightWellCircuit = uint32(hex2dec('300000B'));

        % Classic MEA 48 well plate with AccuSpot
        FortyEightWellAccuSpot = uint32(hex2dec('300000C'));

        % Lumos OptiClear 48 well plate (No Electrodes, Never Recorded)
        FortyEightWellOptiClear = uint32(hex2dec('300000D'));

        % Lumos OptiClear 96 well plate (No Electrodes, Never Recorded)
        NinetySixWellOptiClear = uint32(hex2dec('300000E'));

        % (Reserved ID, Never Recorded)
        Reserved02 = uint32(hex2dec('300000F'));

        % CytoView-Z 384 well plate (Impedance Product, Never Recorded)
        ThreeEightyFourWellImpedance = uint32(hex2dec('3000010'));
        
        % Netri DualLink Pro
        NetriDuaLinkPro = uint32(hex2dec('3000011'));
        
        % Netri DualLinkShift Pro
        NetriDuaLinkShiftPro = uint32(hex2dec('3000012'));
        
        % Netri TialLink Pro
        NetriTrialLinkPro = uint32(hex2dec('3000013'));
        
        % Reserved ID
        Reserved04 = uint32(hex2dec('3000014'));
        
        % CytoView MEA 48 well Organoid Plate
        FortyEightWellOrganoid = uint32(hex2dec('3000015'));
        
        % CytoView MEA 12-well Transparent
        TwelveWellTransparent = uint32(hex2dec('3000016'));
    end

    properties (Constant, Access=private)

        MUSE_MASK    = uint32(hex2dec('0400000'));
        MAESTRO_MASK = uint32(hex2dec('3000000'));
        EDGE_MASK    = uint32(hex2dec('1800000'));
        CREATOR_MASK    = uint32(hex2dec('0800000'));

        MuseElectrodeMap = [ 1, 1, 8, 8;       ... % LinearSingleWell64
                             1, 1, 8, 8];          % P200D30S
                         
        CreatorElectrodeMap = [ 1, 2, 8, 8];    ... % MEA Creator Kit "2-well"

        EdgeElectrodeMap = [ 2, 3, 8, 8;       ... %LinearSixWell
                             4, 6, 4, 4;       ... %TwentyFourWell
                             4, 6, 4, 4;       ... %TwentyFourWellCircuit
                             2, 3, 8, 8;       ... %SixWell
                             4, 6, 4, 4;       ... %TwentyFourWellLumos
                             4, 6, 0, 0;       ... %TwentyFourWellOptiClear
                             8, 12, 0, 0;      ... %NinetySixWellImpedance
                             8, 12, 0, 0;       ...NinetySixWellImpedanceConductiveTech
                             2, 4, 11, 5;      ... %NetriDuaLinkEdge
                             2, 4, 11, 5;      ... %NetriDuaLinkShiftEdge
                             2, 4, 11, 5;      ... %NetriTrialLinkEdge
                             2, 4, 11, 5;]     ... %Reserved03

        MaestroElectrodeMap = [ 3, 4, 8, 8;    ... %LinearTwelveWell
                                3, 4, 8, 8;    ... %TwelveWell
                                6, 8, 4, 4;    ... %FortyEightWell
                                8, 12, 3, 3;   ... %NinetySixWell
                                6, 8, 4, 4;    ... %FortyEightWellTransparent
                                16, 24, 2, 1;  ... %Reserved01
                                6, 8, 4, 4;    ... %FortyEightWellLumos
                                6, 8, 4, 4;    ... %FortyEightWellEStimPlus
                                8, 12, 3, 3;   ... %NinetySixWellCircuit
                                8, 12, 3, 3;   ... %NinetySixWellTransparent
                                8, 12, 3, 3;   ... %NinetySixWellLumos
                                6, 8, 4, 4;    ... %FortyEightWellCircuit
                                6, 8, 4, 4;    ... %FortyEightWellAccuSpot
                                6, 8, 0, 0;    ... %FortyEightWellOptiClear
                                8, 12, 0, 0;   ... %NinetySixWellOptiClear
                                8, 12, 3, 3;   ... %Reserved02
                                16, 24, 0, 0;  ... %ThreeEightyFourWellImpedance
                                4, 4, 11, 5;   ... %NetriDuaLinkPro
                                4, 4, 11, 5;   ... %NetriDuaLinkShiftPro
                                4, 4, 11, 5;   ... %NetriTrialLinkPro
                                4, 4, 11, 5;  ... %Reserved04
                                6, 8, 4, 4;  ... %FortyEightWellOrganoid
                                3, 4, 8, 8;]  ... %TwelveWellTransparent
                                
    end

    methods(Static)
        function fPlateDimentions = GetWellDimensions(aPlateType)
            % GetWellDimensions returns a 2-element array of plate
            % dimensions.
            %
            % First element is the number of well rows, second element
            % is the number of well columns.
            %
            PlateIDMask = 65535;
            offset = bitand(aPlateType, PlateIDMask);
            if(aPlateType == PlateTypes.Empty)
                fPlateDimentions = [];
            elseif (bitand(aPlateType, PlateTypes.MUSE_MASK) == PlateTypes.MUSE_MASK)
               fPlateDimentions = PlateTypes.MuseElectrodeMap(offset + 1, (1:2));
            elseif (bitand(aPlateType, PlateTypes.MAESTRO_MASK) == PlateTypes.MAESTRO_MASK)
               fPlateDimentions = PlateTypes.MaestroElectrodeMap(offset + 1, (1:2));
            elseif (bitand(aPlateType, PlateTypes.EDGE_MASK) == PlateTypes.EDGE_MASK)
               fPlateDimentions = PlateTypes.EdgeElectrodeMap(offset + 1, (1:2));
            elseif (bitand(aPlateType, PlateTypes.CREATOR_MASK) == PlateTypes.CREATOR_MASK)
               fPlateDimentions = PlateTypes.CreatorElectrodeMap(offset + 1, (1:2));
            else
                warning('File has an unknown plate type. These Matlab Scripts may be out of date.');
                fPlateDimentions = [];
            end
        end

        function fElectrodeDimentions = GetElectrodeDimensions(aPlateType)
            % GetElectrodeDimensions returns a 4-element array of plate
            % dimensions (wells and electrodes within wells).
            %
            % Format is [well rows, well columns, electrode columns, electrode rows].
            %
            % NOTE:  wells of a 96-well plates have 3 electrode rows an 3
            % electrode columns.  However, the second row contains only 2
            % valid electrodes.
            %
            % Second note: Netri plates have 48 electrodes per well, there
            % are many locations in the mapping with no electodes:
            % 11, 15, 61, 63, 65, b1, b5
            %
            PlateIDMask = 65535;
            offset = bitand(aPlateType, PlateIDMask);
            if(aPlateType == PlateTypes.Empty)
                fElectrodeDimentions = [];
            elseif (bitand(aPlateType, PlateTypes.MUSE_MASK) == PlateTypes.MUSE_MASK)
               fElectrodeDimentions = PlateTypes.MuseElectrodeMap(offset + 1, :);
            elseif (bitand(aPlateType, PlateTypes.MAESTRO_MASK) == PlateTypes.MAESTRO_MASK)
               fElectrodeDimentions = PlateTypes.MaestroElectrodeMap(offset + 1, :);
            elseif (bitand(aPlateType, PlateTypes.EDGE_MASK) == PlateTypes.EDGE_MASK)
               fElectrodeDimentions = PlateTypes.EdgeElectrodeMap(offset + 1, :);
            elseif (bitand(aPlateType, PlateTypes.CREATOR_MASK) == PlateTypes.CREATOR_MASK)
               fElectrodeDimentions = PlateTypes.CreatorElectrodeMap(offset + 1, :);
            else
                warning('File has an unknown plate type. These Matlab Scripts may be out of date.');
                fElectrodeDimentions = [];
            end
        end
    end
end
