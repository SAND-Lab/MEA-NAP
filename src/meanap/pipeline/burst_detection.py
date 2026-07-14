import numpy as np
from scipy.signal import find_peaks, savgol_filter


def get_isin_threshold(spike_times: np.ndarray, n: int = 10) -> float:
    """Calculate the automatic ISIn threshold using Bakkum's method.
    
    spike_times: 1D array of spike times in seconds.
    n: The number of spikes to consider for ISI_N.
    Returns the threshold in seconds.
    """
    if len(spike_times) <= n:
        return 0.1

    # ISI_N = T[i] - T[i - (N-1)]
    # In MATLAB: SpikeTimes(FRnum:end) - SpikeTimes(1:end-(FRnum-1))
    isin = spike_times[n-1:] - spike_times[:-(n-1)]
    
    if len(isin) == 0:
        return 0.1

    # Steps in ms: 10^(-5) to 10^(1.5)
    steps = 10 ** np.arange(-5, 1.55, 0.05)
    
    # histogram expects data in ms
    isin_ms = isin * 1000.0
    
    counts, _ = np.histogram(isin_ms, bins=steps)
    if counts.sum() == 0:
        return 0.1
        
    curve = counts / counts.sum()
    
    # Smooth the curve using savgol filter (similar to fLOESS with small span)
    # 8 samples window
    window_length = 9 if len(curve) >= 9 else (len(curve) | 1)
    if window_length > 3:
        curve = savgol_filter(curve, window_length, 1)
        
    # Find peaks with min peak distance of 2 (in bin indices)
    peaks, _ = find_peaks(curve, distance=2)
    
    if len(peaks) <= 1:
        if np.max(np.diff(spike_times)) < 0.1:
            return 0.0
        else:
            return 0.1
    else:
        peak1 = peaks[0]
        peak2 = peaks[1]
        
        valley_idx = peak1 + np.argmin(curve[peak1:peak2+1])
        # Bin centers or just use left edges like MATLAB does?
        # MATLAB uses steps for plotting and returning the point
        # So valleyPoint is steps[valley_idx]
        valley_point = steps[valley_idx]
        
        isin_th = valley_point / 1000.0  # back to seconds
        
        return min(isin_th, 0.1)


def burst_detect_isin(spike_times: np.ndarray, n: int, isin_th: float) -> tuple[dict, np.ndarray]:
    """Detect bursts using Bakkum's ISI_N method.
    
    Returns:
        Burst: dict with T_start, T_end, S (size in spikes)
        SpikeBurstNumber: 1D array assigning each spike to a burst (-1 if not in burst)
    """
    n_spikes = len(spike_times)
    spike_burst_number = np.full(n_spikes, -1, dtype=int)
    
    if n_spikes < n:
        return {"T_start": [], "T_end": [], "S": []}, spike_burst_number
        
    # Compute min dT for each spike
    # dT(j, i) = Spike.T(i + j) - Spike.T(i - (N-1) + j)
    # where j is in 0..N-1
    # We only care if min(dT) <= isin_th
    # So a spike i has criteria=1 if it belongs to ANY N-spike window with duration <= isin_th
    
    criteria = np.zeros(n_spikes, dtype=bool)
    
    window_durations = spike_times[n-1:] - spike_times[:-(n-1)]
    valid_windows = window_durations <= isin_th
    
    for i, valid in enumerate(valid_windows):
        if valid:
            criteria[i:i+n] = True
            
    in_burst = False
    num_burst = -1
    number = -1
    bl = 0
    
    for i in range(n-1, n_spikes):
        if not in_burst:
            if criteria[i]:
                in_burst = True
                num_burst += 1
                number = num_burst
                bl = 1
        else:
            if not criteria[i]:
                in_burst = False
                if bl < n:
                    # Erase if not big enough
                    spike_burst_number[spike_burst_number == number] = -1
                    num_burst -= 1
                number = -1
            elif (spike_times[i] - spike_times[i-(n-1)]) > isin_th and bl >= n:
                # Split consecutive bursts
                num_burst += 1
                number = num_burst
                bl = 1
            else:
                bl += 1
                
        spike_burst_number[i] = number
        
    # Handle last burst
    if in_burst and bl < n:
        spike_burst_number[spike_burst_number == number] = -1
        
    # Build Burst dict
    max_burst_num = np.max(spike_burst_number)
    
    t_start = []
    t_end = []
    s_size = []
    
    if max_burst_num >= 0:
        for b_num in range(max_burst_num + 1):
            idx = np.where(spike_burst_number == b_num)[0]
            if len(idx) > 0:
                t_start.append(spike_times[idx[0]])
                t_end.append(spike_times[idx[-1]])
                s_size.append(len(idx))
                
    burst_info = {
        "T_start": np.array(t_start),
        "T_end": np.array(t_end),
        "S": np.array(s_size),
    }
    
    return burst_info, spike_burst_number


