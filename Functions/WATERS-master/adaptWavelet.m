function [newWaveletIntegral, newWaveletSqN] = adaptWavelet(aveWaveform, wavelet_name)

% Description:
%   Uses spike waveform to adapt custom wavelet that can be used for
%   continuous wavelet transform

% INPUT:
%   aveWaveform: average (mean or median) spike waveform

% OUTPUT:
%   newWaveletIntegral: area under the newly adapted wavelet
%   newWaveletSqN: square normm of the newly adapted wavelet

% Author:
%   Jeremy Chabros, University of Cambridge, 2020
%   email: jjc80@cam.ac.uk
%   github.com/jeremi-chabros/CWT

if ~exist('wavelet_name', 'var')
    wavelet_name = 'mea';
end 


template = aveWaveform;

% Interpolation
template = spline(1:length(template), template, linspace(1, length(template), 100));

% Gaussian smoothing
w = gausswin(10);
y = filter(w,1,template);
y = rescale(y);
y = y - mean(y);

% Pre-allocate
signal = zeros(1, 110);

% Center the template
signal(6:105) = y;

% Adapt the wavelet
[Y,X,~] = pat2cwav(signal, 'orthconst', 0, 'none');

% Test if a legitmate wavelet
dxval = max(diff(X));
newWaveletIntegral = dxval*sum(Y); %    Should be zero
newWaveletSqN = dxval*sum(Y.^2);
newWaveletSqN = round(newWaveletSqN,10); % Should be 1

% Save the wavelet
if newWaveletSqN == 1.0000

    % Using built-in cwt method requires saving the custom wavelet each
    % time - currently overwriting as there is no reason to retrieve the
    % wavelet
    
    wavelet_save_name = strcat(['mother', wavelet_name, '.mat']);
    
    save(wavelet_save_name, 'X', 'Y');
    % wavemngr('del', 'meaCustom');
    custom_family_name = strcat(wavelet_name, 'Custom');
    try 
        wavemngr('del', custom_family_name);
        del_wavelet_success = 1;
    catch
        del_wavelet_success = 0;
    end 
    
    % All wavelets cunstructed with wavemngr are type 4 wavelets
    % without a scaling function
    % wavemngr('add', 'meaCustom', wavelet_name, 4, '', 'mother.mat', [-100 100]);
    wavemngr('add', custom_family_name, wavelet_name, 4, '', wavelet_save_name, [-100 100]);
    wname = wavelet_name;
else
    disp('ERROR: Not a proper wavelet');
    disp(['Integral = ', num2str(newWaveletIntegral)]);
    disp(['L^2 norm = ', num2str(newWaveletSqN)]);
end
end
