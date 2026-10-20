import numpy as np

def getXYloc(statFpath):

    stat = np.load(statFpath, allow_pickle=True)
    x_loc = [stat[x]['med'][0] for x in np.arange(0, len(stat))]
    y_loc = [stat[x]['med'][1] for x in np.arange(0, len(stat))]
    
    XYloc = np.stack([x_loc, y_loc])

    return XYloc

