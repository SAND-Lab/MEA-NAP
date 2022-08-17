% Generate some numbers to test if STTC is running

spike_times_1 = [1, 5, 3];
spike_times_2 = [1, 7, 8, 10];
N1v = length(spike_times_1);
N2v = length(spike_times_2);
dtv = 0.1;
Time = [1, 10];
tileCoef = sttc(N1v, N2v, dtv, Time, spike_times_1, spike_times_2);