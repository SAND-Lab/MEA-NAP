function spikeFrames = detectSpikesWavelet(...
    Signal, SFr, Wid, Ns, option, L, wname, PltFlg, CmtFlg)

% DETECT_SPIKES_WAVELET wavelet based algorithm for detection of transients
% from neural data.
%
%   TE=DETECT_SPIKES_WAVELET(Signal,SFr,Wid,Ns,option,L,wname,PltFlg,CmtFlg)
%
%   Signal - extracellular potential data to be analyzed 1 x Nt;
%
%   SFr - sampling frequency [kHz];
%
%   Wid - 1 x 2 vector of expected minimum and maximum width [msec] of transient
%   to be detected Wid=[Wmin Wmax]. For most practical purposes Wid=[0.5 1.0];
%
%   Ns - (scalar): the number of scales to use in detection (Ns >= 2);
%
%   option - (string): the action taken when no coefficients survive hard
%   thresholding
%   'c' means conservative and returns no spikes if P(S) is found to be 0
%   'l' means assume P(S) as a vague prior (see the original reference)
%
%   L is the factor that multiplies [cost of comission]/[cost of omission].
%   For most practical purposes -0.2 <= L <= 0.2. Larger L --> omissions
%   likely, smaller L --> false positives likely. For unsupervised
%   detection, the suggested value of L is close to 0.
%
%   wname - (string): the name of wavelet family in use
%           'bior1.5' - biorthogonal
%           'bior1.3' - biorthogonal
%           'db2'     - Daubechies
%           'sym2'    - symmlet
%           'haar'    - Haar function
%   Note: sym2 and db2 differ only by sign --> they produce the same
%   result;
%
%   PltFlg - (integer) is the plot flag:
%   PltFlg = 1 --> generate figures, otherwise do not;
%
%   CmtFlg - (integer) is the comment flag,
%   CmtFlg = 1 --> display comments, otherwise do not;
%
%   TE is the vector of event occurrence times;
%
%   Reference: Z. Nenadic and J.W. Burdick, Spike detection using the
%   continuous wavelet transform, IEEE T. Bio-med. Eng., vol. 52,
%   pp. 74-87, 2005.

%   Originally developed by:
%   Zoran Nenadic
%   California Institute of Technology
%   May 2003
%
%   Modified by:
%   Zoran Nenadic
%   University of California, Irvine
%   February 2008
%
%   Modified by:
%   Jeremi Chabros
%   University of Cambridge
%   November 2020

% TS 2021-05-03: Allowing for multiple mea templates 
% also changed from switch/case to if/else for flexibility


%admissible wavelet families (more wavelets could be added)
wfam = {'bior1.5','bior1.3','sym2','db2','haar','mea'};

if sum(contains(wname,wfam)) == 0  % orignally strcmp
    error('unknown wavelet family')
elseif CmtFlg == 1
    disp(['wavelet family: ' wname])
    to = clock;
end

%make sure signal is zero-mean
Signal = Signal - mean(Signal);

Nt = length(Signal);      %# of time samples

%define relevant scales for detection
W = determine_scales(wname,Wid,SFr,Ns);

%initialize the matrix of thresholded coefficients
ct = zeros(Ns,Nt);

try
    %get all coefficients
    c = cwt(Signal,W,wname);
catch
    error('Wavelet Toolbox not found');
end

%define detection parameter
Lmax = 36.7368;       % log(Lcom/Lom), where the ratio is the maximum
% allowed by the current machine precision
L = L * Lmax;

%initialize the vector of spike indicators, 0-no spike, 1-spike
Io = zeros(1,Nt);

