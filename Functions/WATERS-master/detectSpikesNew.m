classdef detectSpikes
    
    properties (Access = public)
        data_path;
        save_path;
        file_list;
        params;
        data;
        trace;
        channel;
        spike_train;
        spike_times;
        cost;
        save_name;
        file_name;
        channels;
    end
    
    methods (Access = public)
        
        function main(self)
            
            addpath(self.data_path);
            for file = 1:length(self.file_list)
                self.file_name = self.file_list(file).name;
                file_data = load(self.file_name);
                self.data = file_data.dat;
                self.params.fs = file_data.fs;
                self.channels = file_data.channels;
                filtering(self);
                detectSpikes(self);
                  
            end
        end
        
        function filtering(self)
            lowpass = 600;
            highpass = 8000;
            wn = [lowpass highpass] / (self.params.fs / 2);
            filterOrder = 3;
            [b, a] = butter(filterOrder, wn);
            self.data = filtfilt(b, a, double(self.data));
        end
        
        function detectSpikes(self)
            for cost = self.params.costList
                self.cost = cost;
                self.save_name = [self.save_path file_name(1:end-4) '_L_' num2str(cost) '_spikes.mat'];
                for channel = 1:min(size(self.data))
                    self.channel = channel;
                    self.trace = self.data(:, channel);
                    for method = methods
                        self.method = method;
                        if startsWith(method, 'thr')
                            detectSpikesThreshold(self);
                        else
                            detectSpikesCWT(self);
                        end
                        
                        switch self.params.unit
                            case 's'
                                spike_train = self.spike_train/25000;
                            case 'ms'
                                spike_train = self.spike_train/25;
                            otherwise
                                spike_train = self.spike_train;
                        end
                        spike_struct.(method) = spike_train;
                    end
                    spikeTimes{channel} = spike_struct.(method);
                end
                spikeDetectionResult = struct();
                spikeDetectionResult.params = self.params;
                
                disp(['Saving results to: ' save_name]);
                
                varsList = {'spikeTimes', 'channels', 'spikeDetectionResult', ...
                    'spikeWaveforms'};
                save(save_name, varsList{:}, '-v7.3');
            end
        end
        
        function detectSpikesThreshold(self)
            
            % method: 'thr3p5', multiplier: 3.5
            multiplier = strrep(wname, 'p', '.');
            multiplier = strrep(multiplier, 'thr', '');
            multiplier = str2num(multiplier);
            
            % Determine threshold
            s = median(abs(self.trace-mean(self.trace)))/0.6745;
            m = median(self.trace);
            
            threshold = m - self.params.multiplier*s;
            
            % Detect spikes (defined as threshold crossings)
            spikeTrain = zeros(size(self.trace));
            spikeTrain = self.trace < threshold;
            spikeTrain = double(spikeTrain);
            
            % Impose the refractory period [ms]
            refPeriod = 0.2 * 10^-3 * self.params.fs; % NOTE: hard-coded to 0.2 ms
            for i = 1:length(spikeTrain)
                if spikeTrain(i) == 1
                    refStart = i + 1;
                    refEnd = round(i + refPeriod);
                    if refEnd > length(spikeTrain)
                        spikeTrain(refStart:length(spikeTrain)) = 0;
                    else
                        spikeTrain(refStart:refEnd) = 0;
                    end
                end
            end
            
            self.params.channel_thr(self.channel) = threshold;
            self.spike_train = find(spikeTrain == 1);
        end
        
        function detectSpikesCWT(self)
        end
        
        function getTemplate(self)
            detectSpikesThreshold(self);
            
            
        end
        
        function adaptWavelet(self)
        end
        
        function detectSpikesWavelet(self)
            Signal = self.trace;
            SFr = self.params.fs;
            Wid = self.params.wid;
            Ns = self.params.nScales;
            option = 'l';
            L = self.cost;
            wname = self.method;
            
            %admissible wavelet families (more wavelets could be added)
            wfam = {'bior1.5','bior1.3','sym2','db2','haar','mea'};
            
            if sum(strcmp(wname,wfam)) == 0
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
            self.spike_times.(self.method) = spikeFrames;
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
            
            switch num2str(wname)
                
                case 'haar'
                    for i = 1:Ns
                        Scale(i) = Width(i)/dt - 1;
                    end
                case 'db2'
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
                case 'sym2'
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
                case 'bior1.3'
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
                case 'bior1.5'
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
                    
                case 'mea'
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
                    
                otherwise
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
        
        function fcn = parse(Index,SFr,Wid)
            
            Refract = 0.2;    %[ms] the refractory period
            Refract = round(Refract * SFr);
            Merge = mean(Wid);
            Merge = round(Merge * SFr);
            
            Index([1 end]) = 0;   %discard spikes located at the first and last samples
            
            ind_ones = find(Index == 1,1);    %find where the ones are
            
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
                        if Diff < Refract && Diff > Merge
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
        
        
    end
end