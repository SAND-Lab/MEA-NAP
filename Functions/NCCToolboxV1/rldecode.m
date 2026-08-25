function x = rldecode(len, val)
%RLDECODE Run-length decoding of run-length encode data.
%
%   X = RLDECODE(LEN, VAL) returns a vector XLEN with the length of each run
%   and a vector VAL with the corresponding values.  LEN and VAL must have the
%   same lengths.
%
%   Example: rldecode([ 2 3 1 2 4 ], [ 6 4 5 8 7 ]) will return
%
%      x = [ 6 6 4 4 4 5 8 8 7 7 7 7 ];
%
%   See also RLENCODE.

%   Author:      Peter John Acklam
%   Time-stamp:  2002-03-03 13:50:38 +0100
%   E-mail:      pjacklam@online.no
%   URL:         http://home.online.no/~pjacklam

   % keep only runs whose length is positive
   k = len > 0;
   len = len(k);
   val = val(k);

   % now perform the actual run-length decoding
   i = cumsum(len);             % LENGTH(LEN) flops
   j = zeros(1, i(end));
   j(i(1:end-1)+1) = 1;         % LENGTH(LEN) flops
   j(1) = 1;
   x = val(cumsum(j));          % SUM(LEN) flops