function [spikepos, out_] = SWTTEO(voltageTraces, fs, detectionParams)
%SWTTEO Detects Spikes Location using a modified WTEO approach
%   Usage:  spikepos = swtteo(voltageTraces, fs);
%           spikepos = swtteo(voltageTraces, fs, params);
%
% Parameters
% ----------
% voltageTraces : L x C matrix 
%     where L is the number of time samples of the recording 
%     and C is the number of channels
% fs : int 
%     sampling frequency in Hz
% detectionParams : strct 
%     optional input parameters
%     detectionParams.wavelet : str 
%         which wavelet method to use for spike detection, 
%         default to 'sym5'
% Output
% ------
% spikepos: Timestamps of the detected spikes stored columnwise
% out_ : 
%   Description:
%       swtteo(voltageTraces, fs, params) computes the location of action potential in
%       noisy sym5 sym5surements. This method is based on the work of N.
%       Nabar and K. Rajgopal "A Wavelet based Teager Engergy Operator for
%       Spike Detection in Microelectrode Array Recordings". The algorithm
%       therein was further improved by using a stationary wavelet
%       transform and a different thresholding concept.
%       For an unsupervised usage the sensitivity of the algorithm can be
%       adapted by changing the value of the variable global_fac in line
%       108. A larger value results in fewer detected spikes but also the
%       number of false positives decrease. Decreasing this factor makes it
%       more sensitive to detect spikes.
%
%   References:
%       tbd.
%
% Log 
% -----------------
% Author: F. Lieb, February 2016
% 2023 November: Tim Sit modified this to rely on more explicit variable 
% names and converted the code from object-oriented to functional
% programming

if nargin<2
    detectionParams = struct;
end


%% Parse inputs
% [params,s,fs] = parse_input(self, in,params);
%parse_input parses input variables
s = voltageTraces;
%Default settings for detection method
if ~isfield(detectionParams,'method')
    detectionParams.method = 'auto';
end
if strcmp(detectionParams.method,'numspikes')
    if ~isfield(detectionParams,'numspikes')
        error('please specify number of spikes in params.numspikes');
    end
end

%Default settings for stationary wavelet transform
if ~isfield(detectionParams,'wavLevel')
    detectionParams.wavLevel = 2;
end
if ~isfield(detectionParams, 'wavelet')
    detectionParams.wavelet = 'sym5';
end
if ~isfield(detectionParams, 'winlength')
    detectionParams.winlength = ceil(1.3e-3*fs); 
end
if ~isfield(detectionParams, 'normalize_smoothingwindow')
    detectionParams.normalize_smoothingwindow = 0;
end
if ~isfield(detectionParams, 'smoothing')
    detectionParams.smoothing = 1;
end
if ~isfield(detectionParams, 'filter')
    detectionParams.filter = 0;
end

%% TEO Shift

TEO = @(x,k) (x.^2 - myTEOcircshift(x,[-k, 0]).*myTEOcircshift(x,[k, 0]));
[L,c] = size(s);
if L==1
    s = s';
    L = c;
    c = 1;
end


%do zero padding if the L is not divisible by a power of two
pow = 2^detectionParams.wavLevel;
if rem(L,pow) > 0
    Lok = ceil(L/pow)*pow;
    Ldiff = Lok - L;
    s = [s; zeros(Ldiff,c)];
end

%testing showed prefiltering didnt improve the results
%prefilter signal
if detectionParams.filter
    if ~isfield(detectionParams,'F1')
        detectionParams.Fstop = 100;
        detectionParams.Fpass = 200;
        Apass = 0.2;
        Astop = 80;
        detectionParams.F1 = designfilt(   'highpassiir',...
            'StopbandFrequency',detectionParams.Fstop ,...
            'PassbandFrequency',detectionParams.Fpass,...
            'StopbandAttenuation',Astop, ...
            'PassbandRipple',Apass,...
            'SampleRate',fs,...
            'DesignMethod','butter');
    end
    f = filtfilt(detectionParams.F1,s);
else
    f = s;
end

%non vectorized version:
% [SWTa,~] = swt(s,wavLevel,wavelet);
%     out22 = TEO(SWTa);

