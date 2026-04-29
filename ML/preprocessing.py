import json
from scipy.signal import savgol_filter, medfilt
from sklearn.cluster import DBSCAN
import numpy as np

def _moving_average(data, window_size):
    """
    Apply a centered moving average filter to smooth the data.
    Uses reflection padding to handle edge effects.
    """
    if len(data) == 0 or window_size <= 1:
        return data
    
    kernel = np.ones(window_size) / window_size
    padded = np.pad(data, window_size // 2, mode='reflect')
    return np.convolve(padded, kernel, mode='valid')


def _interpolate_nans(arr):
    """
    Linearly interpolate NaN values in a 1D array.
    Edge NaNs are filled with nearest valid value.
    """
    nan_mask = np.isnan(arr)
    
    if not nan_mask.any():
        return arr
    if nan_mask.all():
        return np.zeros_like(arr)
    
    x = np.arange(len(arr))
    valid_mask = ~nan_mask
    arr[nan_mask] = np.interp(x[nan_mask], x[valid_mask], arr[valid_mask])
    return arr

def _remove_outliers(objects, m=2.0):
    """
    Removes spatial outliers from a list of object dictionaries based on 
    distance from the frame's centroid.
    """
    if len(objects) < 4:
        return objects

    x, y = np.array([obj.get('x', 0) for obj in objects]), np.array([obj.get('y', 0) for obj in objects])
    
    coords = np.array(list(zip(x, y)))
    centroid = np.mean(coords, axis=0)
    distances = np.linalg.norm(coords - centroid, axis=1)
    
    mean_dist = np.mean(distances)
    std_dist = np.std(distances)
    threshold = mean_dist + (m * std_dist)
    
    clean_objects = []
    for i, obj in enumerate(objects):
        if distances[i] <= threshold:
            clean_objects.append(obj)
            
    return clean_objects

def compute_rcs(x_vals, y_vals, snr_vals):
    """
    Computes a relative proxy for Radar Cross Section (RCS) using the radar equation.
    Assuming the standard relationship: RCS_dB = SNR_dB + 40 * log10(R)
    
    Args:
        x_vals (np.ndarray): Array of X coordinates.
        y_vals (np.ndarray): Array of Y coordinates.
        snr_vals (np.ndarray): Array of SNR values.
        
    Returns:
        np.ndarray: Array of estimated relative RCS values.
    """
    # Calculate range (distance from radar) R = sqrt(x^2 + y^2)
    r = np.sqrt(x_vals**2 + y_vals**2)
    # Apply a small epsilon to avoid log10(0) if distance is 0
    r = np.maximum(r, 1e-3)
    
    # Relative RCS computation
    rcs_vals = snr_vals + 40 * np.log10(r)
    return rcs_vals

def _extract_frame_features(frame_data, velocity_thresh=0.1):
    """
    Extract features from a single radar frame.
    Returns feature list or None if frame should be skipped.
    """
    header = frame_data.get('header', {})
    body = frame_data.get('body', [])
    
    num_objs = header.get('numDetectedObj', 0)
    if num_objs == 0:
        return [0, 0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]  # NaN for avg_x so it gets interpolated rather than injecting a false zero-height

    # Initialize defaults
    avg_x = range_x = avg_y = std_vel  = max_snr = avg_snr = avg_rcs = max_rcs = 0.0

    range_ceil = 1.5
    snr_threshold = 10**2
    
    # Find TLVs by type for efficient lookup
    tlv_dict = {tlv.get('header', {}).get('type'): tlv for tlv in body}
    obj_tlv = tlv_dict.get(1)
    info_tlv = tlv_dict.get(7)
    
    # We need both point cloud (type 1) and side info (type 7) to proceed
    if obj_tlv and info_tlv:
        obj_data = obj_tlv.get('body', {}).get('data', [])
        info_data = info_tlv.get('body', {}).get('data', [])
        
        # Ensure data exists and object/side-info lists have matching lengths
        if obj_data and len(obj_data) == len(info_data):
            # Combine object data with its side info (SNR) to ensure correct association
            combined_objs = [
                {**obj, 'snr': info.get('snr', 0)}
                for obj, info in zip(obj_data, info_data)
            ]

            combined_objs = _remove_outliers(combined_objs, m=1.0)

            # Filter for moving objects within distance threshold
            moving_objs = [
                obj for obj in combined_objs
                if (
                    abs(obj.get('velocity', 0)) > velocity_thresh 
                    and abs(obj.get('x', 0)) < range_ceil 
                    and obj.get('snr', 0) > snr_threshold
                )
            ]

            
            # Cluster with DBSCAN to remove noise points and isolate the main subject
            if len(moving_objs) > 2: # DBSCAN needs at least 3 points for min_samples=3
                coords = np.array([[obj.get('x', 0), obj.get('y', 0)] for obj in moving_objs])
                
                # eps: max distance between points to be neighbors (e.g., 0.5 meters)
                # min_samples: min points to form a core cluster
                db = DBSCAN(eps=0.3, min_samples=4).fit(coords)
                labels = db.labels_

                # Find the largest cluster (ignoring outliers labeled -1)
                unique_labels, counts = np.unique(labels[labels != -1], return_counts=True)
                
                if len(counts) > 0:
                    # Identify the label of the largest cluster
                    largest_cluster_label = unique_labels[np.argmax(counts)]
                    
                    # Filter objects to keep only those in the largest cluster
                    moving_objs = [obj for obj, label in zip(moving_objs, labels) if label == largest_cluster_label]
                else:
                    # All points were classified as outliers
                    moving_objs = []

            if moving_objs:
                # Use a single pass to create numpy arrays for efficiency
                values = np.array([[obj.get(k, 0) for k in ['x', 'y', 'velocity', 'snr']] for obj in moving_objs])
                xvals, yvals, velocities, snr_vals = values[:, 0], values[:, 1], values[:, 2], values[:, 3]

                avg_x = np.mean(xvals)
                range_x = np.ptp(xvals)
                avg_y = np.mean(yvals)
                std_vel = np.var(velocities)

                max_snr = np.max(snr_vals)
                avg_snr = np.mean(snr_vals)
                
                rcs_vals = compute_rcs(xvals, yvals, snr_vals)
                avg_rcs = np.mean(rcs_vals)
                max_rcs = np.max(rcs_vals)

    spatial_extent = avg_y * range_x

    return [num_objs, avg_x, range_x, std_vel, max_snr, avg_snr, avg_rcs, max_rcs, spatial_extent]

def _compute_kinematics(features_array, frame_rate=20, smooth_window=15):
    """
    Compute vertical velocity and acceleration by differentiating the Avg X feature.

    Since the IWR1642 is oriented sideways (X is physical Z/height),
    Doppler Velocity measures radial movement (e.g. walking towards the radar).
    By differentiating Avg X (Height) instead, we isolate vertical acceleration
    and velocity to prevent false positives caused by walking/running.
    """
    n_frames = len(features_array)
    if n_frames < 2:
        return np.zeros(n_frames), np.zeros(n_frames)

    # Extract Avg X (Feature at index 1 is height)
    raw_height = features_array[:, 1]

    # 1. Median filter to drop sudden, single-frame noise spikes in radar height
    med_window = min(5, n_frames)
    if med_window % 2 == 0:
        med_window -= 1
    if med_window >= 3:
        raw_height = medfilt(raw_height, kernel_size=med_window)

    # Ensure window is smaller than data length and odd.
    if len(raw_height) < smooth_window:
        smooth_window = len(raw_height)
    if smooth_window % 2 == 0:
        smooth_window -= 1

    # Ensure polyorder is less than window length.
    polyorder = 3
    if smooth_window <= polyorder:
        return np.zeros(n_frames), np.zeros(n_frames) # Not enough data to calculate kin reliably.

    # 2. Compute smooth vertical velocity (Analytic 1st Derivative)
    vert_vel = savgol_filter(raw_height, window_length=smooth_window, polyorder=polyorder, deriv=1, delta=1/frame_rate)

    # 3. Compute smooth vertical acceleration (Analytic 2nd Derivative)
    vert_accel = savgol_filter(raw_height, window_length=smooth_window, polyorder=polyorder, deriv=2, delta=1/frame_rate)
    return vert_vel, vert_accel

def _extract_range_features(frame_data):
    body = frame_data.get('body', [])
    
    # Find range profile TLV (type 2)
    tlv_dict = {tlv.get('header', {}).get('type'): tlv for tlv in body}
    range_tlv = tlv_dict.get(2)
    
    if range_tlv:
        range_data = range_tlv.get('body', {}).get('data', [])
        range_bins = np.array([item.get('bin', 0) for item in range_data])
        # Pad to 64 bins if needed
        if len(range_bins) < 64:
            range_bins = np.pad(range_bins, (0, 64 - len(range_bins)), mode='constant')
        if len(range_bins) > 64:
            range_bins = range_bins[:64]
    else:
        return [0.0] * 64
   
    return range_bins


def dataprep(filepath='parsed.json', smooth_window=5):
    """
    Loads radar data from the specified JSON file, extracts features from each
    frame, applies smoothing, and computes derived features.

    Args:
        filepath (str): The path to the JSON data file.
        smooth_window (int): Window size for moving average smoothing (default 5).
                            Set to 1 or None to disable smoothing.
        smooth_window (int): Window size for the final moving average smoothing pass.
                             Set to 1 or 0 to disable.

    Returns:
        list: A 2D list where each row is a feature vector for a single frame.
              Features: [num_objs, avg_x, range_x, std_vel, min_vel, max_snr, avg_snr, avg_rcs, max_rcs, spatial_extent, vert_vel, accel]
              Returns None if file not found or error occurs.
    """
    # --- Load JSON data ---
    try:
        with open(filepath, 'r') as f:
            all_messages = json.load(f)['messages'][1:]
    except FileNotFoundError:
        print(f"Error: The file '{filepath}' was not found.")
        return None
    except (json.JSONDecodeError, KeyError, IndexError) as e:
        print(f"Error processing JSON file: {e}")
        return None

    if not all_messages:
        print(f"Warning: No frame data found in '{filepath}'")
        return None

    # --- Extract features from each frame ---
    all_frame_features = []
    for frame_data in all_messages:
        features = _extract_frame_features(frame_data)
        if features is not None:
            all_frame_features.append(features)

    if not all_frame_features:
        print(f"Warning: No valid features extracted from '{filepath}'")
        return None

    # Convert to numpy array for vectorized operations
    features_array = np.array(all_frame_features, dtype=np.float64)

    # --- Feature indices ---
    IDX_AVG_X = 1

    # --- Interpolate NaN values ---
    for col in [IDX_AVG_X]:
        features_array[:, col] = _interpolate_nans(features_array[:, col])

    # Make height relative to the starting position
    features_array[:, IDX_AVG_X] = features_array[:, IDX_AVG_X] - features_array[0, IDX_AVG_X]

    # --- Compute kinematics ---
    vert_vel, accel = _compute_kinematics(features_array, smooth_window=15)

    # --- Combine features with kinematics ---
    features_final = np.column_stack([features_array, vert_vel, accel])

    # --- Apply moving average smoothing ---
    if smooth_window and smooth_window > 1:
        for i in range(features_final.shape[1]):
            features_final[:, i] = _moving_average(features_final[:, i], smooth_window)
            
    return features_final.tolist()

def rangebin_prep(filepath='parsed.json'):
    try:
        with open(filepath, 'r') as f:
            # The actual data is nested under the "messages" key
            # and the first item is a raw string we need to skip.
            all_messages = json.load(f)['messages'][1:]
    except FileNotFoundError:
        print(f"Error: The file '{filepath}' was not found.")
        return None
    except (json.JSONDecodeError, KeyError, IndexError) as e:
        print(f"Error processing JSON file: {e}")
        return None

    all_frame_features = []

    for frame_data in all_messages:
        range_profile = _extract_range_features(frame_data)
        all_frame_features.append(range_profile)

    return all_frame_features

def data_diagnostic(
    filename,
    num_features,
    feature_names=['num_objs', 'avg_x', 'range_x', 'std_vel', 'max_snr','avg_snr','avg_rcs','max_rcs','spatial_extent','vert_vel','accel']
):
    
    print("\n--- Features Diagnostic ---")
    features = {i: [] for i in range(num_features)}

    raw = dataprep(filename)
    if raw is None:
        print("No data to analyze.")
        return
    for frame in raw:
        for i in range(num_features):
            features[i].append(frame[i])

    print(f"\n{'Feature':<12} {'Feature Mean':>12}")
    print("-" * 26)
    for i, name in enumerate(feature_names):
        feature_mean = np.mean(features[i])
        print(f"{name:<12} {feature_mean:>12.3f}")
