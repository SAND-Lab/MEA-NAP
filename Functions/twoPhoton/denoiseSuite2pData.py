import pdb

import numpy as np
import numpy.fft as fft
import time

import os
import json

from matplotlib import pyplot as plt
from scipy.signal import find_peaks, savgol_filter
import pandas as pd
from scipy import signal
from pybaselines.polynomial import imodpoly, modpoly
from scipy import integrate

from json import JSONDecodeError

from oasis.functions import deconvolve
from oasis.plotting import simpleaxis
from tqdm.auto import tqdm
import glob

def get_burst_data(prop):
    '''
    Construct a list of dictionary to store burst info:
    start, end, duration, and peak of burst

    Return:
        a dictionary of burst info

    '''
    ret = []
    for peak in prop:
        ret.append({
            "start": peak[2],
            "end": peak[3],
            "duration": peak[4],
            "peak": peak[1],
        })

    return ret


def get_burst_data_from_oasis(trace, peaks, properties):
    x = trace
    ret = []
    peakNum = len(peaks)
    for i in range(peakNum):
        ret.append({
            "start": properties["left_ips"][i],
            "end": properties["right_ips"][i],
            "duration": properties["right_ips"][i] - properties["left_ips"][i],
            "peak": x[peaks[i]],
        })
    return ret

def apply_convolution(sig, window):
    conv = np.repeat([0., 1., 0.], window)
    filtered = signal.convolve(sig, conv, mode='same') / window
    return filtered


def denoise_intensity(df, method, params=None):
    if method == "rolling":
        return df.rolling(100).mean()
        # rolling average using gaussian
    #         return df.rolling(100, win_type='gaussian').mean(std=df.std().mean())

    if method == "convolve":
        # convolve
        return df.apply(lambda srs: apply_convolution(srs, 100))

    #     if method=="filter":
    #         # Savitzky–Golay filter
    #         return df.apply(lambda srs: signal.savgol_filter(srs.values, 151, 3))

    if method == "filter":
        # Savitzky–Golay filter:
        # https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.savgol_filter.html
        return df.apply(lambda srs: signal.savgol_filter(srs.values, 1665, 3))

    if method == "poly":
        # The improved modofied polynomial (IModPoly) baseline algorithm to filter:
        # https://pybaselines.readthedocs.io/en/latest/api/pybaselines/polynomial/index.html
        return df.apply(lambda srs: imodpoly(srs, poly_order=3, num_std=0.7)[0])

def denoise_intensity_np(intensity, method):

    if method == 'filter':
        denoised_intensity = signal.savgol_filter(intensity, 1665, 3)
    elif method == 'poly':
        denoised_intensity, _ = imodpoly(intensity, poly_order=3, num_std=0.7)

    return denoised_intensity

def get_final_intensity(cell_id, raw_intensity, methods, output_dir=None, show=False, savefile=True):
    # create dataframe
    #     df = pd.DataFrame({'intensity': raw_intensity})
    df = pd.DataFrame({'intensity': list(raw_intensity.values())})

    method1, method2 = methods[0], methods[1]

    # denoise
    base_df1 = denoise_intensity(df, method=method1)
    smooth1 = df.sub(base_df1).fillna(0)

    # denoising twice
    base_df2 = denoise_intensity(smooth1, method=method2)
    smooth2 = smooth1.sub(base_df2).fillna(0)

    # find the final base
    base_df3 = denoise_intensity(smooth2, method="poly")

    # plot the intensity
    plot_intensity(cell_id, output_dir, df, [method1, method2], base_df1, smooth1, base_df2, smooth2, base_df3,
                   show=show, savefile=savefile)

    # calculate relative intensity using smooth2 and base3
    mean_base = np.mean(np.array(base_df3["intensity"].tolist()))
    if mean_base < 0:
        mean_base = -mean_base

    rel_intensity = (np.array(smooth2["intensity"].tolist()) - np.array(base_df3["intensity"].tolist())) / mean_base

    return rel_intensity


def get_final_intensity_combine(cell_id, raw_intensity, methods, output_dir=None, show=False, savefile=True):
    # create dataframe
    #     df = pd.DataFrame({'intensity': raw_intensity})
    df = pd.DataFrame({'intensity': list(raw_intensity.values())})

    method1, method2 = methods[0], methods[1]

    # denoise
    base_df1 = denoise_intensity(df, method=method1)
    smooth1 = df.sub(base_df1).fillna(0)

    # denoising twice
    base_df2 = denoise_intensity(smooth1, method=method2)
    smooth2 = smooth1.sub(base_df2).fillna(0)

    # find the final base
    base_df3 = denoise_intensity(df, method="poly")

    # plot the intensity
    #     plot_intensity(cell_id, output_dir, df, [method1, method2], base_df1, smooth1, base_df2, smooth2, base_df3,
    #                    show=show, savefile=savefile)

    # calculate relative intensity using smooth2 and base3
    mean_base = np.mean(np.array(base_df3["intensity"].tolist()))
    if mean_base < 0:
        mean_base = -mean_base

    rel_intensity = (np.array(smooth2["intensity"].tolist()) - np.array(base_df3["intensity"].tolist())) / mean_base

    return rel_intensity, df, base_df1, smooth1, base_df2, smooth2, base_df3


