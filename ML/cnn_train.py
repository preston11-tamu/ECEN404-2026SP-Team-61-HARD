import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset
from sklearn.model_selection import StratifiedKFold, train_test_split
from sklearn.metrics import accuracy_score
from sklearn.metrics import confusion_matrix, ConfusionMatrixDisplay
from auxiliary import *
from training import *
import subprocess
import sys


if __name__ == '__main__':

    save_state = int( sys.argv[1] )
    kfold = int( sys.argv[2] )
    valid_fold = int( sys.argv[3] )
    diagnose = int( sys.argv[4] )
            
    # Force execution on CPU
    torch.set_default_device('cpu')

    FALL_DATA_DIR = 'data/fall'
    NOT_FALL_DATA_DIR = 'data/not_fall'

    config = {
        'hidden1': 64,
        'hidden2': 32,
        'lr': 0.0002,
        'weight_decay': 0.01,
        'batch_size': 1024,
        'epochs': 40,
        'patience': 1000, # disabled to watch for overfitting; lowest loss best model save will cover this
        'LSpatience': 4,
        'threshold': 0.5,
        'n_folds': 10,
        'test_size': 2/239, # out of 239
        'random_state': 42,
        'augmentation_factor': 60
    }

    # --- 2. Load File Paths and Labels ---
    filepaths, labels = load_data_from_folders(FALL_DATA_DIR, NOT_FALL_DATA_DIR)
    filepaths = np.array(filepaths)
    labels = np.array(labels)

    feature_names = ['num_objs', 'avg_x', 'range_x', 'std_vel','max_snr','avg_snr','vert_vel','accel', 'avg_rcs','max_rcs','spatial_extent']
    num_features = len(feature_names)
    
    if diagnose:
        data_diagnostic(filepaths,labels,num_features,feature_names)
    if len(filepaths) < 4:
        print("Error: Not enough data. Please add multiple json files to 'data/fall' and 'data/not_fall' folders.")
    else:
        train_val_files, test_files, y_train_val, y_test = train_test_split(
                filepaths, labels, test_size=config['test_size'], random_state=config['random_state'], stratify=labels
            )
        if kfold:
            # K-Folds Cross validation

            print(f"\n--- Dataset Split ---")
            print(f"Train+Validate: {len(train_val_files)} samples")
            print(f"Test: {len(test_files)} samples")

            print(f"\n--- {config['n_folds']}-Fold Cross-Validation ---")

            skf = StratifiedKFold(n_splits=config['n_folds'], shuffle=True, random_state=config['random_state'])

            fold_results = []
            all_val_cms = []
            fold_acc = []

            for fold, (train_idx, val_idx) in enumerate(skf.split(train_val_files, y_train_val)):
                print(f"\nFold {fold + 1}/{config['n_folds']}:")

                # Get files for this fold
                fold_train_files = [ train_val_files[index] for index in train_idx ]
                fold_val_files = [ train_val_files[index] for index in val_idx ]
                fold_y_train = [ y_train_val[index] for index in train_idx ]
                fold_y_val = [ y_train_val[index] for index in val_idx ]
                
                print(f" Train: {len(fold_train_files)} ({sum(fold_y_train)} falls)")
                print(f" Val: {len(fold_val_files)} ({sum(fold_y_val)} falls)")
                
                # Process and scale data (fit scaler on training fold only)
                X_train_scaled, scaler = process_files(fold_train_files, fit_scaler=True)
                X_val_scaled = process_files(fold_val_files, scaler=scaler, fit_scaler=False)

                num_features = X_train_scaled[0].shape[1]

                result = train_single_fold(
                    X_train_scaled, fold_y_train,
                    X_val_scaled, fold_y_val,
                    config, verbose=True
                )

                fold_results.append(result)
                all_val_cms.append(result['confusion_matrix'])

                tn, fp, fn, tp = result['confusion_matrix'].ravel()
                fold_acc.append([ (tn+tp) / (tn+fp+fn+tp) * 100 ])

                print(f" Train Acc: {result['train_acc']*100:.2f}%")
                print(f" Val Acc: {result['val_acc']*100:.2f}%")
                print(f" Confusion Matrix:\n{result['confusion_matrix']}")

            print("\nCROSS-VALIDATION SUMMARY")

            plt.figure(figsize=(10, 6))
            plt.plot(fold_acc, label='Validation Accuracy', marker='o', linestyle='-')
            plt.title(f'Accuracy over {config["n_folds"]}-Folds')
            plt.xlabel('Folds')
            plt.ylabel('Validation Accuracy')
            plt.legend()
            plt.grid(True)
            plt.savefig('fold_accuracy.png')
            plt.close()

            train_accs = [r['train_acc'] for r in fold_results]
            val_accs = [r['val_acc'] for r in fold_results]

            print(f"\nTraining Accuracy: {np.mean(train_accs)*100:.2f}% ± {np.std(train_accs)*100:.2f}%")
            print(f"Validation Accuracy: {np.mean(val_accs)*100:.2f}% ± {np.std(val_accs)*100:.2f}%")

            total_cm = sum(all_val_cms)
            print(f"\nAggregated Confusion Matrix (all validation folds):")
            print(total_cm)

            tn, fp, fn, tp = total_cm.ravel()
            total_samples = tn + fp + fn + tp
            print(f"True Negatives:  {tn} ({tn/total_samples*100:.1f}%)")
            print(f"False Positives: {fp} ({fp/total_samples*100:.1f}%) - false alarms")
            print(f"False Negatives: {fn} ({fn/total_samples*100:.1f}%) - MISSED FALLS")
            print(f"True Positives:  {tp} ({tp/total_samples*100:.1f}%)")
            print(f"Fall Recall:     {tp/(tp+fn)*100:.1f}% (sensitivity)")
            print(f"Fall Precision:  {tp/(tp+fp)*100:.1f}%" if (tp+fp) > 0 else "Fall Precision:  N/A")
    

        # --- Final Test Set Evaluation ---
        print("\nFINAL TEST SET EVALUATION")
    
        # Retrain on ALL train_val data, test on held-out test set
        print("\nRetraining on full train+val set...")

        X_trainval_scaled, final_scaler = process_files(train_val_files, fit_scaler=True)
        X_test_scaled = process_files(test_files, scaler=final_scaler, fit_scaler=False)

        num_features = X_trainval_scaled[0].shape[1]

        final_train_idx, final_val_idx = train_test_split(
            range(len(X_trainval_scaled)), test_size=1/6, random_state=config['random_state'], stratify=y_train_val
        )

        X_final_train = [X_trainval_scaled[i] for i in final_train_idx]
        y_final_train = [y_train_val[i] for i in final_train_idx]

        X_final_val = [X_trainval_scaled[i] for i in final_val_idx]
        y_final_val = [y_train_val[i] for i in final_val_idx]

        print("\nValidation set size: ", len(X_final_val))
        
        final_result = train_single_fold(
            X_final_train, y_final_train,
            X_final_val, y_final_val,
            config, verbose=True
        )

        # Smooth curves for better visualization
        def smooth(scalars, weight=0.6):
            last = scalars[0]
            smoothed = list()
            for point in scalars:
                smoothed_val = last * weight + (1 - weight) * point
                smoothed.append(smoothed_val)
                last = smoothed_val
            return smoothed

        plt.figure(figsize=(10, 6))
        if kfold:
            cv_train_losses = [r['all_train_loss'] for r in fold_results]
            cv_val_losses = [r['all_val_loss'] for r in fold_results]
            
            max_len = max(len(l) for l in cv_train_losses)
            padded_cv_train = [l + [l[-1]] * (max_len - len(l)) for l in cv_train_losses]
            padded_cv_val = [l + [l[-1]] * (max_len - len(l)) for l in cv_val_losses]
            
            avg_cv_train = np.mean(padded_cv_train, axis=0)
            avg_cv_val = np.mean(padded_cv_val, axis=0)
            
            plt.plot(smooth(avg_cv_train.tolist()), label='Avg CV Training Loss', linestyle=':', color='tab:blue')
            plt.plot(smooth(avg_cv_val.tolist()), label='Avg CV Validation Loss', linestyle=':', color='tab:orange')

        plt.plot(final_result['all_train_loss'], label='Final Training Loss', linestyle='-', color='tab:blue')
        plt.plot(final_result['all_val_loss'], label='Final Validation Loss', linestyle='-', color='tab:orange')
        
        plt.title('Aggregated Training & Validation Loss Curves')
        plt.xlabel('Epoch')
        plt.ylabel('Loss (BCEWithLogitsLoss)')
        plt.legend()
        plt.grid(True)
        plt.savefig('final_training_loss.png')
        plt.close()
        
        # Evaluate on test set
        final_model = final_result['model']
        final_model.eval()
        
        test_ds = variable_length_dataset(X_test_scaled, y_test)
        
        test_preds, test_labels = [], []
        
        with torch.no_grad():
            for i in range(len(test_ds)):
                # Get PyTorch tensors for CNN
                sequence_tensor, label_tensor, length_tensor = test_ds[i]
                
                seq_batch = sequence_tensor.unsqueeze(0)
                len_batch = length_tensor.unsqueeze(0)

                output = final_model(seq_batch, len_batch)
                pred = int((torch.sigmoid(output) > config['threshold']).item())
                
                test_preds.append(pred)
                test_labels.append(int(label_tensor.item()))
                
        test_acc = accuracy_score(test_labels, test_preds)
        test_cm = confusion_matrix(test_labels, test_preds)
        
        print(f"\nTest Accuracy: {test_acc*100:.2f}%")
        print(f"Test Confusion Matrix:")
        print(test_cm)
        
        tn, fp, fn, tp = test_cm.ravel()
        print(f"\nTest Metrics:")
        print(f"True Negatives:  {tn}")
        print(f"False Positives: {fp} - false alarms")
        print(f"False Negatives: {fn} - MISSED FALLS")
        print(f"True Positives:  {tp}")
        print(f"Fall Recall:     {tp/(tp+fn)*100:.1f}%" if (tp+fn) > 0 else "Fall Recall: N/A")
        print(f"Fall Precision:  {tp/(tp+fp)*100:.1f}%" if (tp+fp) > 0 else "Fall Precision:  N/A")
        
        # --- Summary ---
        print("\nFINAL SUMMARY")
        if kfold:
            print(f"Validation Accuracy: {np.mean(val_accs)*100:.2f}% ± {np.std(val_accs)*100:.2f}%")
        print(f"Test Accuracy:          {test_acc*100:.2f}%")
        print(f"Missed Falls (Test):      {fn} out of {tp+fn}")
        print(f"False Alarms (Test):      {fp} out of {tn+fp}")

        # --- Retrain on Validation Set ---
        if valid_fold:
            print("\nRetraining final model on the 1/6 validation set to maximize data usage...")
            final_model.train()
            
            aug_factor = config.get('augmentation_factor', 0)
            aug_X_val, aug_y_val = [], []
            for seq, label in zip(X_final_val, y_final_val):
                aug_X_val.append(seq)
                aug_y_val.append(label)
                for _ in range(aug_factor):
                    aug_X_val.append(augment_sequence(seq))
                    aug_y_val.append(label)
                    
            val_retrain_ds = variable_length_dataset(aug_X_val, aug_y_val)
            val_retrain_loader = DataLoader(val_retrain_ds, batch_size=config['batch_size'], shuffle=True, collate_fn=collate_fn)
            
            optimizer = torch.optim.Adam(final_model.parameters(), lr=config['lr'], weight_decay=config['weight_decay'])
            num_not_fall = sum(1 for label in aug_y_val if label == 0)
            num_fall = sum(1 for label in aug_y_val if label == 1)
            pos_weight = torch.tensor((num_not_fall / num_fall) if num_fall > 0 else 1.0, dtype=torch.float32)
            criterion = nn.BCEWithLogitsLoss(pos_weight=pos_weight)
            
            for epoch in range(config['epochs']*3 // 4):
                for sequences, labels, lengths in val_retrain_loader:
                    outputs = final_model(sequences, lengths)
                    loss = criterion(outputs, labels)
                    optimizer.zero_grad()
                    loss.backward()
                    optimizer.step()
            print("Validation set retraining completed.")

        if save_state:
            torch.save({
                'model_state_dict': final_model.state_dict(),
                'scaler': final_scaler,
                'num_features': num_features,
                'seed': 42,
                'test_accuracy': test_acc,
                'config': config
                },
            'cnn_fall_detection.pth')

            # Export to ONNX
            subprocess.run(['python', 'pyt_to_onnx.py'])