%loop over scales
for i = 1:Ns
    
    %take only coefficients that are independent (W(i) apart) for median
    %standard deviation
    Sigmaj = median(abs(c(i,1:round(W(i)):end) - mean(c(i,:))))/0.6745;
    Thj = Sigmaj * sqrt(2 * log(Nt));     %hard threshold
    index = find(abs(c(i,:)) > Thj);
    if isempty(index) && strcmp(num2str(option),'c')
        %do nothing ct=[0];
    elseif isempty(index) && strcmp(num2str(option),'l')
        Mj = Thj;
        %assume at least one spike
        PS = 1/Nt;
        PN = 1 - PS;
        DTh = Mj/2 + Sigmaj^2/Mj * [L + log(PN/PS)];    %decision threshold
        DTh = abs(DTh) * (DTh >= 0);                 %make DTh>=0
        ind = find(abs(c(i,:)) > DTh);
        if isempty(ind)
            %do nothing ct=[0];
        else
            ct(i,ind) = c(i,ind);
        end
    else
        Mj = mean(abs(c(i,index)));       %mean of the signal coefficients
        PS = length(index)/Nt;            %prior of spikes
        PN = 1 - PS;                        %prior of noise
        DTh = Mj/2 + Sigmaj^2/Mj * [L + log(PN/PS)];   %decision threshold
        DTh = abs(DTh) * (DTh >= 0);         %make DTh>=0
        ind = find(abs(c(i,:)) > DTh);
        ct(i,ind) = c(i,ind);
    end
    
    %find which coefficients are non-zero
    ct(ct<0)=0; % Delete if you allow positive peaks
    Index = ct(i,:) ~= 0;
    
    %make a union with coefficients from previous scales
    Index = or(Io,Index);
    Io = Index;
end

spikeFrames = parse(Index,SFr,Wid);

% PLOT RESULTS
if PltFlg == 1
    
    tiledlayout(3,1,'tilespacing','none','padding','none');
    
    nexttile
    scale = 64./[max(abs(c),[],2) * ones(1,Nt)];
    temp = zeros(1,Nt);
    temp(spikeFrames) = 1;
    imagesc(flipud(abs(c)) .* scale)
    colormap((gray));

    yl = ylabel('|C| across scales');
        yl.VerticalAlignment = 'bottom';
        yl.HorizontalAlignment = 'right';
%     ypos = get(gca,'position');
%     yl.Position(2) = 3.5;
    
    Wt = [fliplr(W)];
    set(gca,'YTick', [1,Ns],'YTickLabel',Wt([1,end]),...
        'XTick',[])
%     title(['|C| across scales: ' num2str(W)])
    hold on
    coefs_all=(flipud(abs(c)).*scale)';
    coefs = abs(sum(coefs_all,2));
    coefs = rescale(coefs, 0, Ns);
%     plot(-coefs+0.6,'k','linewidth',0.5);
%     xlim([1 length(c)])
%     ylim([-Ns Ns])
    box off
    
    nexttile
    plot(Signal,'Color',[0.7 0.7 0.7],'LineWidth',1)
    xl = get(gca,'xlim');
    yl = get(gca,'ylim');
    hold on
    plot(-ct','-o','LineWidth',0.5,'MarkerFaceColor','k', ...
        'MarkerSize',4, 'color', [0.8 0.4 0]);
    xlabel('Time (samples)')
    yyaxis left
    ylabel("Voltage ("+char(956)+"V)");
    yyaxis right
    ylabel('Coefficients')
    set(gca,'XLim',[1 Nt], 'xcolor','none', 'tickdir','out')
    set(gca, 'ycolor', [0.8 0.4 0]);
    box off
    
    nexttile
    plot(Signal, 'k','linewidth',1);
    hold on
    scatter(spikeFrames, repmat(max(Signal), 1, length(spikeFrames)), 'v', 'filled','markerfacecolor',[0 0.5 0]);
    box off
    set(gcf,'color','w')
    xlabel('Time (ms)')
    ylabel("Voltage ("+char(956)+"V)");
    set(gca, 'xticklabel', get(gca,'xtick')/25,...
        'tickdir','out')
    set(gca, 'xlim',[1 length(Signal)],'ylim',yl);
    
    set(findall(gcf,'-property','FontSize'),'FontSize',12);
    set(findall(gcf,'-property','FontName'),'FontName','Roboto')