def plot_intensity(cell_id, output_dir, df, methods, base1, smooth1, base2=None, smooth2=None, base3=None,
                   show=False, savefile=True):
    # plot the intensity of cell

    method1 = methods[0]
    if len(methods) == 2:
        method2 = methods[1]
    else:
        method2 = None

    fig = plt.figure(figsize=(20, 4))
    plt.plot(df["intensity"], label="raw intensity")
    plt.plot(base1["intensity"], label="base1")
    plt.plot(smooth1["intensity"], label="smooth1")

    title = f"intensity plot of cell {cell_id} using {method1}"

    if method2 is not None:
        plt.plot(base2["intensity"], label="base2")
        plt.plot(smooth2["intensity"], label="smooth2")
        title = title + ', ' + method2

    if base3 is not None:
        plt.plot(base3["intensity"], label="base3")

    plt.title(title)
    plt.xlabel("time (image frames)")
    plt.ylabel("flourescent intensity (ADU)")
    plt.legend()

    if savefile:
        filename = os.path.join(output_dir, f"cell_{cell_id} intensity plot.jpg")
        fig.savefig(filename)

    if not show:  # don't display the image
        plt.close(fig)


def plot_polygons(data, ax=None, **kwargs):
    if ax is None:
        ax = plt.gca()

    ax.plot([1, 2, 3, 4])


#     artists = [ax.fill(x, y, **kwargs) for x, y in data]
#     return artists

def plot_verts(data, ax=None, **kwargs):
    if ax is None:
        ax = plt.gca()

    artists = [ax.scatter(x, y, **kwargs) for x, y in data]
    return artists


def find_bursts(data, height=0.4, width=[2, 50], plot=False):
    '''
    Find bursts given the intensity time-series data
    '''

    # sliding window max
    peaks = []
    properties = {}

    trend = apply_convolution(data, 10)

    # use sliding window to find potential peaks
    win_size = 20
    diff = 4  # min diff between peak and trough in trend

    p = []  # potential peaks
    left = 0
    right = win_size
    while right < 1600:
        mean_y = sum(trend[left:right]) / win_size
        peak = max(trend[left + 1:right])
        peak_idx = trend.tolist().index(peak, left, right)
        trough = min(y for y in trend[left:peak_idx])
        trough_idx = trend.tolist().index(trough, left, peak_idx)

        if peak - trough >= diff:
            p.append(peak_idx)

        left += 1
        right += 1

        # get real peaks from potential peaks
    real_p = []
    i = 0
    batch = []  # a batch contains neighboring peak index
    while i < len(p) - 1:
        if p[i + 1] - p[i] < 10:
            batch.append(p[i])
        else:
            # get the peak in the batch
            if len(batch) != 0:
                rp = max(data[idx] for idx in batch)
                peak_idx = data.tolist().index(rp, batch[0], batch[-1] + 1)
                real_p.append([peak_idx, rp])
                batch = []
        i += 1

        # get the burst properties: start, end, duration
    base = 0
    prop = []
    for each in real_p:
        px, py = each[0], each[1]
        s = px - 1
        t = px + 1
        while data[s] > base:
            s -= 1
        while data[t] > base:
            t += 1
        prop.append([px, py, s, t, t - s])

    if plot:
        plt.figure(figsize=(20, 4))
        plt.plot(data, label='intensity')
        plt.plot(trend, label="trend")
        py = [trend[i] for i in p]
        plt.plot(p, py, "rx", label="pp")

        if len(real_p) != 0:
            rp = np.array(real_p)
            plt.plot(rp[:, 0], rp[:, 1], "k*", label="reak peak")

        plt.title("rel intensity")
        plt.legend()
        plt.show()

    return prop


