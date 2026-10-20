function idx2 = get_spike_pos(input_sig, fs, orig_sig, params)
% get_spike_pos computes spike positions from thresholded data
%
% This function computes the exact spike locations based on a thresholded
% signal. The spike locations are indicated as non-zero elements in
% input_sig and are accordingly evaluated.
%
% The outputs are the spike positions in absolute index values (no time
% dependance).
% 
% Parameters 
% ----------
% input_sig : 
% fs : int 
%     sampling frequency (Hz)
% orig_sig : 
% params : 
% Author: F.Lieb, February 2016


%Define a fixed spike duration, prevents from zeros before this duration is
%over
%maxoffset
spikeduration = 10e-4*fs; %10e-4
%minoffset
minoffset = 3e-4*fs; %3e-4

offset = floor(5e-4*fs); %5e-4 %was 2e-4, dunno why
L = length(input_sig);
L2 = length(orig_sig);

switch params.method
    case 'numspikes'
        out = input_sig;
        np = 0;
        idx2 = zeros(1,params.numspikes);
        while (np < params.numspikes)
            [~, idxmax] = max(out);
            idxl = idxmax;
            idxr = idxmax;
            out(idxmax) = 0;
            offsetcounter = 0;
            while( (out(max(1,idxl-2)) < out(max(1,idxl-1)) ||...
                    offsetcounter < minoffset) &&...
                    offsetcounter < spikeduration )
                out(max(1,idxl-1)) = 0;
                idxl = idxl-1;
                offsetcounter = offsetcounter + 1;
            end
            offsetcounter = 0;
            while( (out(min(L,idxr+2)) < out(min(L,idxr+1)) ||...
                    offsetcounter < minoffset ) &&...
                    offsetcounter < spikeduration )
                out(min(L,idxr+1)) = 0;
                idxr = idxr+1;
                offsetcounter = offsetcounter + 1;
            end
            %new approach

            indexx = min(L2, idxmax-offset:idxmax+offset);
            %indexx = min(L2,idxl-offset:idxr+offset); %old approach
            indexx = max(offset,indexx);
            idxx = find( abs(orig_sig(indexx)) == ...
                max( abs(orig_sig(indexx) )),1,'first');
            idx2(np+1) = idxmax - offset + idxx-1;
            np = np + 1;
        end
    case {'energy'}
        rel_norm = params.rel_norm;
        p = params.p;
        ysig = input_sig;
        normy = norm(input_sig);
        L = length(input_sig);
        %min and max length of signal duration
        maxoffset = 12;
        minoffset = 6;
        offset = 5;
        idx2 = [];
        np = 0;
        maxspikecount = 300;
        temp = 0;

        %while( norm(ysig) > (1-p)*normy )
        while( 1 )
            norm_old = norm(ysig);
            [~, idxmax] = max(ysig);
            idxl = idxmax;
            idxr = idxmax;
            ysig(idxmax) = 0;
            offsetcounter = 0;
            while ( ( ysig(max(1,idxl-2)) < ysig(max(1,idxl-1)) ||...
                    offsetcounter < minoffset ) && ...
                    offsetcounter < maxoffset )
                ysig(max(1,idxl-1)) = 0;
                idxl = idxl - 1;
                %if (ysig(max(1,idxl))==0)
                %    break;
                %end
                offsetcounter = offsetcounter + 1;
            end
            offsetcounter = 0;
            while ( ( ysig(min(L,idxr+2)) < ysig(min(L,idxr+1)) ||...
                    offsetcounter < minoffset ) && ...
                    offsetcounter < maxoffset )
                ysig(min(L,idxr+1)) = 0;
                idxr = idxr + 1;
                %if (ysig(min(L,idxr)) == 0)
                %    break;
                %end
                offsetcounter = offsetcounter + 1;
            end

            indexx = min(L, idxmax-offset:idxmax+offset);
            %indexx = min(L2,idxl-offset:idxr+offset); %old approach
            indexx = max(offset,indexx);
            idxx = find( abs(orig_sig(indexx)) == ...
                max( abs(orig_sig(indexx) )),1,'first');
            idx2(np+1) = idxmax - offset + idxx-1;
            np = np + 1;

            fprintf('rel norm: %f\n', (norm_old-norm(ysig))/norm_old);
            temp(np+1) = (norm_old-norm(ysig))/norm_old;
            if (norm_old-norm(ysig))/norm_old < rel_norm
                if length(idx2)>1
                    idx2 = idx2(1:end-1);
                else
                    idx2 = [];
                end
                break
            end
            if  np > maxspikecount
                break;
            end
        end
        %figure(2), plot(temp);
    case {'auto','lambda'}
        %helper variables
        idx2=[];
        iii=1;
        test2 = input_sig;
        %loop until the input_sig is only zeros
        while (sum(test2) ~= 0)
            %get the first nonzero position
            tmp = find(test2,1,'first');
            test2(tmp) = 0;
            %tmp2 is the counter until the spike duration
            tmp2 = min(length(test2),tmp + 1);%protect against end of vec
            counter = 0;
            %search for the end of the spike
            while(test2(tmp2) ~= 0 || counter<spikeduration )
                test2(tmp2) = 0;
                tmp2 = min(length(test2),tmp2 + 1);
                counter = counter + 1;
            end
            %spike location is in intervall [tmp tmp2], look for the max
            %element in the original signal with some predefined offset:
            indexx = min(length(orig_sig),tmp-offset:tmp2+offset);
            indexx = max(offset,indexx);
            idxx = find( abs(orig_sig(indexx)) == ...
                max( abs(orig_sig(indexx) )),1,'first');
            idx2(iii) = tmp - offset + idxx-1;
            iii = iii+1;
        end
    otherwise
        error('unknown method');
end
end

