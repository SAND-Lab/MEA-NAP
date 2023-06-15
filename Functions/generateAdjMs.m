function [adjMs, F1] = generateAdjMs(spikeTimes, ExN, Params, Info, HomeDir, oneFigureHandle)
%
% Create AdjM for a series of lag values
% 
% Parameters
% ----------
% spikeTimes : 
% ExN : 
% Params : struct
% Info : struct
% HomeDir : path 
% 
% Returns 
% -------
% adjMs : 

figFolder = fullfile(Params.outputDataFolder, ...
    strcat('OutputData',Params.Date), '3_EdgeThresholdingCheck');


for p = 1:length(Params.FuncConLagval)
    
    % lag value
    lag = Params.FuncConLagval(p);
    disp(lag)
    
    %% plots for random checks of probabilistic thresholding
    
    if Params.ProbThreshPlotChecks == 1
        
        % is the current experiment file and lag value one of the
        % random check points?
        for ii = 1:size(Params.randRepCheckP,2)
            Params.randRepCheckN(ii) = double(isequal([ExN lag],[Params.randRepCheckP(1,ii) Params.randRepCheckP(2,ii)]));
        end
        
        if sum(Params.randRepCheckN)>0  % if it is a randomly chosen check point:
            % plot data over incresing repetition number to check stability of
            % probabilistic thresholding
            [F1, adjM, adjMci] = adjM_thr_checkreps(spikeTimes, Params.SpikesMethod, lag, Params.ProbThreshTail, Params.fs,...
                Info.duration_s, Params.ProbThreshRepNum, oneFigureHandle);

            % Export figure
            for nFigExt = 1:length(Params.figExt)
                figName = strcat([char(Info.FN), num2str(lag), 'msLagProbThreshCheck', Params.figExt{nFigExt}]);
                figPath = fullfile(figFolder, figName);
                saveas(gcf, figPath);
            end 
            
            if ~Params.showOneFig
                close all
            else
                clf(F1)
            end 
            
        else % otherwise just generate the adjM
            [adjM, adjMci] = adjM_thr_parallel(spikeTimes, Params.SpikesMethod, lag, Params.ProbThreshTail, Params.fs,...
                Info.duration_s, Params.ProbThreshRepNum);
        end
        
        
    else % if no random checks for probabilistic thresholding
        [adjM, adjMci] = adjM_thr_parallel(spikeTimes, Params.SpikesMethod, lag, Params.ProbThreshTail, Params.fs,...
            Info.duration_s, Params.ProbThreshRepNum);
        
    end
    
    % TODO: slightly confusing here that the adjacency matrix being saved is
    % actually adjMci, perhaps the adjM outputf from previous function
    % should be renamed ot adjMnoThreshold
    eval(['adjMs.adjM' num2str(lag) 'mslag = adjMci;']);
end

end