def burst_detect_network(
    spike_times_dict: dict[int, np.ndarray], 
    fs: float,
    min_spikes: int = 10,
    min_channels: int = 3,
    isin_th_param: str | float = "automatic"
) -> tuple[list[dict], np.ndarray, list[np.ndarray], dict]:
    """Network burst detection combining all active channels."""
    
    # Combine spikes
    all_spikes = []
    all_chans = []
    
    for ch, times in spike_times_dict.items():
        if len(times) > 0:
            all_spikes.append(times)
            all_chans.append(np.full(len(times), ch))
            
    if not all_spikes:
        return [], np.zeros((0, 2)), [], {}
        
    t_cat = np.concatenate(all_spikes)
    c_cat = np.concatenate(all_chans)
    
    # Sort by time
    sort_idx = np.argsort(t_cat)
    t_cat = t_cat[sort_idx]
    c_cat = c_cat[sort_idx]
    
    # Merge coincident spikes (MATLAB trainCombine > 1 = 1)
    # We just keep unique times
    t_unique, unique_idx = np.unique(t_cat, return_index=True)
    # For channels, it keeps the first one (MATLAB lost channel info when summing anyway for network burst times)
    
    if str(isin_th_param).lower() == "automatic":
        min_unique_itis = 10
        if len(np.unique(np.diff(t_unique))) > min_unique_itis:
            isin_th = get_isin_threshold(t_unique, n=min_spikes)
        else:
            isin_th = 0.1
    else:
        isin_th = float(isin_th_param)
        
    burst_info, spike_bn = burst_detect_isin(t_unique, min_spikes, isin_th)
    
    n_bursts = len(burst_info["T_start"])
    burst_matrix_list = []
    burst_times = np.zeros((n_bursts, 2))
    burst_channels_list = []
    
    for i in range(n_bursts):
        # Time window
        t0 = burst_info["T_start"][i]
        t1 = burst_info["T_end"][i]
        
        burst_times[i, 0] = t0 * fs
        burst_times[i, 1] = t1 * fs
        
        # Original spikes in this window
        mask = (t_cat >= t0) & (t_cat <= t1)
        b_times = t_cat[mask]
        b_chans = c_cat[mask]
        
        unique_chans = np.unique(b_chans)
        burst_channels_list.append(unique_chans)
        
        b_dict = {ch: b_times[b_chans == ch] for ch in unique_chans}
        burst_matrix_list.append(b_dict)
        
    # Filter by min_channels
    valid = np.array([len(chans) >= min_channels for chans in burst_channels_list])
    
    if len(valid) > 0 and valid.sum() > 0:
        burst_matrix_list = [b for b, v in zip(burst_matrix_list, valid) if v]
        burst_times = burst_times[valid]
        burst_channels_list = [c for c, v in zip(burst_channels_list, valid) if v]
    else:
        burst_matrix_list = []
        burst_times = np.zeros((0, 2))
        burst_channels_list = []
        
    info = {"isin_th": isin_th}
    return burst_matrix_list, burst_times, burst_channels_list, info