def plot_trace(raw_trace, spike_train, groundtruth=False):
    plt.figure(figsize=(20, 8))
    plt.subplot(211)
    plt.plot(b + c, lw=2, label='denoised')
    if groundtruth:
        plt.plot(true_b + true_c, c='r', label='truth', zorder=-11)
    plt.plot(raw_trace, label='raw trace', zorder=-12, c='y')
    plt.legend(ncol=3, frameon=False, loc=(.02, .85))
    simpleaxis(plt.gca())

    #### plot of deconvolved spike train
    #     plt.subplot(212)
    #     plt.plot(spike_train, lw=2, label='deconvolved', c='g')
    #     if groundtruth:
    #         for k in np.where(true_s)[0]:
    #             plt.plot([k,k],[-.1,1], c='r', zorder=-11, clip_on=False)
    #     plt.ylim(0,1.3)

    #     plt.legend(ncol=3, frameon=False, loc=(.02,.85))
    plt.legend()
    simpleaxis(plt.gca())
    # print("Correlation of deconvolved activity  with ground truth ('spikes') : %.4f" % np.corrcoef(s,true_s)[0,1])
    # print("Correlation of denoised fluorescence with ground truth ('calcium'): %.4f" % np.corrcoef(c,true_c)[0,1])


def plot_burst_events(x, peaks, properties, save_file=False):
    plt.figure(figsize=(20,4))
    plt.plot(x, c='g', label="trace")
    plt.plot(peaks, x[peaks], "x")
    plt.vlines(x=peaks, ymin=x[peaks] - properties["prominences"],
               ymax = x[peaks], color = "C1")
    plt.hlines(
                y=properties["width_heights"],
#                 y=x[peaks] - properties["prominences"],
               xmin=properties["left_ips"],
               xmax=properties["right_ips"], color = "C1")
    plt.legend()
    plt.show()


def save_burst_events_to_file(cell_id, image_output_path,
                              raw_trace, spike_train, denoised_trace, peaks, properties, spike_threshold,
                              show=False, savefile=False,
                              groundtruth=False):
    fig = plt.figure(figsize=(20, 12))
    plt.suptitle(f"burst analysis of cell {cell_id}")

    #### plot of denoised trace using OASIS deconvolve ####
    plt.subplot(311)
    plt.plot(raw_trace, label='filtered once trace', zorder=-12, c='y')
    plt.plot(denoised_trace, lw=2, label='denoised trace', c='tab:blue')
    plt.ylabel("relative intensity")
    if groundtruth:
        plt.plot(true_b + true_c, c='r', label='truth', zorder=-11)
    plt.legend()

    #### plot of burst events ####
    plt.subplot(312)
    x = denoised_trace
    plt.plot(x, c='tab:blue', label="denoised trace")
    plt.plot(peaks, x[peaks], "x", c='r', label="calcium transients")
    plt.ylabel("relative intensity")
    plt.vlines(x=peaks, ymin=x[peaks] - properties["prominences"],
               ymax=x[peaks], color="r")
    plt.hlines(
        y=properties["width_heights"],
        #                 y=x[peaks] - properties["prominences"],
        xmin=properties["left_ips"],
        xmax=properties["right_ips"], color="r")
    plt.legend()

    #### plot of spike train ####
    plt.subplot(313)

    # Label unnormalised spikes with values larger than spike_threshold
    spike_indices = np.where(spike_train > spike_threshold)[0]
    plt.vlines(x=spike_indices, ymin=-0.05 * np.max(spike_train), ymax=np.max(spike_train), color='#FFC0CB',
               label='selected spike', alpha=1)
    plt.legend()
    # plot unnormalised spike train: plotted later to make it appear on top of the selected ones
    plt.plot(spike_train, label='inferred spikes', c='g')
    plt.xlabel("time (image frames)")
    plt.ylabel("inferred spike")
    plt.legend()

    #### plot of normalized spike_train & selected spikes ####
    #     normalized_spike_train = spike_train / np.max(spike_train)  # Normalize spike_train
    #     # Label normalised spikes with values larger than spike_threshold
    #     spike_indices = np.where(normalized_spike_train > spike_threshold)[0]
    #     plt.vlines(x=spike_indices, ymin=-0.05, ymax=1, color='#FFC0CB', label='selected spike', alpha=1)
    #     plt.legend()
    #     # plot normalised spike train: plotted later to make it appear on top of the selected ones
    #     plt.plot(normalized_spike_train, label='normalised spikes', c='g')
    #     plt.xlabel("time (image frames)")
    #     plt.ylabel("inferred spike")
    #     plt.legend()

    file_name = f"cell_{cell_id} bursts plot.jpg"
    if savefile:
        fig.savefig(os.path.join(image_output_path, file_name))
        data_file_name = os.path.join(image_output_path, file_name.replace('.jpg', '.json'))
        groundtruth_data = []
        if groundtruth:
            groundtruth_data = true_b + true_c
        save_data = {
            "cell_id": cell_id,
            "raw_trace": raw_trace.tolist(),
            "denoised_trace": denoised_trace.tolist(),
            "groundtruth": groundtruth_data,
            "peaks": peaks.tolist(),
            "peak_vline_ymin": (x[peaks] - properties["prominences"]).tolist(),
            "peak_vline_ymax": x[peaks].tolist(),
            "peak_hline": properties["width_heights"].tolist(),
            "peak_hline_xmin": properties["left_ips"].tolist(),
            "peak_hline_xmax": properties["right_ips"].tolist(),
        }
        with open(data_file_name, 'w') as fd:
            json.dump(save_data, fd)
    if not show:
        plt.close(fig)


