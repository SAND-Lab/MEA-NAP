function [y,t,optw,gs,C,confb95,yb] = ssvkernel(x,tin)
% [y,t,optw,gs,C,confb95,yb] = ssvkernel(x,t,W)
%
% Function `ssvkernel' returns an optimized kernel density estimate 
% using a Gauss kernel function with bandwidths locally adapted to data.
%
% Examples:
% >> x = 0.5-0.5*log(rand(1,1e3)); t = linspace(0,3,500);
% >> [y,t,optw] = ssvkernel(x,t);
% This example produces a vector of kernel density estimates, y, at points
% specified in a vector t, using locally adaptive bandwidths, optw 
% (a standard deviation of a normal density function).
% 
% >> ssvkernel(x);
% By calling the function without output arguments, the estimated density 
% is displayed.
%
% Input arguments:
% x:    Sample data vector. 
% tin (optinal):
%       Points at which estimation are computed. 
% W (optinal): 
%       A vector of kernel bandwidths. 
%       If W is provided, the optimal bandwidth is selected from the 
%       elements of W.
%       * Do not search bandwidths smaller than a sampling resolution of data.
%       If W is not provided, the program searches the optimal bandwidth
%       using a golden section search method. 
%
% Output arguments:
% y:    Estimated density
% t:    Points at which estimation was computed.
%       The same as tin if tin is provided. 
%       (If the sampling resolution of tin is smaller than the sampling 
%       resolution of the data, x, the estimation was done at smaller
%       number of points than t. The results, t and y, are obtained by 
%       interpolating the low resolution sampling points.)
% optw: Optimal kernel bandwidth.
% gs:   Stiffness constants of the variable bandwidth examined. 
%       The stifness constant is defined as a ratio of the optimal fixed
%       bandwidth to a length of a local interval in which a fixed-kernel
%       bandwidth optimization was performed. 
% C:    Cost functions of stiffness constants.
% conf95:
%       Bootstrap confidence intervals.
% yb:   Booststrap samples.
%
% 
% Usage:
% >> [y,t,optw] = ssvkernel(x);
% When t is not given in the input arguments, i.e., the output argument t 
% is generated automatically.
%
% >> W = linspace(0.01,1,20);
% >> [y,t,optw] = ssvkernel(x,t,W);
% The optimal bandwidth is selected from the elements of W.
%
% >> [y,t,optw,confb95,yb] = ssvkernel(x);
% This additionally computes 95% bootstrap confidence intervals, confb95.
% The bootstrap samples are provided as yb.
% 
%
% Optimization principle:
% The optimization is based on a principle of minimizing 
% expected L2 loss function between the kernel estimate and an unknown 
% underlying density function. An assumption is merely that samples 
% are drawn from the density independently each other. 
%
% The locally adaptive bandwidth is obtained by iteratively computing
% optimal fixed-size bandwidths wihtihn local intervals. The optimal 
% bandwidths are selected such that they are selected in the intervals 
% that are \gamma times larger than the optimal bandwidths themselves. 
% The paramter \gamma was optimized by minimizing the L2 risk estimate.
%
% The method is described in 
% Hideaki Shimazaki and Shigeru Shinomoto
% Kernel Bandwidth Optimization in Spike Rate Estimation 
% Journal of Computational Neuroscience 2010
% http://dx.doi.org/10.1007/s10827-009-0180-4
%
%
% For more information, please visit 
% http://2000.jukuin.keio.ac.jp/shimazaki/res/kernel.html
%
% See also SSKERNEL, SSHIST
%
% Bug fix
% 131004 fixed a problem for large values
% 170917 further fix for the large value issue
%
% Hideaki Shimazaki 
% http://2000.jukuin.keio.ac.jp/shimazaki


%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
% Parameters Settings
M = 80;            %Number of bandwidths examined for optimization.

WinFunc = 'Gauss'; %Window function ('Boxcar', 'Gauss','Laplace','Cauchy') 

nbs = 1*1e2;        %number of bootstrap samples

x = reshape(x,1,numel(x));

if nargin == 1
    T = max(x) - min(x);
    [mbuf,nbuf,dt_samp] = find( sort(diff(sort(x))),1,'first');
    tin = linspace(min(x),max(x), min(ceil(T/dt_samp),1e3));
    t = tin;
    x_ab = x( logical((x >= min(tin)) .*(x <= max(tin))) ) ;
else
    T = max(tin) - min(tin);
    x_ab = x( logical((x >= min(tin)) .*(x <= max(tin))) ) ;
    [mbuf,nbuf,dt_samp] = find( sort(diff(sort(x_ab))),1,'first');

    if dt_samp > min(diff(tin))
        t = linspace(min(tin),max(tin), min(ceil(T/dt_samp),1e3));
    else
        t = tin;
    end
end
clear mbuf nbuf;
dt = min(diff(t));

% Compute a globally optimal fixed bandwidth
%[yf,~,optWg] = sskernel(x,t);

% Create a finest histogram
y_hist = histc(x_ab,t-dt/2)/dt;
L = length(y_hist);
N = sum(y_hist*dt);

%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
% Computing local MISEs and optimal bandwidths
%disp('computing local bandwidths...');

%logexp = @(x) log(1+exp(x)); 
%ilogexp = @(x) log(exp(x)-1);

%Window sizes
WIN = logexp(linspace(ilogexp(max(5*dt)),ilogexp(1*T),M));

W = WIN;        %Bandwidths

c = zeros(M,L);
for j = 1:M
    w = W(j);
    yh = fftkernel(y_hist,w/dt);
    %computing local cost function
    c(j,:) = yh.^2 - 2*yh.*y_hist + 2/sqrt(2*pi)/w*y_hist;
end


optws = zeros(M,L);
for i = 1:M
    Win = WIN(i);
    
    C_local = zeros(M,L);
    for j = 1:M
        %computing local cost function
        %c = yh.^2 - 2*yh.*y_hist + 2/sqrt(2*pi)/w*y_hist;
        C_local(j,:) = fftkernelWin(c(j,:),Win/dt,WinFunc); %Eq.15 for t= 1...L   
    end
    
    [mbuf,n] = min(C_local,[],1); %find optw at t=1...L
    optws(i,:) = W(n);
end

%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
% Golden section search of the stiffness parameter of variable bandwidths.
% Selecting a bandwidth w/W = g. 

%disp('adapting local bandwidths...');

% Initialization
tol = 10^-5; 
a = 1e-12; b = 1;
%a = 1.1; b = 1.11;

phi = (sqrt(5) + 1)/2;  %golden ratio

c1 = (phi-1)*a + (2-phi)*b;
c2 = (2-phi)*a + (phi-1)*b;

f1 = CostFunction(y_hist,N,t,dt,optws,WIN,WinFunc,c1);
f2 = CostFunction(y_hist,N,t,dt,optws,WIN,WinFunc,c2);
    
k = 1;
while  ( abs(b-a) > tol*(abs(c1)+abs(c2)) ) && k < 30
    if f1 < f2
        b = c2;
        c2 = c1;
        c1 = (phi - 1)*a + (2 - phi)*b;
        
        f2 = f1;
        [f1 yv1 optwp1] = CostFunction(y_hist,N,t,dt,optws,WIN,WinFunc,c1);
        
        %optg = c1;
        yopt = yv1 / sum(yv1*dt);
        optw = optwp1;
    else
        a = c1;
        c1 = c2;
        c2 = (2 - phi)*a + (phi - 1)*b;
        
        f1 = f2;
        [f2 yv2 optwp2] = CostFunction(y_hist,N,t,dt,optws,WIN,WinFunc,c2);
        
        %optg = c2;
        yopt = yv2 / sum(yv2*dt);
        optw = optwp2;
    end
    
    gs(k) = (c1);
    C(k) = f1;
    k = k + 1;
end
%disp('optimization completed.');


%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
% Bootstrap Confidence Interval
if nargout == 0 || nargout >= 6 || nargin >= 3
    disp('computing bootstrap confidence intervals...');

    yb = zeros(nbs,length(tin));

    for i = 1: nbs, %disp([i nbs])
        Nb = poissrnd(N);
        %Nb = N;
        idx = ceil(rand(1,Nb)*N);
        xb = x_ab(idx);
        y_histb = histc(xb,t-dt/2);
        
        idx = find(y_histb ~= 0);
        y_histb_nz = y_histb(idx); 
        t_nz = t(idx);
        for k = 1: L
            yb_buf(k) = sum(y_histb_nz.*Gauss(t(k)-t_nz,optw(k)))/Nb;
        end
        yb_buf = yb_buf / sum(yb_buf*dt);
        
        yb(i,:) = interp1(t,yb_buf,tin);
        
    end

    ybsort = sort(yb);
    y95b = ybsort(floor(0.05*nbs),:);
    y95u = ybsort(floor(0.95*nbs),:); 
    
    confb95 = [y95b; y95u];
    
    disp('done');
end

%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
% Return results
y = interp1(t,yopt,tin);
optw = interp1(t,optw,tin);
t = tin;

%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
% Display results
if nargout == 0
	hold on;

	line([t; t],[y95b; y95u]...
        ,'Color',[7 7 7]/8,'LineWidth',1 );
	plot(t,y95b,'Color',[7 7 7]/9,'LineWidth',1);
	plot(t,y95u,'Color',[7 7 7]/9,'LineWidth',1);

	plot(t,y,'Color',[0.9 0.2 0.2],'LineWidth',2);

	grid on;
	ylabel('density');
	set(gca,'TickDir','out');    
end


function [Cg yv optwp] = CostFunction(y_hist,N,t,dt,optws,WIN,WinFunc,g)
%Selecting w/W = g bandwidth

L = length(y_hist);
optwv = zeros(1,L);
for k = 1: L
	gs = optws(:,k)'./WIN;
        
	if g > max(gs) 
        optwv(k) = min(WIN);
    else
        if g < min(gs)
            optwv(k) = max(WIN);
        else
            idx = find(gs >= g, 1, 'last');
            optwv(k) = g*WIN(idx); 
            %optwv(k) = optws(idx,k);%exp
        end
    end
end

%Nadaraya-Watson kernel regression
optwp = zeros(1,L);
for k = 1: L
    Z = feval(WinFunc,t(k)-t,optwv/g); 
    optwp(k) = sum(optwv.*Z)/sum(Z);
end
        
%optwp = optwv;
%Density estimation with the variable bandwidth

% Baloon estimator
%yv = zeros(1,L);
%for k = 1: L
%    yv(k) = sum( y_hist*dt.*Gauss(t(k)-t,optwp(k),PI) ) / N;    
%end
%yv = yv / sum(yv*dt);

% Baloon estimator (speed optimized)
idx = find(y_hist ~= 0);
y_hist_nz = y_hist(idx); 
t_nz = t(idx);

yv = zeros(1,L);
for k = 1: L
    yv(k) = sum( y_hist_nz*dt.*Gauss(t(k)-t_nz,optwp(k)));    
end
yv = yv *N/sum(yv*dt); %rate

% Sample points estimator
%yv = zeros(1,L);
%for k = 1: L
%    yv(k) = sum( y_hist_nz*dt.*Gauss(t(k)-t_nz,optwp(idx)) ) / N;    
%end

%yv = yv / sum(yv*dt);

% Kernel regression
%for k = 1: L
%	yv(k) = sum(y_hist.*Gauss(t(k)-t,optwp))...
%        /sum(Gauss(t(k)-t,optwp));
%end
%yv = yv *N/ sum(yv*dt);
%end

%yv = zeros(1,L);
%for k = 1: L
%    yv(k) = sum( y_hist.*Gauss(t(k),optwp).*Boxcar(t(k)-t,optwp/g) ) ...
%        / sum(Gauss(t(k),optwp).*Boxcar(t(k)-t,optwp/g));    
%end

%Cost function of the estimated density
cg = yv.^2 - 2*yv.*y_hist + 2/sqrt(2*pi)./optwp.*y_hist;
Cg = sum(cg*dt);


function [y] = fftkernel(x,w)
L = length(x);
Lmax = L+3*w; %take 3 sigma to avoid aliasing 

%n = 2^(nextpow2(Lmax)); 
n = 2^(ceil(log2(Lmax))); 

X = fft(x,n);

f = [-(0:n/2) (n/2-1:-1:1)]/n;

% Gauss
K = exp(-0.5*(w*2*pi*f).^2);

% Laplace
%K = 1 ./ ( 1+ (w*2*pi*f).^2/2 );

y = ifft(X.*K,n);
y = y(1:L);

function [y] = fftkernelWin(x,w,WinFunc)
L = length(x);
Lmax = L+3*w; %take 3 sigma to avoid aliasing 

%n = 2^(nextpow2(Lmax)); 
n = 2^(ceil(log2(Lmax)));

X = fft(x,n);

f = [-(0:n/2) (n/2-1:-1:1)]/n;
t = 2*pi*f;

if strcmp(WinFunc,'Boxcar')
    % Boxcar
    a = sqrt(12)*w;
    %K = (exp(1i*2*pi*f*a/2) - exp(-1i*2*pi*f*a/2)) ./(1i*2*pi*f*a);
    K = 2*sin(a*t/2)./(a*t);
    K(1) = 1;
elseif strcmp(WinFunc,'Laplace')
    % Laplace
    K = 1 ./ ( 1+ (w*2*pi.*f).^2/2 );
elseif strcmp(WinFunc,'Cauchy')
    % Cauchy
    K = exp(-w*abs(2*pi*f));
else
    % Gauss
    K = exp(-0.5*(w*2*pi*f).^2);
end

y = ifft(X.*K,n);
y = y(1:L);

function y = Gauss(x,w) 
y = 1/sqrt(2*pi)./w.*exp(-x.^2/2./w.^2);

function y = Laplace(x,w)
y = 1./sqrt(2)./w.*exp(-sqrt(2)./w.*abs(x));

function y = Cauchy(x,w) 
y = 1./(pi*w.*(1+ (x./w).^2));

function y = Boxcar(x,w)
a = sqrt(12)*w;
%y = 1./a .* ( x < a/2 ) .* ( x > -a/2 );
%y = 1./a .* ( abs(x) < a/2 );
y = 1./a; y(abs(x) > a/2) = 0; %speed optimization


function y = logexp(x)
idx = x<1e2;  
y(idx) = log(1+exp(x(idx)));

idx = x>=1e2; 
y(idx) = x(idx);

function y = ilogexp(x)
%ilogexp = @(x) log(exp(x)-1);
idx = x<1e2;  
y(idx) = log(exp(x(idx))-1);

idx = x>=1e2; 
y(idx) = x(idx);