def single_channel_burst_detection(
    spike_times_dict: dict[int, np.ndarray],
    n_channels: int,
    fs: float,
    min_spikes: int = 5,
    isi_threshold: str | float = "automatic",
    recording_duration_s: float = 0.0
) -> dict:
    """Per-channel burst detection matching singleChannelBurstDetection.m."""
    
    # Preallocate metrics
    bursting_units = []
    
    burst_matrices = {}
    burst_times_all = {}
    
    all_burst_rates = []
    all_inburst_frs = []
    all_burst_durs = []
    all_isis_within = []
    all_isis_outside = []
    all_fracs_in_burst = []

    total_sp_in_bst_sum = 0
    total_all_spikes = sum(len(spike_times_dict.get(ch, ())) for ch in range(n_channels))

    if recording_duration_s <= 0.0:
        for times in spike_times_dict.values():
            if len(times) > 0:
                recording_duration_s = max(recording_duration_s, np.max(times))

    for ch in range(n_channels):
        times = spike_times_dict.get(ch, np.array([]))
        
        if len(times) >= min_spikes:
            if str(isi_threshold).lower() == "automatic":
                min_unique_itis = 10
                if len(np.unique(np.diff(times))) > min_unique_itis:
                    isin_th = get_isin_threshold(times, n=min_spikes)
                else:
                    isin_th = 0.1
            else:
                isin_th = float(isi_threshold)
                
            b_info, s_bn = burst_detect_isin(times, min_spikes, isin_th)
        else:
            b_info = {"T_start": [], "T_end": [], "S": []}
            
        n_b = len(b_info["T_start"])
        burst_matrices[ch] = b_info
        
        if n_b > 0:
            bursting_units.append(ch)
            
            # Times in frames
            bt = np.zeros((n_b, 2))
            bt[:, 0] = b_info["T_start"] * fs
            bt[:, 1] = b_info["T_end"] * fs
            burst_times_all[ch] = bt
            
            # Metrics
            sp_in_bst = np.sum(b_info["S"])
            burst_rate = n_b / (recording_duration_s / 60.0) if recording_duration_s > 0 else 0
            
            b_durs = b_info["T_end"] - b_info["T_start"]  # in seconds
            b_durs_ms = b_durs * 1000.0
            
            # Within burst FR
            with np.errstate(divide='ignore', invalid='ignore'):
                in_burst_fr = b_info["S"] / b_durs
                in_burst_fr[b_durs == 0] = np.nan
            
            # ISI within
            isi_w = []
            for i in range(n_b):
                idx = np.where(s_bn == i)[0]
                if len(idx) > 1:
                    isi_w.append(np.mean(np.diff(times[idx])) * 1000.0)
                else:
                    isi_w.append(np.nan)
                    
            isi_o = []
            idx_o = np.where(s_bn == -1)[0]
            if len(idx_o) > 1:
                isi_o = np.diff(times[idx_o]) * 1000.0
            else:
                isi_o = [np.nan]
                
            all_burst_rates.append(burst_rate)
            all_inburst_frs.append(np.nanmean(in_burst_fr))
            all_burst_durs.append(np.nanmean(b_durs_ms))
            all_isis_within.append(np.nanmean(isi_w))
            all_isis_outside.append(np.nanmean(isi_o))
            all_fracs_in_burst.append(sp_in_bst / len(times))
            total_sp_in_bst_sum += sp_in_bst

    # Matches MATLAB's array_fracInBursts: total spikes-in-bursts across all
    # bursting electrodes, divided by total spikes across ALL electrodes
    # (not just bursting ones) — not a median of per-channel fractions.
    array_frac_in_bursts = total_sp_in_bst_sum / total_all_spikes if total_all_spikes > 0 else np.nan

    burstData = {
        "bursting_units": np.array(bursting_units),
        "array_burstRate": np.nanmedian(all_burst_rates) if all_burst_rates else np.nan,
        "all_burstRates": np.array(all_burst_rates),
        "array_inBurstFR": np.nanmedian(all_inburst_frs) if all_inburst_frs else np.nan,
        "all_inBurstFRs": np.array(all_inburst_frs),
        "array_burstDur": np.nanmedian(all_burst_durs) if all_burst_durs else np.nan,
        "all_burstDurs": np.array(all_burst_durs),
        "array_ISI_within": np.nanmedian(all_isis_within) if all_isis_within else np.nan,
        "all_ISIs_within": np.array(all_isis_within),
        "array_ISI_outside": np.nanmedian(all_isis_outside) if all_isis_outside else np.nan,
        "all_ISIs_outside": np.array(all_isis_outside),
        "array_fracInBursts": array_frac_in_bursts,
        "all_fracsInBursts": np.array(all_fracs_in_burst),
        "burst_matrices": burst_matrices,
        "burst_times": burst_times_all,
    }
    
    return burstData
