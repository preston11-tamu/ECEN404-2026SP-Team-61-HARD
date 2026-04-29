import glob
import os
import preprocessing as pp
import numpy as np
import matplotlib.pyplot as plt
from sklearn.preprocessing import MaxAbsScaler, MinMaxScaler, RobustScaler

def load_data_from_folders(fall_dir, not_fall_dir):
    """Loads file paths and assigns labels (1 for fall, 0 for not fall)."""
    filepaths = []
    labels = []
    
    # Get all .json files from the fall directory
    fall_files = sorted(glob.glob(os.path.join(fall_dir, '*.json')))
    filepaths.extend(fall_files)
    labels.extend([1] * len(fall_files))
    
    # Get all .json files from the not_fall directory
    not_fall_files = sorted(glob.glob(os.path.join(not_fall_dir, '*.json')))
    filepaths.extend(not_fall_files)
    labels.extend([0] * len(not_fall_files))
    
    return filepaths, labels

def data_diagnostic(
    filepaths,
    labels,
    num_features,
    feature_names=['num_objs', 'avg_x', 'range_x', 'std_vel','max_snr','avg_snr','vert_vel','accel','avg_rcs','max_rcs','spatial_extent']
):
    
    print("\n--- Feature Comparison: Fall vs Not-Fall ---")
    fall_features = {i: [] for i in range(num_features)}
    notfall_features = {i: [] for i in range(num_features)}

    for f, label in zip(filepaths, labels):
        raw = pp.dataprep(f)
        if raw is None:
            continue
        for frame in raw:
            for i in range(num_features):
                if label == 1:
                    fall_features[i].append(frame[i])
                else:
                    notfall_features[i].append(frame[i])

    print(f"\n{'Feature':<12} {'Fall Mean':>12} {'NotFall Mean':>12} {'Difference':>12}")
    print("-" * 52)
    for i, name in enumerate(feature_names):
        fall_mean = np.mean(fall_features[i])
        notfall_mean = np.mean(notfall_features[i])
        diff = fall_mean - notfall_mean
        print(f"{name:<12} {fall_mean:>12.3f} {notfall_mean:>12.3f} {diff:>12.3f}")

def process_files(files, scaler=None, fit_scaler=False):
    sequences = []
    for f in files:
        raw_features = pp.dataprep(f)
        feature_array = np.array(raw_features, dtype=np.float64)
        sequences.append(feature_array)
    
    if fit_scaler and scaler is None:
        scaler = MinMaxScaler()
        concatenated = np.concatenate(sequences, axis=0)
        scaler.fit(concatenated)
        
    scaled_sequences = [scaler.transform(seq) for seq in sequences]
    
    if fit_scaler:
        return scaled_sequences, scaler
    else:
        return scaled_sequences
    
def plot_loss_curve(train_loss, val_loss, save_path="final_training_loss_cnn.png"):
    plt.figure(figsize=(10, 6))
    plt.plot(train_loss, label='Training Loss', linestyle='-')
    plt.plot(val_loss, label='Validation Loss', linestyle='--')
    plt.title('Final Model Training & Validation Loss Curve')
    plt.xlabel('Epoch')
    plt.ylabel('Loss (BCEWithLogitsLoss)')
    plt.legend()
    plt.grid(True)
    plt.savefig(save_path)
    plt.close()