# the get_final_intensity_v2 after modifying to use subtraction of negative amplitude noise + preservation + delF/F filtering for denoising on 20240227
def get_final_intensity_v2_subtractionOn20240227(cell_id, raw_intensity, methods, output_dir=None, show=False,
                                                 savefile=True):
    # create dataframe
    #     df = pd.DataFrame({'intensity': raw_intensity})

    if type(raw_intensity) is np.ndarray:
        df = pd.DataFrame({'intensity': list(raw_intensity)})
    else:
        df = pd.DataFrame({'intensity': list(raw_intensity.values())})

    method1, method2 = methods[0], methods[1]
    #     methods[0] is poly, methods[1] is filter

    # Denoising using poly
    base_df1 = denoise_intensity(df, method=method1)
    smooth1 = df.sub(base_df1).fillna(0)

    # print('Checkpoint A: %.2f' % np.sum(base_df1))

    # Calculate mean_base
    mean_base = np.mean(np.abs(base_df1["intensity"].tolist()))
    #     if mean_base<0:
    #         mean_base = -mean_base

    # Calculate F_denoised
    F_denoised = np.array(base_df1["intensity"].tolist())
    condition1 = (np.array(df["intensity"].tolist()) - np.array(base_df1["intensity"].tolist()) <= 0)
    condition2 = (np.array(df["intensity"].tolist())
                  - (np.array(base_df1["intensity"].tolist())
                     + 1.3 * abs(np.min(np.array(df["intensity"].tolist()) - np.array(base_df1["intensity"].tolist()))))
                  > 0)
    if condition1.any():
        F_denoised = np.where(condition1, np.array(base_df1["intensity"].tolist()), F_denoised)
    # calculate F raw - (base1 + absolute value of minimal fluorescence)
    # = F raw - noise band = true F raw stands out of the noise band (noise band = +- 2*minimal)
    if condition2.any():
        F_denoised = np.where(condition2, np.array(df["intensity"].tolist()), F_denoised)
    else:
        F_denoised = np.where(~condition2, np.array(base_df1["intensity"].tolist()), F_denoised)

    # print('Checkpoint -1: %.2f' % np.sum(F_denoised))

    # Preserve df["intensity"] values 30 frames before and after where F_denoised does not equal to base_df1["intensity"].tolist()
    # 3 combinations: 1abs, 10, 26; 1.3abs, 20, 41; 1.5abs, 30, 51;  2abs, 30, 76
    preserved_intensity = base_df1["intensity"].tolist().copy()
    for i, (denoised, base) in enumerate(zip(F_denoised, base_df1["intensity"].tolist())):
        if denoised != base:
            for j in range(max(0, i - 20), min(len(df), i + 41)):
                preserved_intensity[j] = df["intensity"].tolist()[j]
                # code optimisation might be possible? Make F_denoised=preserved_intensity
                # or Use preserved_intensity directly as: deltaF = np.array(preserved_intensity)-np.array(base_df1["intensity"].tolist())

    # print('Checkpoint 0: %.2f' % np.sum(preserved_intensity))

    # Update F_denoised with preserved intensity
    F_denoised = np.where(np.array(preserved_intensity) != np.array(F_denoised), np.array(preserved_intensity),
                          F_denoised)

    # print('Checkpoint 1: %.2f' % np.sum(F_denoised))

    # rel_intensity = (np.array(smooth1["intensity"].tolist())-np.array(base_df2["intensity"].tolist()))/mean_base

    # calculate delF/F = (F_denoised - base1)/mean base or delF/F = (F_denoised - base1)/base1
    deltaF = F_denoised - np.array(base_df1["intensity"].tolist())
    #     rel_intensity = deltaF/mean_base
    rel_intensity = deltaF / np.array(base_df1["intensity"].tolist())

    # print('Checkpoint 2: %.2f' % np.sum(deltaF))
    # print('Checkpoint 3: %.2f' % np.sum(rel_intensity))

    # Filter relative intensity (dF/F), with threshold 0.1 or 0.05
    rel_intensity_filtered = rel_intensity
    condition1 = (rel_intensity < 0.05)
    if condition1.any():
        rel_intensity_filtered = np.where(condition1, 0, rel_intensity_filtered)

    # print('Checkpoint 4: %.2f' % np.sum(rel_intensity_filtered))

    # Preserve rel_intensity["intensity"] values 50 frames before and after where rel_intensity_filtered does not equal to base=0
    # 2 combinations: 0.1, 30, 81; 0.05, 20, 51;
    preserved_rel_intensity = np.zeros_like(rel_intensity)
    for i, (filtered, base) in enumerate(zip(rel_intensity_filtered, np.zeros_like(rel_intensity))):
        if filtered != base:
            for j in range(max(0, i - 20), min(len(df), i + 51)):
                preserved_rel_intensity[j] = rel_intensity[j]
                # code optimisation might be possible? Make rel_intensity_filtered=preserved_rel_intensity
                # or Use preserved_rel_intensity directly as: return deltaF, preserved_rel_intensity

    # print('Checkpoint 5: %.2f' % np.sum(preserved_rel_intensity))

    # Update rel_intensity_filtered with preserved relative intensity
    rel_intensity_filtered = np.where(np.array(preserved_rel_intensity) != np.array(rel_intensity_filtered),
                                      np.array(preserved_rel_intensity), rel_intensity_filtered)

    return deltaF, rel_intensity_filtered


