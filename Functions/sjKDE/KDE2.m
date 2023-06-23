function [fx,h,Xrange,Yrange]=KDE2(Xi,Yi,h,Xrange,Yrange)
%
% Kernel Density Estimate for 2 vairable
% for diagonal type h and multivariate normal kernel
% Each "Smoothing parameter" h is estimated from the SJ method 
% unless it is provided
% The X and Y range is devided 30 along the min and max 
% of historical data as a default
%
% Used subfunction : bandwidth_SJ.m
%
% Input
% Xi Yi : Historical Data (n*1) vector with the same data length
% h : bandwidth
% Xrange, Yrange : nr*1 vector with same length
%
% Output
% fx : Estiamted 2 variable density matrix (nr*nr) or 30*30(default)
% h  : Sheather and Jones 
% Xrange, Yrange - min~max with 30 (default)
%
% Programmed by Taesam Lee (04.29.2006)
% Reference : Simonoff JS(1996)-Smoothing methods in Statistics

nL=length(Xi);
if nargin<=2
[h(1)]=bandwidth_SJ(Xi,'norm');
[h(2)]=bandwidth_SJ(Yi,'norm');
end
if nargin<=3
    Xrange=min(Xi):(max(Xi)-min(Xi))/29:max(Xi);
    Yrange=min(Yi):(max(Yi)-min(Yi))/29:max(Yi);
end
nX=length(Xrange);
nY=length(Yrange);
for ix=1:nX
    for iy=1:nY
        u1=(Xrange(ix)-Xi)/h(1);
        u2=(Xrange(iy)-Yi)/h(2);
        u=[u1,u2]';
        for is=1:nL
            Kd_u(is)=1/(2*pi)^(2/2)*exp(-1/2*u(:,is)'*u(:,is));
        end
        fx(ix,iy)=mean(Kd_u)/prod(h);
    end
end

contour(Xrange,Yrange,fx,15);
hold on,scatter(Xi,Yi);
ylabel('YData'),xlabel('XData');
title('Biv. KDE (contour) with scatterplot of X&Y');

