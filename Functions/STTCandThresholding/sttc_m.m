function tileCoef = sttc_m(N1v, N2v, dtv, Time, spike_times_1, spike_times_2)
%sttc calculates the spike timing tiling coefficient 
%   Originally written in C by Cutts and Eglen 
% https://github.com/CCutts/Detecting_pairwise_correlations_in_spike_trains/blob/master/spike_time_tiling_coefficient.c
%   See their 2014 paper on this 
% https://www.ncbi.nlm.nih.gov/pubmed/25339742

% INPUTS 
    % N1v           | The number of spikes in electrode 1 (double) 
    % N2v           | The number of spikes in electrode 2 (double)
    % dtv           | The delay (in seconds) (double) 
    % Time          | 2 x 1 vector containing the start time and end time 
    % of the recording (seconds), so that Time(2) - Time(1) = length of 
    % recording
    % spike_times_1 | The spike times in electrode 1 (in seconds)  (vector)
    % spike_times_2 | the spikes times in electrode 2 (in seconds) (vector)

% OUTPUT

    % tileCoef | The tiling coefficient

% Now tranlsated to matlab by Tim Sit (sitpakhang@gmail.com)
% I have included some of the original comments
% Last Update: 20180516 
% This copy is from the github repo for the organoids paper
% https://github.com/Timothysit/organoids/blob/c05c2b16ab0d58fd87d2539ad9e1b92596aaad90/correlation_analysis/sttc.m

N1 = N1v; % need to think about these gloabl var names
N2 = N2v; 
dt = dtv; 

if N1 == 0 || N2 == 0 
   %  index = R_NaN; % I think this just means NaN values
   index = NaN; 
   
else 
    T = Time(2) - Time(1); 
    TA = run_T(N1, dt, Time(1), Time(2), spike_times_1); 
    TA = TA / T; 
    TB = run_T(N2, dt, Time(1), Time(2), spike_times_2); 
    TB = TB / T; 
    PA = run_P(N1, N2, dt, spike_times_1, spike_times_2); 
    PA = PA / N1; 
    PB = run_P(N2, N1, dt, spike_times_2, spike_times_1); 
    PB = PB / N2; 
    index = 0.5 * (PA - TB) / (1 - TB * PA) + 0.5 * (PB - TA) / (1 - TA * PB);
end 

tileCoef = index; 


    function Nab = run_P(N1, N2, dt, spike_times_1, spike_times_2)
        Nab = 0; 
        j = 1; % change to 1 for 1 indexing
        % also note the switch from 0 to 1 indexing
        for i = 1:N1
            while j <= N2 % changed to <= for 1 indexing
                if abs(spike_times_1(i) - spike_times_2(j)) <= dt
                    Nab = Nab + 1; 
                    break 
                elseif spike_times_2(j) > spike_times_1(i) 
                    break
                else 
                    j = j + 1;
                end 
            end 
        end 
    end


    function time_A = run_T(N1v, dtv, startv, endv, spike_times_1)
        dt = dtv; 
        start = startv; 
        endvv = endv; % end is not a valid variable name in MATLAB 
        tempN = N1v; % changed N1 into tempN as nested function variables are declared
        % globally. This is problematic when N1v and N2v are different
        % values
        
        % maximum
        time_A = 2 * tempN * dt; 
        
        % if just one spike in train 
        if tempN == 1
            
            if spike_times_1(1) - start < dt 
                time_A = time_A - start + spike_times_1(1) - dt; 
            elseif spike_times_1(1) + dt > endvv 
                time_A = time_A - spike_times_1(1) - dt + endvv; 
            end
        
            % if more than one spike in train 
        else 
            i = 1; % added by TS
            while i < tempN % switched from N1 - 1, to take account of 1 indexing
            
                diff = spike_times_1(i+1) - spike_times_1(i); 
                
                if diff < 2 * dt 
                    % subtract overlap 
                    time_A = time_A -2 * dt + diff; 
                end 
                 
                i = i + 1; 
            end 
            
            % check if spikes are within dt of the start and/or end, if so
            % just need to subtract overlap of first and/or last spike as
            % all within-train overlaps have been accounted for 
            
            if spike_times_1(1) - start < dt 
                time_A = time_A - start + spike_times_1(1) - dt; 
            end 
            
            if endvv - spike_times_1(tempN) < dt % switched from N1 - 1 to N1 to for 1 indexing
                time_A = time_A - spike_times_1(tempN) - dt + endvv; 
            end 
       
            
        end 
                
    
        
    end 


end