end

if CmtFlg == 1
    disp([num2str(length(spikeFrames)) ' spikes found'])
    disp(['elapsed time: ' num2str(etime(clock,to))])
end
end


function Scale = determine_scales(wname,Wid,SFr,Ns)

%Ns - # of scales

dt = 1/SFr;  %[msec]

%signal sampled @ 1 KHz
Signal = zeros(1,1000);
%create Dirac function
Signal(500) = 1;

Width = linspace(Wid(1),Wid(2),Ns);

%infinitesimally small number
Eps = 10^(-15);

ScaleMax = 4;
ScaleMax = ScaleMax*SFr;

wname_str = num2str(wname);

if strcmp(wname_str, 'haar')
        for i = 1:Ns
            Scale(i) = Width(i)/dt - 1;
        end
elseif strcmp(wname_str, 'db2')
        Scales = 2:ScaleMax;
        c = cwt(Signal,Scales,wname);
        for i = 1:length(Scales)
            %indicators of positive coefficients
            IndPos = (c(i,:) > 0);
            %indicators of derivative
            IndDer = diff(IndPos);
            %indices of negative slope zero crossings
            IndZeroCross = find(IndDer == -1);
            IndMax = IndZeroCross > 500;
            Ind(2) = min(IndZeroCross(IndMax))+1;
            IndMin = IndZeroCross < 500;
            Ind(1) = max(IndZeroCross(IndMin));
            WidthTable(i) = diff(Ind) * dt;
        end
        WidthTable = WidthTable + [1:length(Scales)] * Eps;
        %look-up table
        Scale = round(interp1(WidthTable,Scales,Width,'linear'));
elseif strcmp(wname_str, 'sym2')
        Scales = 2:ScaleMax;
        c = cwt(Signal,Scales,wname);
        for i = 1:length(Scales)
            %indicators of positive coefficients
            IndPos = (c(i,:) > 0);
            %indicators of derivative
            IndDer = diff(IndPos);
            %indices of positive slope zero crossings
            IndZeroCross = find(IndDer == 1);
            IndMax = IndZeroCross > 500;
            Ind(2) = min(IndZeroCross(IndMax))+1;
            IndMin = IndZeroCross < 500;
            Ind(1) = max(IndZeroCross(IndMin));
            WidthTable(i) = diff(Ind) * dt;
        end
        WidthTable = WidthTable + [1:length(Scales)] * Eps;
        %look-up table
        Scale = round(interp1(WidthTable,Scales,Width,'linear'));
elseif  strcmp(wname_str, 'bior1.3')
        Scales = 2:ScaleMax;
        c = cwt(Signal,Scales,wname);
        for i = 1:length(Scales)
            %indicators of positive coefficients
            IndPos = (c(i,:) > 0);
            %indicators of derivative
            IndDer = diff(IndPos);
            %indices of negative slope zero crossings
            IndZeroCross = find(IndDer == -1);
            IndMax = IndZeroCross > 500;
            Ind(2) = min(IndZeroCross(IndMax))+1;
            IndMin = IndZeroCross < 500;
            Ind(1) = max(IndZeroCross(IndMin));
            WidthTable(i) = diff(Ind) * dt;
        end
        WidthTable = WidthTable + [1:length(Scales)] * Eps;
        %look-up table
        Scale = round(interp1(WidthTable,Scales,Width,'linear'));
