function [] = tempdynamicsPC(spikeTimes,lagval)

segLength = 15; % length of segment in seconds
segShift = 5; % shift between segments in seconds

lag = lagval;

ItNum =(duration_s/segShift)-(segLength/segShift);

for i = 1:ItNum
    
    startT = segShift*(i-1);
    endT = segShift*(i-1) + 30;
    
    for uu = 1:length(spikeTimes)
        temp_spike_times = double(spikeTimes{1,uu}.(method));
        temp_spike_times(temp_spike_times<=startT) = [];
        temp_spike_times(temp_spike_times>endT) = []; 
        temp_spike_times = temp_spike_times-startT;
        spikeTimesSeg{1,uu}.(method) = temp_spike_times;
        clear temp_spike_times
    end
    
    cd('Functions')
    cd('STTCandThresholding')
    [~, adjMci] = adjM_thr_parallel(spikeTimesSeg, method, lag, tail, fs,...
        segLength, rep_num);
    cd(HomeDir)
    
    adjMci(adjMci<0) = 0;
    adjMci(isnan(adjMci)) = 0;   
    
    aNtemp = sum(adjMci,1);
    iN = find(aNtemp==0);
    aNtemp(aNtemp==0) = [];
    aN = length(aNtemp);  
    clear aNtemp
    
    adjMci(iN,:) = [];
    adjMci(:,iN) = [];
    
    % Modularity
    [Ci,~,~] = mod_consensus_cluster_iterate(adjMci,0.4,50);

    % participation coefficient
    PC = participation_coef(adjMci,Ci,0);
    
    PCt(i) = mean(PC);
    
    clear spikeTimesSeg adjM adjMci aN iN Ci PC
end
            
            
            
  