

Params.output_spreadsheet_file_type = 'csv';
% Sampling frequency of your recordings
Params.fs = 25000; % HPC: 25000, Axion: 12500;
Params.dSampF = 25000; % down sampling factor for spike detection check, 
% by default should be equal to your recording sampling frequency
Params.potentialDifferenceUnit = 'uV';  

struct2dlg(Params)