def get_denoised_intensity(raw_intensity):

    base_df1 = denoise_intensity_np(raw_intensity, method='poly')
    F_denoised = base_df1

    # print('Checkpoint A: %.2f' % np.sum(base_df1))

    preserved_intensity = base_df1.copy()

    condition1 = (raw_intensity - base_df1) <= 0
    condition2 = (raw_intensity - (base_df1 + 1.3 * abs(np.min(raw_intensity - base_df1))) > 0)

    if np.any(condition1):
        F_denoised = np.where(condition1, base_df1, F_denoised)
    if condition2.any():
        F_denoised = np.where(condition2, raw_intensity, F_denoised)
    else:
        F_denoised = np.where(~condition2, base_df1, F_denoised)

    # print('Checkpoint -1: %.2f' % np.sum(F_denoised))

    mismatch_indices = np.where(F_denoised != base_df1)[0]
    for m_idx in mismatch_indices:
        start_idx = np.max([0, m_idx - 20])
        end_idx = np.min([len(raw_intensity), m_idx + 41])
        preserved_intensity[start_idx:end_idx] = raw_intensity[start_idx:end_idx]

    # print('Checkpoint 0: %.2f' % np.sum(preserved_intensity))

    # Update F_denoised with preserved intensity
    F_denoised = np.where(np.array(preserved_intensity) != np.array(F_denoised),
                          np.array(preserved_intensity), F_denoised)

    # print('Checkpoint 1: %.2f' % np.sum(F_denoised))

    # calculate delF/F = (F_denoised - base1)/mean base or delF/F = (F_denoised - base1)/base1
    deltaF = F_denoised - base_df1
    #     rel_intensity = deltaF/mean_base
    rel_intensity = deltaF / base_df1

    # print('Checkpoint 2: %.2f' % np.sum(deltaF))
    # print('Checkpoint 3: %.2f' % np.sum(rel_intensity))

    # Filter relative intensity (dF/F), with threshold 0.1 or 0.05
    rel_intensity_filtered = rel_intensity
    condition1 = (rel_intensity < 0.05)
    if condition1.any():
        rel_intensity_filtered = np.where(condition1, 0, rel_intensity_filtered)

    # print('Checkpoint 4: %.2f' % np.sum(rel_intensity_filtered))
    # Preserve rel_intensity["intensity"] values 50 frames before and after where rel_intensity_filtered does not equal to base=0
    # 2 combinations: 0.1, 30, 81; 0.05, 20, 51;

    preserved_rel_intensity = np.zeros_like(rel_intensity)
    mismatch_indices = np.where(rel_intensity_filtered != preserved_rel_intensity)[0]
    for m_idx in mismatch_indices:
        start_idx = np.max([0, m_idx - 20])
        end_idx = np.min([len(raw_intensity), m_idx + 51])
        preserved_rel_intensity[start_idx:end_idx] = rel_intensity[start_idx:end_idx]

    # print('Checkpoint 5: %.2f' % np.sum(preserved_rel_intensity))

    # Update rel_intensity_filtered with preserved relative intensity
    rel_intensity_filtered = np.where(preserved_rel_intensity != rel_intensity_filtered,
                                      preserved_rel_intensity, rel_intensity_filtered)


    return deltaF, rel_intensity_filtered