elseif strcmp(wname_str, 'bior1.5')
        Scales = 2:ScaleMax;
        c = cwt(Signal,Scales,wname);
        for i = 1:length(Scales)
            %indicators of positive coefficients
            IndPos = (c(i,:) > 0);
            %indicators of derivative
            IndDer = diff(IndPos);
            %indices of negative slope zero crossings
            IndZeroCross = find(IndDer == -1);
            IndMax = IndZeroCross > 500;
            Ind(2) = min(IndZeroCross(IndMax))+1;
            IndMin = IndZeroCross < 500;
            Ind(1) = max(IndZeroCross(IndMin));
            WidthTable(i) = diff(Ind) * dt;
        end
        WidthTable = WidthTable + [1:length(Scales)] * Eps;
        %look-up table
        Scale = round(interp1(WidthTable,Scales,Width,'linear'));
        
        % Custom data-driven wavelets added by JJC, November 2020
        % See: https://github.com/jeremi-chabros/CWT
        
elseif contains(wname_str, 'mea')
        Scales = 2:ScaleMax;
        c = cwt(Signal,Scales,wname);
        for i = 3:length(Scales)
            %indicators of positive coefficients
            IndPos = (c(i,:) > 0);
            %indicators of derivative
            IndDer = diff(IndPos);
            %indices of negative slope zero crossings
            IndZeroCross = find(IndDer == -1);
            IndMax = IndZeroCross > 500;
            Ind(2) = min(IndZeroCross(IndMax))+1;
            IndMin = IndZeroCross < 500;
            Ind(1) = max(IndZeroCross(IndMin));
            WidthTable(i) = diff(Ind) * dt;
        end
        WidthTable = WidthTable + [1:length(Scales)] * Eps;
        %look-up table
        Scale = round(interp1(WidthTable,Scales,Width,'linear'));
        
else
        error('unknown wavelet family')
end

NaNInd = isnan(Scale);

if sum(NaNInd) > 0
    warning(['Your choice of Wid is not valid given' ...
        ' the sampling rate and wavelet family'])
    if NaNInd(1) == 1
        disp(['Most likely Wid(1) is too small'])
    elseif NaNInd(Ns) == 1
        disp(['Most likely Wid(2) is too large'])
        disp(['Change the value on line: ''ScaleMax = 2'' to something larger'])
    end
end
end

%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

function fcn = parse(Index,SFr,Wid)

%This is a special function, it takes the vector Index which has
%the structure [0 0 0 1 1 1 0 ... 0 1 0 ... 0]. This vector was obtained
%by coincidence detection of certain events (lower and upper threshold
%crossing for threshold detection, and the appearance of coefficients at
%different scales for wavelet detection).
%The real challenge here is to merge multiple 1's that belong to the same
%spike into one event and to locate that event

Refract = 0.1;    %[ms] the refractory period -- can't resolve spikes
%that are closer than Refract;
Refract = round(Refract * SFr);

Merge = mean(Wid);      %[ms] merge spikes that are closer than Merge, since
%it is likely they belong to the same spike

Merge = round(Merge * SFr);


Index([1 end]) = 0;   %discard spikes located at the first and last samples

ind_ones = find(Index == 1);    %find where the ones are

if isempty(ind_ones)
    TE = [];
else
    temp = diff(Index);  %there will be 1 followed by -1 for each spike
    N_sp = sum(temp == 1); %nominal number of spikes
    
    lead_t = find(temp == 1);  %index of the beginning of a spike
    lag_t = find(temp == -1);  %index of the end of the spike
    
    for i = 1:N_sp
        tE(i) = ceil(mean([lead_t(i) lag_t(i)]));
    end
    
    i = 1;        %initialize counter
    while 0 < 1
        if i > (length(tE) - 1)
            break;
        else
            Diff = tE(i+1) - tE(i);
            if Diff < Refract & Diff > Merge
                tE(i+1) = [];      %discard spike too close to its predecessor
            elseif Diff <= Merge
                tE(i) = ceil(mean([tE(i) tE(i+1)]));  %merge
                tE(i+1) = [];                         %discard
            else
                i = i+1;
            end
        end
    end
    TE = tE;
end

fcn = TE;
end