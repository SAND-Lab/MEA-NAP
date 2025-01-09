function c_code_works = test_sttc_c_code()
%UNTITLED Summary of this function goes here
%   Detailed explanation goes here

Time = [1, 10];
spike_times_1 = [1, 4, 5, 8];
spike_times_2 = [2, 4.5, 6, 10];
dtv = 0.5; % in seconds, the delay time to look for conincidental spikes 
N1v = length(spike_times_1);
N2v = length(spike_times_2);

try
    tileCoef = sttc(N1v, N2v, dtv, Time, spike_times_1, spike_times_2); 
    c_code_works = 1;
catch 
    c_code_works = 0;
end 

end

