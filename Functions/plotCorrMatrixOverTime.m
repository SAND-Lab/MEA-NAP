%% Make animated gif of correlation matrix over time

time_window = 60;
step_size = 10;
fs = 25000;
corrMatrixOverT = calCorrMatrixOverTime(full(spikeMatrix), time_window, step_size, fs);

%% Loop through each matrix and make the network plot 
plotType = 'MEA';
edge_thresh = 0.0001;
FN = 'nan';
pNum = 1;
lagval = [10, 20, 30];
e = 1;
Params.oneFigure = figure();
corrMatrixOverT(isnan(corrMatrixOverT)) = 0.0001;

filename = '/Users/timothysit/AnalysisPipeline/networkPlotOverTime.gif';

for nT = 1:size(corrMatrixOverT, 3)
    adjM = corrMatrixOverT(:, :, nT);
    z = sum(adjM, 1);
    
    StandardisedNetworkPlot(adjM, Params.coords, edge_thresh, z, plotType, FN, pNum, Params, lagval, e);
    % Capture the plot as an image 
    title(sprintf('T = %.f', nT));
    frame = getframe(Params.oneFigure); 
    im = frame2im(frame); 
    [imind,cm] = rgb2ind(im,256); 

    % Write to the GIF File 
    if nT == 1 
          imwrite(imind,cm,filename,'gif', 'Loopcount',inf); 
    else 
          imwrite(imind,cm,filename,'gif','WriteMode','append'); 
    end 

    
    % clear figure 
    set(0, 'CurrentFigure', Params.oneFigure);
    clf reset

end 