def plot_intensity_in_combined_plot(cell_id, output_dir, df, methods, base1, deltaF, smooth1, base2=None, smooth2=None,
                                    base3=None,
                                    show=False, savefile=False):
    # plot the intensity of cell

    method1 = methods[0]
    if len(methods) == 2:
        method2 = methods[1]
    else:
        method2 = None

    plt.plot(df["intensity"], label="raw intensity", c='k')
    plt.plot(base1["intensity"], label="base1", c='tab:orange')
    plt.plot(deltaF, label="filtered once", c='y')

    #     if method2 is not None:
    #         plt.plot(base2["intensity"], label="base2")
    #         plt.plot(smooth2["intensity"], label="smooth2")

    #     if base3 is not None:
    #         plt.plot(base3["intensity"], label="base3")

    plt.ylabel("flourescent intensity")
    plt.legend()


def combine_intensity_burst_plot_save(cell_id, raw_intensity, methods,
                                      image_output_path, deltaF, raw_trace, spike_train, denoised_trace, peaks,
                                      properties,
                                      spike_threshold,
                                      output_dir=None, show=False, savefile=True, groundtruth=False):
    fig = plt.figure(figsize=(20, 10))
    plt.suptitle(f"burst detection and spike inference of cell {cell_id}")

    #### plot of raw fluorescent intensity and relative intensity using baseline filers ####
    plt.subplot(411)

    # create dataframe
    df = pd.DataFrame({'intensity': list(raw_intensity.values())})

    # methods[0] is poly, methods[1] is filter
    method1, method2 = methods[0], methods[1]
    # filter noise once using poly
    base_df1 = denoise_intensity(df, method=method1)
    smooth1 = df.sub(base_df1).fillna(0)
    # filter twice using filter method
    base_df2 = denoise_intensity(smooth1, method=method2)
    smooth2 = smooth1.sub(base_df2).fillna(0)
    # find the final base
    base_df3 = denoise_intensity(smooth2, method="poly")

    # plot the intensity
    plot_intensity_in_combined_plot(cell_id, output_dir, df, [method1, method2], base_df1, deltaF, smooth1, base_df2,
                                    smooth2, base_df3,
                                    show=False, savefile=False)
    plt.legend()

    #### plot of denoised trace using OASIS deconvolve ####
    plt.subplot(412)
    plt.plot(raw_trace, label='filtered once trace', zorder=-12, c='y')
    plt.plot(denoised_trace, lw=2, label='denoised trace', c='tab:blue')
    plt.ylabel("relative intensity")
    if groundtruth:
        plt.plot(true_b + true_c, c='r', label='truth', zorder=-11)
    plt.legend()

    #### plot of burst events ####
    plt.subplot(413)
    x = denoised_trace
    plt.plot(x, c='tab:blue', label="denoised trace")
    plt.plot(peaks, x[peaks], "x", c='r', label="calcium transients")
    plt.ylabel("relative intensity")
    plt.vlines(x=peaks, ymin=x[peaks] - properties["prominences"],
               ymax=x[peaks], color="r")
    plt.hlines(
        y=properties["width_heights"],
        #                 y=x[peaks] - properties["prominences"],
        xmin=properties["left_ips"],
        xmax=properties["right_ips"], color="r")
    plt.legend()

    #### plot of spike train ####
    plt.subplot(414)

    # Label unnormalised spikes with values larger than spike_threshold
    spike_indices = np.where(spike_train > spike_threshold)[0]
    plt.vlines(x=spike_indices, ymin=-0.05 * np.max(spike_train), ymax=np.max(spike_train), color='#FFC0CB',
               label='selected spike', alpha=1)
    plt.legend()
    # plot unnormalised spike train: plotted later to make it appear on top of the selected ones
    plt.plot(spike_train, label='inferred spikes', c='g')
    plt.xlabel("time (image frames)")
    plt.ylabel("inferred spike")
    plt.legend()

    #### plot of normalized spike_train & selected spikes ####
    #     normalized_spike_train = spike_train / np.max(spike_train)  # Normalize spike_train
    #     # Label normalised spikes with values larger than spike_threshold
    #     spike_indices = np.where(normalized_spike_train > spike_threshold)[0]
    #     plt.vlines(x=spike_indices, ymin=-0.05, ymax=1, color='#FFC0CB', label='selected spike', alpha=1)
    #     plt.legend()
    #     # plot normalised spike train: plotted later to make it appear on top of the selected ones
    #     plt.plot(normalized_spike_train, label='normalised spikes', c='g')
    #     plt.xlabel("time (image frames)")
    #     plt.ylabel("inferred spike")
    #     plt.legend()

    file_name = f"cell_{cell_id} combined plot.jpg"
    if savefile:
        fig.savefig(os.path.join(image_output_path, file_name))
        data_file_name = os.path.join(image_output_path, file_name.replace('.jpg', '.json'))
        groundtruth_data = []
        if groundtruth:
            groundtruth_data = true_b + true_c
        save_data = {
            "cell_id": cell_id,
            "raw_trace": raw_trace.tolist(),
            "denoised_trace": denoised_trace.tolist(),
            "groundtruth": groundtruth_data,
            "peaks": peaks.tolist(),
            "peak_vline_ymin": (x[peaks] - properties["prominences"]).tolist(),
            "peak_vline_ymax": x[peaks].tolist(),
            "peak_hline": properties["width_heights"].tolist(),
            "peak_hline_xmin": properties["left_ips"].tolist(),
            "peak_hline_xmax": properties["right_ips"].tolist(),
        }
        with open(data_file_name, 'w') as fd:
            json.dump(save_data, fd)
    if not show:
        plt.close(fig)

