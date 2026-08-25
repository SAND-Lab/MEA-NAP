%% Test trace 
traceDur = 1; % in seconds 
fs = 10000;
trace = zeros(traceDur * fs, 1);
% trace = 0;
Wid = [0.4000 0.8000];
% Wid = [0.00001 0.8]; % [0.4000    0.4000];
Ns = 5;
wname = 'bior1.5';

spikeTimes = detectSpikesWavelet(trace, fs/1000, Wid, Ns, 'l', L, wname, 0, 0);




%% Test specifically the loop

Ns = 5;
c = [0; 0; 0; 0; 0];
% W = [6  8 10    12    14];
W = [nan nan nan nan nan];

for i = 1:Ns
    Sigmaj = median(abs(c(i,1:round(W(i)):end) - mean(c(i,:))))/0.6745;
end 

%% Determine scales
SFr = 25000;
Wid = [0.4000    0.8000];
Ns = 5;
wname = 'bior1.5';
% W = determine_scales(wname,Wid,SFr,Ns);


 