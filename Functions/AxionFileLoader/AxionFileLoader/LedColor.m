%{
    Copyright (c) 2024 Axion BioSystems, Inc.
    Contact: support@axion-biosystems.com
    All Rights Reserved
%}
classdef LedColor < uint16
    %LEDCOLOR Color of a Stimulating LED
    enumeration
        % None: Indicates that a color hasn't been assigned yet.
        None(uint16(0)),

        % None: Indicates that this was a Blue Led
        Blue(uint16(1)),

        % None: Indicates that this was an Orange Led
        Orange(uint16(2)),

        % None: Indicates that this was a Green Led
        Green(uint16(3)),

        % None: Indicates that this was a Red Led
        Red(uint16(4))
    end
end