def denoise_suite2p_data(F, output_dir, make_plots=False, image_output_dir=None, denoise_methods=["rolling", "convolve", "filter", "poly"]):
    """

    Parameters
    ----------
    :param F:
    :param output_dir:
    :param make_plots:
    :param denoise_methods:
    :return:
    """


    """
    # Create a CSV file to store num_of_bursts for each cell
    num_of_bursts_file = os.path.join(output_dir, "num_of_bursts.csv")
    num_of_bursts_data = []
    # Create a CSV file to store peak_areas for each peak of each cell
    peak_areas_file = os.path.join(output_dir, "peak_areas.csv")
    # Create a dictionary to store peak areas for each cell
    peak_areas_dict = {}
    # Create a CSV file to store peak_durations (in frames) for each peak of each cell
    peak_durations_file = os.path.join(output_dir, "peak_durations.csv")
    # Create a dictionary to store peak durations for each cell
    peak_durations_dict = {}
    """

    if make_plots:
        image_output_path = os.path.join(image_output_dir, file[:-3])
        os.makedirs(image_output_path, exist_ok=True)


    methods = ["poly", "filter"]

    num_cells, num_time_points = np.shape(F)

    F_denoised = np.zeros(np.shape(F)) + np.nan
    peak_start_frames = np.empty(num_cells, object)

    for cell_id in tqdm(np.arange(num_cells)):

        raw_intensity = F[cell_id, :]
        """
        deltaF, rel_intensity = get_final_intensity_v2_subtractionOn20240227(cell_id, raw_intensity,
                                                                             methods=["poly", "filter"],
                                                                             show=False,
                                                                             savefile=True)
        signal_array = np.array(rel_intensity)     
        c, spike_train, b, g, lam = deconvolve(signal_array)                                                                
        """

        deltaF, rel_intensity = get_denoised_intensity(raw_intensity)
        # oasis
        c, spike_train, b, g, lam = deconvolve(rel_intensity)
        #             plot_trace(rel_intensity, spike_train, False)

        denoised_trace = b + c

        peaks, properties = signal.find_peaks(denoised_trace, height=0.0015, width=17, distance=50,
                                              prominence=0.0015, rel_height=0.95, wlen=180)
        #         peaks, properties = signal.find_peaks(denoised_trace, height=0.022, width=6.6, distance=40,
        #                                                   prominence=0.022, rel_height=0.83, wlen=160)
        #           peaks, properties = signal.find_peaks(denoised_trace, height=0.025, width=6.6, distance=48,
        #                                                 prominence=0.035, rel_height=0.5)

        # plot the burst detection figure
        #         spike_threshold = 0.18 #normalised spike threshold
        spike_threshold = 0.015  # unnormalised spike threshold

        cell_peak_start_frames = np.array([int(properties["left_ips"][x]) for x in np.arange(len(peaks))])
        peak_start_frames[cell_id] = cell_peak_start_frames
        F_denoised[cell_id, :] = denoised_trace


        """
        save_burst_events_to_file(cell_id, image_output_path,
                                  rel_intensity, spike_train, denoised_trace, peaks, properties, spike_threshold)
        combine_intensity_burst_plot_save(cell_id, raw_intensity, methods,
                                          image_output_path, deltaF, rel_intensity, spike_train, denoised_trace, peaks,
                                          properties,
                                          spike_threshold)
        """

        """
        if len(peaks) != 0:  # current cell has burst events
            # Calculate the area under the curve for each peak
            peak_areas = []
            peak_durations = []
            burst_data = get_burst_data_from_oasis(denoised_trace, peaks, properties)

            for peak_idx, peak in enumerate(peaks):
                peak_start = int(properties["left_ips"][peak_idx])
                peak_end = int(properties["right_ips"][peak_idx])
                area = integrate.trapz(denoised_trace[peak_start:peak_end])
                duration = peak_end - peak_start  # Duration in data points

                # TODO: also output peak_start time, to be interpreted as "spike times"
                # for STTC

                peak_areas.append(area)
                peak_durations.append(duration)
                burst_data[peak_idx]["area"] = area

                cell_data[cell_id] = {
                    "num_of_bursts": len(burst_data),
                    "bursts": burst_data,
                }

                # Store num_of_bursts in the num_of_bursts_data list
                num_of_bursts_data.append({"file": file, "cell_id": cell_id, "num_of_bursts": len(burst_data)})
                # Store the peak_areas data for each cell in the peak_areas_dict
                peak_areas_dict[cell_id] = peak_areas
                # Store the peak_durations data for each cell in the peak_durations_dict
                peak_durations_dict[cell_id] = peak_durations

            # Inside the loop, create and save a separate JSON file for each input file
        burst_out = [{
            "methods": methods,
            "cells": cell_data
        }]

        out = file[:-5] + "_bursts_mask.json"
        output_path = os.path.join(output_dir, out)

        with open(output_path, "w") as f:
            json.dump(burst_out, f)

        # Save num_of_bursts data to a CSV file
        # Create a DataFrame from the num_of_bursts_data list
        num_of_bursts_df = []
        num_of_bursts_df = pd.DataFrame(num_of_bursts_data)
        # Drop duplicates to keep only one entry per cell
        num_of_bursts_df = num_of_bursts_df.drop_duplicates(subset=["file", "cell_id"])
        # Save num_of_bursts data to a CSV file
        num_of_bursts_file = os.path.join(output_dir, file[:-5] + "_num_of_bursts.csv")
        num_of_bursts_df.to_csv(num_of_bursts_file, index=False)

        # Save all peak_areas data to a single CSV file
        # Create a DataFrame from the peak_areas_dict
        peak_areas_df = pd.DataFrame.from_dict(peak_areas_dict, orient='index').T
        # Save peak_areas data to a CSV file
        peak_areas_file = os.path.join(output_dir, file[:-5] + "_peak_areas.csv")
        peak_areas_df.to_csv(peak_areas_file, index=True)

        # Save all peak_durations data to a single CSV file
        # Create a DataFrame from the peak_durations_dict
        peak_durations_df = pd.DataFrame.from_dict(peak_durations_dict, orient='index').T
        # Save peak_durations data to a CSV file
        peak_durations_file = os.path.join(output_dir, file[:-5] + "_peak_durations.csv")
        peak_durations_df.to_csv(peak_durations_file, index=True)

        del num_of_bursts_df, num_of_bursts_data, peak_areas_dict, peak_durations_dict
        """


    # Make peak_start_frames_matrix (easier to read into matlab)
    max_num_peaks = np.max(np.array([len(x) for x in peak_start_frames]))
    peak_start_frames_matrix = np.zeros((num_cells, max_num_peaks)) + np.nan
    for cell_id in np.arange(num_cells):
        peak_start_frames_matrix[cell_id, 0:len(peak_start_frames[cell_id])] = peak_start_frames[cell_id]


    return F_denoised, peak_start_frames_matrix


