/*==========================================================
 *   sttc.c -  High-performance mex implementation of Spike Time Tiling Coefficient.
 *   @Author: Jeremy Chabros (2021), https://github.com/jeremi-chabros
 *
 *   Originally written by Catherine S Cutts (2014):
 *   https://github.com/CCutts/Detecting_pairwise_correlations_in_spike_trains/blob/master/spike_time_tiling_coefficient.c
 *   See the original paper:
 *   https://www.ncbi.nlm.nih.gov/pubmed/25339742

 
* INPUTS 
    * N1v           | The number of spikes in electrode 1 (double) 
    * N2v           | The number of spikes in electrode 2 (double)
    * dtv           | The delay (in seconds) (double) 
    * Time          | 2 x 1 vector containing the start time and end time 
    *               | of the recording (seconds), so that Time(2) - Time(1) = length of 
    *               | recording
    * spike_times_1 | The spike times in electrode 1 (in seconds)  (vector)
    * spike_times_2 | the spikes times in electrode 2 (in seconds) (vector)

* OUTPUT

    * tileCoef | The tiling coefficient

 *========================================================*/

#include "mex.h"
#include <math.h>

/* The computational routine */
double run_P(int N1,int N2,double dt,double *spike_times_1,double *spike_times_2){
    
    int i;
    int j;
    int Nab;
    
    Nab=0;
    j=0;
    for(i=0;i<=(N1-1);i++){
        while(j<N2){
            if(fabs(spike_times_1[i]-spike_times_2[j])<=dt){
                Nab=Nab+1;
                break;
            }
            else if(spike_times_2[j]>spike_times_1[i]){
                break;
            }
            else{
                j=j+1;
            }
        }
    }
    return Nab;
}



double run_T(int N1v,double dtv,double startv, double endv, double *spike_times_1){
    
    double dt= dtv;
    double start=startv;
    double end=endv;
    int N1= N1v;
    double time_A;
    int i=0;
    double diff;
    
//maximum
    time_A=2*(double)N1*dt;
    
// if just one spike in train
    if(N1==1){
        
        if((spike_times_1[0]-start)<dt){
            time_A=time_A-start+spike_times_1[0]-dt;
        }
        else if((spike_times_1[0]+dt)>end){
            time_A=time_A-spike_times_1[0]-dt+end;
        }
        
    }
    
//if more than one spike in train
    else{
        
        
        while(i<(N1-1)){
            
            diff=spike_times_1[i+1]-spike_times_1[i];
            
            if(diff<2*dt){
                //subtract overlap
                time_A=time_A-2*dt+diff;
                
            }
            
            i++;
        }
        
        //check if spikes are within dt of the start and/or end, if so just need to subract
        //overlap of first and/or last spike as all within-train overlaps have been accounted for
        
        
        if((spike_times_1[0]-start)<dt){
            
            time_A=time_A-start+spike_times_1[0]-dt;
        }
        
        
        if((end-spike_times_1[N1-1])<dt){
            
            time_A=time_A-spike_times_1[N1-1]-dt+end;
        }
    }
    
    return time_A;
}


void run_sttc(int *N1v,int *N2v,double *dtv,double *Time,double *tileCoef,double *spike_times_1,double *spike_times_2)
{
//  actual code for the main function
    double TA;
    double TB;
    double PA;
    double PB;
    int N1 = *N1v;
    int N2 = *N2v;
    double dt = *dtv;
    double T;
    
    if(N1==0 || N2==0){
        *tileCoef=NAN;
    }
    else{
        T=Time[1]-Time[0];
        TA=run_T(N1,dt,Time[0],Time[1], spike_times_1);
        TA=TA/T;
        TB=run_T(N2,dt,Time[0],Time[1], spike_times_2);
        TB=TB/T;
        PA=run_P(N1,N2,dt, spike_times_1, spike_times_2);
        PA=PA/(double)N1;
        PB=run_P(N2,N1,dt, spike_times_2, spike_times_1);
        PB=PB/(double)N2;
        *tileCoef=0.5*(PA-TB)/(1-TB*PA)+0.5*(PB-TA)/(1-TA*PB);
    }
}

/* The gateway function */
void mexFunction( int nlhs, mxArray *plhs[],
        int nrhs, const mxArray *prhs[])
{
    int N1v;                /* input scalar */
    int N2v;                /* input scalar */
    double dtv;             /* input scalar */
    double *Time;           /* input scalar */
    double *spike_times_1;  /* 1xN input matrix */
    double *spike_times_2;  /* 1xN input matrix */
    
    double *tileCoef;        /* output scalar */
    
    /* get the value of the scalar input  */
    N1v = mxGetScalar(prhs[0]);
    N2v = mxGetScalar(prhs[1]);
    dtv = mxGetScalar(prhs[2]);
    
    /* create a pointer to the real data in the input matrix  */
#if MX_HAS_INTERLEAVED_COMPLEX
    Time = mxGetDoubles(prhs[3]);
    spike_times_1 = mxGetDoubles(prhs[4]);
    spike_times_2 = mxGetDoubles(prhs[5]);
#else
    Time = mxGetPr(prhs[3]);
    spike_times_1 = mxGetPr(prhs[4]);
    spike_times_2 = mxGetPr(prhs[5]);
#endif
    
    plhs[0] = mxCreateDoubleMatrix(1,1,mxREAL);
    
    /* get a pointer to the real data in the output matrix */
#if MX_HAS_INTERLEAVED_COMPLEX
    tileCoef = mxGetDoubles(plhs[0]);
#else
    tileCoef = mxGetPr(plhs[0]);
#endif
    
    /* call the computational routine */
    run_sttc(&N1v, &N2v, &dtv, Time, tileCoef, spike_times_1, spike_times_2);
}
