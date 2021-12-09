function blockdiag = consensuscheck(D)
% H Smith, Cambridge, 2020
% Check if matrix is binary and block diagonal
%
% INPUTS:
%   D: adjacency matrix
%
% OUTPUTS:
%   blockdiag:
%       = 0: matrix is not block diagonal
%       = 1: matrix is block diagonal

v1 = sum(D,1);
v1 = v1';
v2 = sum(D,2);
check = sum(v1 - v2,'all');

if check == 0 && (numel(D(D == 0)) + numel(D(D == 1))) == numel(D)
    blockdiag = 1;
else
    blockdiag = 0;
end

end