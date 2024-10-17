import numpy as np

def getFs(opsFpath): 
    
    ops = np.load(opsFpath, allow_pickle=True).item()
    fs = ops['fs']

    return fs