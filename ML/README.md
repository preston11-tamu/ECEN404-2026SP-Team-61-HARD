
# ML — Fall Detection via mmWave Radar

This directory contains the machine learning pipeline for detecting human falls using millimeter-wave (mmWave) radar sensor data. A 1D CNN with a Temporal Attention mechanism classifies sequences of radar frames as fall or non-fall events.

---

## Directory Structure

```
ML/
├── cnn_train.py        Main training script (k-fold CV, final training, ONNX export)
├── training.py         Model definition (FallDetectionCNN) and training loop
├── preprocessing.py    Raw radar JSON → 11-feature vectors per frame
├── auxiliary.py        Data loading, diagnostics, and MinMax scaling utilities
├── spliced_eval.py     Sliding-window inference on ONNX model
│
├── data/
│   ├── fall/           Raw .dat radar recordings of fall events
│   └── nonfall/        Raw .dat radar recordings of non-fall activity
│
└── parse/
    ├── demo.py             Serial capture and binary-to-JSON parser
    ├── common_structs.py   Byte-level TLV frame parser
    ├── demo_structs.py     Session management for captured frames
    └── runscript.txt       Instructions for running the parser
```

---

## Pipeline Overview

```
Raw .dat files
      │
      ▼  parse/demo.py
JSON frame files
      │
      ▼  preprocessing.py
11 engineered features per frame (variable-length sequences)
      │
      ▼  cnn_train.py + training.py
Trained CNN model  →  cnn_fall_detection.pth / .onnx
      │
      ▼  spliced_eval.py
Sliding-window fall/non-fall predictions
```

---

## Step-by-Step Usage

### Step 1 — Parse raw radar recordings

The `data/` folders contain binary `.dat` files recorded from the TI IWR radar. Convert them to JSON before training:

```bash
cd parse/
python demo.py --command_port=COM3 --data_port=COM4 --data_type=fall
python demo.py --command_port=COM3 --data_port=COM4 --data_type=notfall
```

Parsed JSON files are written to `data/fall/` and `data/nonfall/`. See `parse/runscript.txt` for additional options.

### Step 2 — Train the model

```bash
python cnn_train.py <save_state> <kfold> <valid_fold> <diagnose>
```

| Argument | Values | Description |
|---|---|---|
| `save_state` | 0 / 1 | Save model weights to `cnn_fall_detection.pth` |
| `kfold` | 0 / 1 | Run 10-fold stratified cross-validation |
| `valid_fold` | 0 / 1 | Retrain on the validation fold after CV |
| `diagnose` | 0 / 1 | Print per-feature class statistics |

Example — full training run with saved model:

```bash
python cnn_train.py 1 1 1 0
```

**Outputs:**
- `fold_accuracy.png` — validation accuracy across all 10 folds
- `final_training_loss.png` — training and validation loss curves
- `cnn_fall_detection.pth` — model weights and fitted scaler (if `save_state=1`)

### Step 3 — Export to ONNX

```bash
python pyt_to_onnx.py
```

Produces `cnn_fall_detection.onnx` and `scaler.save` for deployment.

### Step 4 — Evaluate on new data

```bash
python spliced_eval.py /path/to/test/json/dir/
```

Runs sliding-window inference (window=400 frames, stride=100) and prints per-window fall probabilities.

---

## Model Architecture

**Input:** variable-length sequence of shape `[T, 11]` (frames × features)

```
Conv1d Block 1  (11 → 32 channels, kernel=21, BatchNorm, Dropout=0.3, MaxPool)
Conv1d Block 2  (32 → 64 channels, kernel=11, BatchNorm, Dropout=0.3, MaxPool)
       │
       ├─ Global Max Pool    →  [64]
       └─ Temporal Attention →  [64]   (learns to weight impact-moment frames)
       │
  Concat  →  [128]
       │
  FC 128 → 64 → 32 → 1  (Dropout=0.6 between layers)
       │
  BCEWithLogitsLoss (pos_weight for class imbalance)
```

### Engineered Features (11 total)

| Feature | Description |
|---|---|
| `num_objs` | Number of detected point-cloud objects |
| `avg_x` | Mean height (normalized to starting position) |
| `range_x` | Height span of detected points |
| `std_vel` | Velocity standard deviation |
| `max_snr` | Peak signal-to-noise ratio |
| `avg_snr` | Mean SNR |
| `vert_vel` | Derived vertical velocity (Savitzky-Golay) |
| `accel` | Derived vertical acceleration |
| `avg_rcs` | Mean radar cross-section |
| `max_rcs` | Peak radar cross-section |
| `spatial_extent` | avg_y × range_x (body spread) |

### Training Configuration

```python
config = {
    'hidden1': 64,
    'hidden2': 32,
    'lr': 0.0002,
    'weight_decay': 0.01,
    'batch_size': 1024,
    'epochs': 40,
    'patience': 1000,
    'LSpatience': 4,
    'threshold': 0.5,
    'n_folds': 10,
    'test_size': 2/239,
    'random_state': 42,
    'augmentation_factor': 60,
}
```

Data augmentation (60× per training sequence) applies random combinations of jitter, scaling, time warping, and segment masking to improve generalization on the small dataset.

---

## Dependencies

```
torch
scikit-learn
numpy
scipy
onnx
onnxruntime
joblib
matplotlib
```

Install with:

```bash
pip install torch scikit-learn numpy scipy onnx onnxruntime joblib matplotlib
```

---

## Notes

- The `parse/` scripts expect a live TI IWR radar connected over serial, or pre-recorded `.dat` files fed through the same interface.
- DBSCAN clustering (`eps=0.3 m`, `min_samples=4`) is applied per-frame during preprocessing to isolate the main subject and suppress multipath noise.
- Sequences that are all-NaN after filtering are dropped before training.
- The sliding-window evaluator in `spliced_eval.py` uses a lower threshold (0.4) than training (0.5) to reduce missed-fall false negatives.
