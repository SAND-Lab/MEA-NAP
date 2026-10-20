function sec = TickToSec(tick)
% Converts tick in microseconds to seconds
%
% function sec = TickToSec(tick)
%
% Input:
%   tick     -   Time in microseconds
%
% Output:
%   sec    -   microseconds converted to seconds.
%
% (c) 2016 by Multi Channel Systems MCS GmbH

    sec = double(tick) * 1e-6;
end