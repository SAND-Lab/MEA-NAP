function [spikepos, out_] = SWTTEO(self, in,params)
%SWTTEO Detects Spikes Location using a modified WTEO approach
%   Usage:  spikepos = swtteo(in);
%           spikepos = swtteo(in,params);
%
%   Input parameters:
%       in_struc:   Input structure which contains
%                       M:      Matrix with data, stored columnwise
%                       SaRa:   Sampling frequency
%       optional input parameters:
%                       none
%   Output parameters:
%       spikepos:   Timestamps of the detected spikes stored columnwise
%
%   Description:
%       swtteo(in,params) computes the location of action potential in
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
%
%   Author: F. Lieb, February 2016
            
    if nargin<2
        params = struct;
    end
    
    %parse inputs
    [params,s,fs] = parse_input(self, in,params);
    TEO = @(x,k) (x.^2 - myTEOcircshift(self, x,[-k, 0]).*myTEOcircshift(self,x,[k, 0]));
    [L,c] = size(s);
    if L==1
        s = s';
        L = c;
        c = 1;
    end
    
    
    %do zero padding if the L is not divisible by a power of two
    pow = 2^params.wavLevel;
    if rem(L,pow) > 0
        Lok = ceil(L/pow)*pow;
        Ldiff = Lok - L;
        s = [s; zeros(Ldiff,c)];
    end
    
    %testing showed prefiltering didnt improve the results
    %prefilter signal
    if params.filter
        if ~isfield(params,'F1')
            params.Fstop = 100;
            params.Fpass = 200;
            Apass = 0.2;
            Astop = 80;
            params.F1 = designfilt(   'highpassiir',...
                'StopbandFrequency',params.Fstop ,...
                'PassbandFrequency',params.Fpass,...
                'StopbandAttenuation',Astop, ...
                'PassbandRipple',Apass,...
                'SampleRate',fs,...
                'DesignMethod','butter');
        end
        f = filtfilt(params.F1,s);
    else
        f = s;
    end
    
    %non vectorized version:
    % [SWTa,~] = swt(s,wavLevel,wavelet);
    %     out22 = TEO(SWTa);
    
    %vectorized version:
    lo_D = wfilters(params.wavelet);
    out_ = zeros(size(s));
    ss = f;
    for k=1:params.wavLevel
        %Extension
        lf = length(lo_D);
        ss = extendswt(self,ss,lf);
        %convolution
        swa = conv2(ss,lo_D','valid');
        swa = swa(2:end,:); %even number of filter coeffcients
        %apply teo to swt output
        
        
        temp = abs(TEO(swa,1));
        
        if params.smoothing
            wind = hamming(params.winlength);
            %wind = sqrt(3*sum(wind.^2) + sum(wind)^2);
            %temp = filtfilt(wind,1,temp);
            if params.normalize_smoothingwindow
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
    switch params.method
        case 'auto'
            %         global_fac = 1.11e+03;%1.6285e+03; %540;%1800;%430; %1198; %change this
            global_fac = 430;%1.6285e+03; %540;%1800;%430; %1198; %change this
            if c == 1
                [CC,LL] = wavedec(s,5,'sym5');
                lambda = global_fac*wnoisest(CC,LL,1);
                thout = wthresh(out_,'h',lambda);
                spikepos = get_spike_pos(self,thout,fs,s,params);
            else
                spikepos = cell(c,1);
                for jj=1:c
                    [CC,LL] = wavedec(s(:,jj),5,'sym5');
                    lambda = global_fac*wnoisest(CC,LL,1);
                    thout = wthresh(out_(:,jj),'h',lambda);
                    spikepos{jj}=get_spike_pos(self,thout,fs,s(:,jj),params);
                end
            end
        case 'auto2'
            %         global_fac = 9.064e+02;%1.3454e+03;%800;%1800;%430; %1198; %change this
            global_fac = 1198;
            params.method = 'auto';
            if c == 1
                [CC,LL] = wavedec(out_,5,'sym5');
                lambda = global_fac*wnoisest(CC,LL,1);
                thout = wthresh(out_,'h',lambda);
                spikepos = get_spike_pos(self,thout,fs,s,params);
            else
                spikepos = cell(c,1);
                for jj=1:c
                    [CC,LL] = wavedec(out_(:,jj),5,'sym5');
                    lambda = global_fac*wnoisest(CC,LL,1);
                    thout = wthresh(out_(:,jj),'h',lambda);
                    spikepos{jj}=get_spike_pos(self,thout,fs,s(:,jj),params);
                end
            end
        case 'numspikes'
            if c == 1
                spikepos=get_spike_pos(self,out_,fs,s,params);
            else
                spikepos = cell(1,c);
                params_tmp = params;
                for jj=1:c
                    % extract spike positions from wteo output
                    params_tmp.numspikes = params.numspikes(jj);
                    spikepos{jj}=get_spike_pos(self,out_(:,jj),fs,s(:,jj),params_tmp);
                end
            end
        case 'lambda'
            thout = wthresh(out_,'h',params.lambda);
            spikepos = get_spike_pos(self,thout,fs,s,params);
        case 'energy'
            params.p = 0.80;
            params.rel_norm =  5.718e-3;%5.718e-3;%4.842e-3;%22e-5;%1.445e-4;
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
                spikepos = get_spike_pos(self,out_,fs,s,params);
            else
                spikepos = cell(c,1);
                for jj=1:c
                    if wdenoising == 1
                        out_(:,jj) = wden(out_(:,jj),tptr,'h','mln',n,w);
                    end
                    spikepos{jj} = get_spike_pos(self,out_(:,jj),fs,s(:,jj),params);
                end
            end
        otherwise
            error('unknown detection method specified');
    end
end