def get_suite2p_fs(ops_fpath):

    ops = np.load(ops_fpath, allow_pickle=True).item()
    fs = ops['fs']

    return fs


def do_suite2p_processing(suite2p_folder, resample_Hz=None, overwrite_existing=False):

    F_denoised_savepath = os.path.join(suite2p_folder, 'Fdenoised.npy')
    peak_start_frames_savepath = os.path.join(suite2p_folder, 'peakStartFrames.npy')
    time_points_savepath = os.path.join(suite2p_folder, 'timePoints.npy')

    if (not os.path.exists(F_denoised_savepath)) or overwrite_existing:

        F_fpath = os.path.join(suite2p_folder, 'F.npy')
        F = np.load(F_fpath)  # F is cell by time
        # F = F[0:20, :]  # temp : take first few cells

        ops_fpath = os.path.join(suite2p_folder, 'ops.npy')
        fs = get_suite2p_fs(ops_fpath)

        time_points = fs * np.arange(np.shape(F)[1])

        F_denoised, peak_start_frames = denoise_suite2p_data(F, suite2p_folder, make_plots=False, denoise_methods=["rolling", "convolve", "filter", "poly"])

        np.save(F_denoised_savepath, F_denoised)
        np.save(time_points_savepath, time_points)
        np.save(peak_start_frames_savepath, peak_start_frames)


def main():
    suite2p_folder = '/home/timothysit/testMultiSuite2pData/recordingB'

    do_suite2p_processing(suite2p_folder, resample_Hz=None, overwrite_existing=True)


if __name__ == '__main__':
    main()