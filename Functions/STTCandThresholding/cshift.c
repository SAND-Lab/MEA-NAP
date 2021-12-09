#include "mex.h"
#include <stdio.h> 

/*Function to reverse arr[] from index start to end*/
void reverseArray(double arr[], int start, int end) 
{ 
    int temp; 
    while (start < end) { 
        temp = arr[start]; 
        arr[start] = arr[end]; 
        arr[end] = temp; 
        start++; 
        end--; 
    } 
} 

void leftRotate(double arr[], int d, int n) 
{ 
  
    if (d == 0) 
        return; 
    // in case the rotating factor is 
    // greater than array length 
    d = d % n; 
  
    reverseArray(arr, 0, d - 1); 
    reverseArray(arr, d, n - 1); 
    reverseArray(arr, 0, n - 1);
} 



void mexFunction(int nlhs, mxArray *plhs[],
        int nrhs, const mxArray *prhs[])
{
    int n;             /* input scalar */
    int d;             /* input scalar */
    double *arr;        /* 1xN input matrix */
    
    /* get the value of the scalar input  */
    n =  mxGetScalar(prhs[1]);
    d = mxGetScalar(prhs[2]);
    
    /* create a pointer to the real data in the input matrix  */
#if MX_HAS_INTERLEAVED_COMPLEX
    arr = mxGetDoubles(prhs[0]);
#else
    arr = mxGetPr(prhs[0]);
#endif
    leftRotate(arr, d, n);
} 
