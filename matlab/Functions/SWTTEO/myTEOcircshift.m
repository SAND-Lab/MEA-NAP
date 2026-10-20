function X = myTEOcircshift(Y,k)
% circshift without the boundary behaviour
% Parameters 
% ----------
% Y : 
% k : 
%
% Output 
% ------
% X : 

colshift = k(1);
rowshift = k(2);

temp  = circshift(Y,k);

if colshift < 0
    temp(end+colshift+1:end,:) = flipud(Y(end+colshift+1:end,:));
elseif colshift > 0
    temp(1:1+colshift-1,:) = flipud(Y(1:1+colshift-1,:));
else

end

if rowshift<0
    temp(:,end+rowshift+1:end) = fliplr(Y(:,end+rowshift+1:end));
elseif rowshift>0
    temp(:,1:1+rowshift-1) = fliplr(Y(:,1:1+rowshift-1));
else
end

X = temp;

end
