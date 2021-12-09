function [smoothed] = fLOESS(noisy,span) 
%
% Author; Gabriel Marsh
% Latest revision; 
% 22/02/2016    Included non-uniformly spaced x-data capability
%
%% DESCRIPTION
% Function fLOESS performs LOESS (locally weighted regression fitting using 
% a 2nd order polynomial) to one dimensional data. This might be considered 
% a better approach to LOWESS, which produces a locally weighted regression 
% using a linear fit.
% 
%% INPUTS
% noisy     =   An (nx1) vector containing the noisy data to be smoothed,
%               or, and(nx2) array containing x-data in the first column
%               (increasing values) and noisy y-data in the second column.
% span      =   A value specifying the fraction of data to use with the 
%               fitting procedure. Minimum value is span = 4/n
%
%% OUTPUTS
% smoothed  =   An (nx1) vector of smoothed data points
%
%% EXAMPLE
% generate some random data
% x = 10*sort(rand(100,1));
% clean = cos(1.0*x + 1) + 1.0;
% noisy =  [x,clean + 1.5*(rand(length(x),1)-0.5)];
% 
% % define the span length (randomised between 10 and length of data)
% span = 0.1 + 0.9*rand(1,1);
% 
% % fit the data
% smoothed = fLOESS(noisy,span); 
% 
% % Plot the data
% hold off
% plot(x,clean,'k')
% hold all
% plot(x,noisy(:,2),'.')
% plot(x,smoothed,'LineWidth',2)
% legend({'clean','noisy',['smoothed (span = ',sprintf('%1.2f',span),')']})

%% Error checking

% Check suffient number of data points will be included in the fitting
if length(noisy)*span<4 
    error('myApp:argChk','input arg "span" is too low')    
end

% Default x-data
if size(noisy,2)<2
    noisy = [(1:1:length(noisy))',noisy];
end

%% Smooth the data points

% define variables
x = noisy(:,1);
y = noisy(:,2);
n = length(noisy);
r = x(end) - x(1);
hlims = [span,x(1);...
    (span)/2,x(1)+r*span/2;...
    (span)/2,x(1)+r*(1-span/2);...
    span,x(end)];  

% Find the LOESS fit to the data
smoothed = zeros(n,1); % pre-allocate space
for i = 1:n
    
    % define the tricube weight function
    h = interp1(hlims(:,2),hlims(:,1),x(i));
    w = (1-abs((x./max(x)-x(i)./max(x))/h).^3).^3;
    
    % data points outwith the defined span can be ignored (for speed)
    w_idx = w>0;
    w_ = w(w_idx);
    x_ = x(w_idx);
    y_ = y(w_idx);
    
    % Calculate the weighted coefficients
    XX =   [nansum(w_.*x_.^0), nansum(w_.*x_.^1), nansum(w_.*x_.^2);...
            nansum(w_.*x_.^1), nansum(w_.*x_.^2), nansum(w_.*x_.^3);...
            nansum(w_.*x_.^2), nansum(w_.*x_.^3), nansum(w_.*x_.^4)];
    
    YY =   [nansum(w_.*y_.*(x_.^0));...
            nansum(w_.*y_.*(x_.^1));...
            nansum(w_.*y_.*(x_.^2))];
    
    CC = XX\YY;
    
    % calculate the fitted data point
    smoothed(i) = CC(1) + CC(2)*x(i) + CC(3)*x(i).^2;
    
end

end

