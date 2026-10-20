function Qexp = getCommunicability(W,g,nQexp)
% 
% call:
% 
%      Qexp = getCommunicability(W,g,nQexp)
%      
% Compute the communicability matrix Qexp from
% the structural network defined by matrix W. 
% 
% INPUT
% 
%        W       :  n-by-n matrix (cab be weighted, unweighted, directed or undirected)
%        g       :  global coupling factor (default is 1)
%        nQexp   :  set to 1 if want to normalize the communicability matrix Qexp between
%                   0 and 1, 0 otherwise (default is 0).[*]
%        
% OUTPUT
% 
%        Qexp    : Communicability matrix (n-by-n)
%        
%
% 
% [*] If I want to compare the communicability between network of same size, 
%     perhaps I would want o normalize the communicability (nQexp=1). Otherwise,
%     if networks have different size, I do not want to normalize the communicability (nQexp=0).
%     
%
% BIBLIOGRAPHY:
% -------------
%
% - E Estrada, N Hatano, Communicability in complex networks
%   Physical Review E, 2008 - APS
%
% - E Estrada, N Hatano, M Benzi, The physics of communicability in complex networks
%   Physics reports, 2012 - Elsevier
%
% ----------------------------------------------------------
% R.G. Bettinardi
%
% Computational Neuroscience Group, Pompeu Fabra University
% mail: rug.bettinardi@gmail.com
% ---------------------------------------------------------

if ismatrix(W)==0
    error('Input W must have maximum 2 dimensions!')
end

if size(W,1)~=size(W,2)
    error('Input W must be a SQUARE matrix!')
end     

if nargin < 3
    nQexp = 0;
end
    
if nargin < 2
    nQexp = 0;
    g     = 1;
end

n    = size(W,1);
T    = zeros(n);

% exponential mapping ("influence" matrix)
Qexp = expm(g.*W);   

% normalize Qexp if required:
if nQexp == 1
    Qexp = ( Qexp - min(Qexp(:)) )./( max(Qexp(:)) - min(Qexp(:)) );
end
