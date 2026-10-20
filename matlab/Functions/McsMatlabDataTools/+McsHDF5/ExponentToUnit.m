function [fact,unit_string] = ExponentToUnit(e,o)
% Utility function for some nice plotting of data.
%
% function [fact,unit_string] = ExponentToUnit(e,o)
%
% Receives the exponent of the largest absolute value of the data (i.e.
% log10(max(abs(data)))) and the exponent after the data is scaled by the
% exponent of the unit in which it is expressed. Example: Maximum
% amplitude: 200 mV = 2*10^-1 V. Data is given in units of 10^-9 V. Then e
% = -1, o = -1 - (-9) = 8. The function outputs a scaling factor for the
% data and a prefix string for the unit it is represented in after applying
% the scaling factor.
%
% Output: 
%   fact        -   scalar factor. data * fact transforms the data to nice
%                   units. In the 200 mV example with units of 10^-9 V,
%                   fact = 10^-6
%
%   unit_string -   depending on the output range, the unit prefix (n, µ,
%                   m, ...)
%
% (c) 2016 by Multi Channel Systems MCS GmbH

    poss_strings = {'p','n','\mu','m','','k','M','G'};
    poss_exp = [-12,-9,-6,-3,0,3,6,9];
    i = find(poss_exp <= e,1,'last');
    if isempty(i)
        i = 1;
    end
    fact = 10^(rem(o,3)-o);
    unit_string = poss_strings{i};
end