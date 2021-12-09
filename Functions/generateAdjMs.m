function [adjMs] = generateAdjMs(spikeTimes,ExN,Params,Info,HomeDir)

% create AdjM for a series of lag values

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
                Info.duration_s, Params.ProbThreshRepNum);
            cd('3_EdgeThresholdingCheck')
            if Params.figMat == 1
                saveas(gcf,strcat(char(Info.FN),num2str(lag),'msLagProbThreshCheck.fig'));
            end
            if Params.figPng == 1
                saveas(gcf,strcat(char(Info.FN),num2str(lag),'msLagProbThreshCheck.png'));
            end
            if Params.figEps == 1
                saveas(gcf,strcat(char(Info.FN),num2str(lag),'msLagProbThreshCheck.eps'));
            end
            close all
            cd(HomeDir); cd(strcat('OutputData',Params.Date))
            
        else % otherwise just generate the adjM
            [adjM, adjMci] = adjM_thr_parallel(spikeTimes, Params.SpikesMethod, lag, Params.ProbThreshTail, Params.fs,...
                Info.duration_s, Params.ProbThreshRepNum);
        end
        
        
    else % if no random checks for probabilistic thresholding
        [adjM, adjMci] = adjM_thr_parallel(spikeTimes, Params.SpikesMethod, lag, Params.ProbThreshTail, Params.fs,...
            Info.duration_s, Params.ProbThreshRepNum);
        
    end
    
    eval(['adjMs.adjM' num2str(lag) 'mslag = adjMci;']);
end

end