%vectorized version:
lo_D = wfilters(detectionParams.wavelet);
out_ = zeros(size(s));
ss = f;
for k=1:detectionParams.wavLevel
    %Extension
    lf = length(lo_D);
    ss = extendswt(ss, lf);
    %convolution
    swa = conv2(ss,lo_D','valid');
    swa = swa(2:end,:); %even number of filter coeffcients
    %apply teo to swt output

    temp = abs(TEO(swa,1));

    if detectionParams.smoothing
        wind = hamming(detectionParams.winlength);
        %wind = sqrt(3*sum(wind.^2) + sum(wind)^2);
        %temp = filtfilt(wind,1,temp);
        if detectionParams.normalize_smoothingwindow
            wind = wind./(sqrt(3*sum(wind.^2) + sum(wind)^2));
        end
        temp2 = conv2(temp,wind','same');
        %temp = circshift(filter(wind,1,temp), [-3*1 1]);
    else
        temp2 = temp;
    end

    out_ = out_ + temp2;


    %dyadic upscaling of filter coefficients
    lo_D = dyadup(lo_D,0,1);
    %updates
    ss = swa;
end



%non-vectorized version to extract spikes...
switch detectionParams.method
    case 'auto'
        %         global_fac = 1.11e+03;%1.6285e+03; %540;%1800;%430; %1198; %change this
        global_fac = 430;%1.6285e+03; %540;%1800;%430; %1198; %change this
        if c == 1
            [CC,LL] = wavedec(s,5,'sym5');
            lambda = global_fac*wnoisest(CC,LL,1);
            thout = wthresh(out_,'h',lambda);
            spikepos = get_spike_pos(thout,fs,s,detectionParams);
        else
            spikepos = cell(c,1);
            for jj=1:c
                [CC,LL] = wavedec(s(:,jj),5,'sym5');
                lambda = global_fac*wnoisest(CC,LL,1);
                thout = wthresh(out_(:,jj),'h',lambda);
                spikepos{jj}=get_spike_pos(thout,fs,s(:,jj),detectionParams);
            end
        end
    case 'auto2'
        %         global_fac = 9.064e+02;%1.3454e+03;%800;%1800;%430; %1198; %change this
        global_fac = 1198;
        detectionParams.method = 'auto';
        if c == 1
            [CC,LL] = wavedec(out_,5,'sym5');
            lambda = global_fac*wnoisest(CC,LL,1);
            thout = wthresh(out_,'h',lambda);
            spikepos = get_spike_pos(thout,fs,s,detectionParams);
        else
            spikepos = cell(c,1);
            for jj=1:c
                [CC,LL] = wavedec(out_(:,jj),5,'sym5');
                lambda = global_fac*wnoisest(CC,LL,1);
                thout = wthresh(out_(:,jj),'h',lambda);
                spikepos{jj}=get_spike_pos(thout,fs,s(:,jj),detectionParams);
            end
        end
    case 'numspikes'
        if c == 1
            spikepos=get_spike_pos(out_,fs,s,detectionParams);
        else
            spikepos = cell(1,c);
            params_tmp = detectionParams;
            for jj=1:c
                % extract spike positions from wteo output
                params_tmp.numspikes = detectionParams.numspikes(jj);
                spikepos{jj}=get_spike_pos(out_(:,jj),fs,s(:,jj),params_tmp);
            end
        end
    case 'lambda'
        thout = wthresh(out_,'h',detectionParams.lambda);
        spikepos = get_spike_pos(thout,fs,s,detectionParams);
    case 'energy'
        detectionParams.p = 0.80;
        detectionParams.rel_norm =  5.718e-3;%5.718e-3;%4.842e-3;%22e-5;%1.445e-4;
        %wavelet denoising
        wdenoising = 0;
        n = 9;
        w = 'sym5';
        tptr = 'sqtwolog'; %'rigrsure','heursure','sqtwolog','minimaxi'


        if c == 1
            if wdenoising == 1
                out_ = wden(out_,tptr,'h','mln',n,w);
                %high frequencies, decision variable
                c = dgtreal(out_,{'hann',10},1,200);
                out_ = sum(abs(c).^2,1);
            end
            spikepos = get_spike_pos(out_,fs,s,detectionParams);
        else
            spikepos = cell(c,1);
            for jj=1:c
                if wdenoising == 1
                    out_(:,jj) = wden(out_(:,jj),tptr,'h','mln',n,w);
                end
                spikepos{jj} = get_spike_pos(out_(:,jj),fs,s(:,jj),detectionParams);
            end
        end
    otherwise
        error('unknown detection method specified');
end
end