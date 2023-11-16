function y = extendswt(x, lf)
%EXTENDSWT extends the signal periodically at the boundaries
% Parameters 
% -----------
% x : 
% lf :
% 
% Output 
% ------
% y : 
[r,c] = size(x);
y = zeros(r+lf,c);
y(1:lf/2,:) = x(end-lf/2+1:end,:);
y(lf/2+1:lf/2+r,:) = x;
y(end-lf/2+1:end,:) = x(1:lf/2,:);

end