%{
    Copyright (c) 2024 Axion BioSystems, Inc.
    Contact: support@axion-biosystems.com
    All Rights Reserved
%}
classdef ChannelID < handle
    %ChannelID Representation of ChannelID class in AxIS
    %
    %   Artichoke: Numerical amplifier number (e.g., 0-11)
    %
    %   Channel: Numerical channel number (e.g., 0-63)
    %

    properties(GetAccess = public, SetAccess = private)
        Artichoke
        Channel
    end

    methods
        function this = ChannelID(aID)
            this.Artichoke = bitand(hex2dec('ff'), bitshift(aID, -8));
            this.Channel = bitand(hex2dec('ff'), bitshift(aID, 0));
        end
    end

end

