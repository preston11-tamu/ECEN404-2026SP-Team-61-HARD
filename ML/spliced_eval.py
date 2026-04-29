import onnx
import onnxruntime as ort
from natsort import natsorted
import joblib
import numpy as np
import preprocessing as pp
import glob
import os
import sys

def prediction(filepath, session, scaler, window_size=400, stride=100):
    # Threshold for binary classification
    threshold = 0.4

    for file in filepath:
        # Load and preprocess
        raw_features = pp.dataprep(file)
        if raw_features is None:
            continue
            
        feature_array = np.array(raw_features, dtype=np.float64)
        
        scaled = scaler.transform(feature_array)
        
        total_frames = scaled.shape[0]
        print(f"\n--- Analyzing {os.path.basename(file)} ({total_frames} frames) ---")

        # Loop through data in chunks of WINDOW_SIZE
        # Logic: 0->120, 120->240, 240->300 (remainder)
        for start_idx in range(0, total_frames, stride):
            end_idx = min(start_idx + window_size, total_frames)
            chunk_len = end_idx - start_idx

            # 1. Slice the chunk
            chunk = scaled[start_idx:end_idx]

            # Skip empty chunks or small remainders already covered by a previous window
            if chunk.shape[0] == 0:
                continue
            if start_idx > 0 and chunk_len < stride:
                continue

            # 2. Prepare Input for ONNX
            # Add batch dimension: [1, Length, Features]
            input_sequence = chunk.astype(np.float32)[np.newaxis, :, :]

            # 3. Run Inference
            try:
                output_logit = session.run(
                    None,
                    {
                        'sequence': input_sequence,
                        'length': np.array([chunk_len], dtype=np.int64)
                    }
                )

                logit = output_logit[0][0][0]
                probability = 1 / (1 + np.exp(-logit))

                prediction = "FALL" if probability >= threshold else "NOT FALL"

                print(f"  Frames {start_idx:03d}-{end_idx:03d}: {prediction} ({probability:.3f})")

            except Exception as e:
                print(f"  Error processing frames {start_idx}-{end_idx}: {e}")
        print(f"--- Finished analyzing {os.path.basename(file)} ---\n\n")

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python eval_cnn_onnx.py <directory_path>")
        sys.exit(1)

    directory = sys.argv[1]

    # Load resources
    print("Loading Scaler and ONNX Model...")
    scaler = joblib.load('scaler.save')
    ort_session = ort.InferenceSession('cnn_fall_detection.onnx')

    # Get files
    test_files = natsorted(glob.glob(os.path.join(directory, '*.json')))

    if not test_files:
        print("No .json files found in directory.")
    else:
        prediction(test_files, ort_session, scaler)