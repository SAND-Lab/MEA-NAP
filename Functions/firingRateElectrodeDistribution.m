function firingRateElectrodeDistribution(File, Ephys, Params, Info, figFolder)
%{
% Plots the firing rate distribution across electrodes
Parameters
----------
File : 
Ephys : 
Params : 
Info : 

Returns
-------
None

%}

% create a half violin plot of the firing rate for individual electrodes

p = [50 50 500 600];
set(0, 'DefaultFigurePosition', p)
F1 = figure;

HalfViolinPlot(Ephys.FR,1,[0.5 0.5 0.5],0.3)
xlim([0.5 1.5])
xticks([])
xlabel(strcat('age',num2str(cell2mat(Info.DIV))))
aesthetics
ylabel('mean firing rate per electrode (Hz)')
title({strcat(regexprep(File,'_','','emptymatch')),' '});
ax = gca;
ax.TitleFontSizeMultiplier = 0.7;

max_ephys_fr = max(Ephys.FR);
max_ephys_fr = max([max_ephys_fr, 0.1]);  % ensures a minimum of 0.1
ylim([0 max_ephys_fr+max_ephys_fr*0.15])

%% save the figure
figName = 'FiringRateByElectrode';
figPath = fullfile(figFolder, figName);
pipelineSaveFig(figPath, Params.figExt, Params.fullSVG);

close(F1); 
  
end