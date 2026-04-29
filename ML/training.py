import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset
import numpy as np
from sklearn.metrics import accuracy_score
from sklearn.metrics import confusion_matrix, ConfusionMatrixDisplay

class variable_length_dataset(torch.utils.data.Dataset):
    def __init__(self, sequences, labels):
        self.sequences = sequences
        self.labels = labels

    def __len__(self):
        return len(self.sequences)

    def __getitem__(self, idx):
        seq = self.sequences[idx]
            
        sequence = torch.tensor(seq, dtype=torch.float32)
        label = torch.tensor(self.labels[idx], dtype=torch.float32)
        length = torch.tensor(len(seq), dtype=torch.long)
        return sequence, label, length
    
def collate_fn(batch):
    sequences, labels, lengths = zip(*batch)
    padded_seqs = nn.utils.rnn.pad_sequence(sequences, batch_first=True)

    labels_stacked = torch.stack(labels).unsqueeze(1)
    lengths_stacked = torch.stack(lengths)

    return padded_seqs, labels_stacked, lengths_stacked

def augment_sequence(sequence):
    """
    Applies diverse augmentations inspired by radar physics:
    1. Jitter: Additive noise (Sensor thermal noise)
    2. Scaling: Multiplicative factor (RCS/Velocity magnitude variation)
    3. Time Warping: Resampling (Fall speed variation)
    4. Masking: Zeroing out segments (Packet loss/Occlusion)
    """
    choice = np.random.rand()
    
    if choice < 0.4:
        # Jitter (40% chance)
        noise_level = np.random.uniform(0.01, 0.05)
        return sequence + np.random.normal(0, noise_level, sequence.shape)
        
    elif choice < 0.6:
        # Scaling (20% chance)
        factor = np.random.uniform(0.8, 1.2)
        return sequence * factor
        
    elif choice < 0.8:
        # Time Warping (20% chance)
        speed_factor = np.random.uniform(0.8, 1.2)
        old_len = sequence.shape[0]
        new_len = int(old_len * speed_factor)
        if new_len < 5: new_len = 5
        
        # Interpolate each feature to the new length
        new_indices = np.linspace(0, old_len - 1, new_len)
        old_indices = np.arange(old_len)
        new_seq = np.zeros((new_len, sequence.shape[1]))
        for i in range(sequence.shape[1]):
            new_seq[:, i] = np.interp(new_indices, old_indices, sequence[:, i])
        return new_seq
        
    else:
        # Masking/Dropout (20% chance)
        seq_len = sequence.shape[0]
        if seq_len > 10:
            mask_len = np.random.randint(1, max(2, seq_len // 5))
            start_idx = np.random.randint(0, seq_len - mask_len)
            masked_seq = sequence.copy()
            masked_seq[start_idx : start_idx + mask_len, :] = 0
            return masked_seq
        return sequence

# Convolutional Neural Network for Fall Detection
class TemporalAttention(nn.Module):
    """
    Attention mechanism that learns to focus on important time steps.
    For fall detection, this should learn to attend to high-velocity impact moments.
    """
    def __init__(self, feature_dim):
        super(TemporalAttention, self).__init__()
        # Attention scoring network: maps each timestep's features to a score
        self.attention_fc = nn.Sequential(
            nn.Linear(feature_dim, feature_dim // 2),
            nn.Tanh(),
            nn.Linear(feature_dim // 2, 1, bias=False)
        )
    
    def forward(self, x, lengths):
        # x: [Batch, Time, Features]
        # lengths: [Batch] actual sequence lengths
        
        batch_size, max_len, _ = x.size()
        
        # 1. Compute attention scores for each timestep
        # Shape: [Batch, Time, 1]
        scores = self.attention_fc(x)
        
        # 2. Create mask for padded positions
        # Shape: [Batch, Time]
        mask = torch.arange(max_len, device=x.device)[None, :] < lengths[:, None]
        
        # 3. Set padded positions to -inf so softmax gives them 0 weight
        scores = scores.squeeze(-1)  # [Batch, Time]
        scores = scores.masked_fill(~mask, float('-inf'))
        
        # 4. Softmax to get attention weights
        attention_weights = torch.softmax(scores, dim=1)  # [Batch, Time]
        
        # 5. Handle edge case where all positions are masked (shouldn't happen but safe)
        attention_weights = attention_weights.masked_fill(~mask, 0.0)
        
        # 6. Weighted sum of features
        # [Batch, Time, 1] * [Batch, Time, Features] -> sum -> [Batch, Features]
        attended = torch.sum(attention_weights.unsqueeze(-1) * x, dim=1)
        
        return attended, attention_weights
 
# Convolutional Neural Network with Attention
class FallDetectionCNN(nn.Module):
    def __init__(self, num_features, hidden_size1, hidden_size2, output_size):
        super(FallDetectionCNN, self).__init__()
 
        self.num_features = num_features
        
        # --- 1. Convolutional Blocks ---
        self.conv_block1 = nn.Sequential(
            nn.Conv1d(in_channels=num_features, out_channels=32, kernel_size=21, padding=10),
            nn.BatchNorm1d(32),
            nn.ReLU(),
            nn.Dropout1d(0.3),
            nn.MaxPool1d(kernel_size=2)  # Reduces length by 2
        )
 
        self.conv_block2 = nn.Sequential(
            nn.Conv1d(in_channels=32, out_channels=64, kernel_size=11, padding=5),
            nn.BatchNorm1d(64),
            nn.ReLU(),
            nn.Dropout1d(0.3),
            nn.MaxPool1d(kernel_size=2)  # Reduces length by 2 (Total reduction: /4)
        )
       
        # --- 2. Attention Mechanism ---
        # Learns to focus on important timesteps (e.g., the moment of impact)
        self.attention = TemporalAttention(feature_dim=64)
        
        # --- 3. Global Max Pooling (kept for capturing peak signals) ---
        self.global_max_pool = nn.AdaptiveMaxPool1d(1)
 
        # --- 4. Classifier ---
        # Input: 64 (attention) + 64 (max pool) = 128
        self.fc1 = nn.Linear(64 + 64, hidden_size1)
        self.relu1 = nn.ReLU()
        self.dropout1 = nn.Dropout(0.6)
        
        self.fc2 = nn.Linear(hidden_size1, hidden_size2)
        self.relu2 = nn.ReLU()
        self.dropout2 = nn.Dropout(0.6)
        
        self.fc3 = nn.Linear(hidden_size2, output_size)
 
    def forward(self, x, lengths):
        # x input: [Batch, Time, Features]
        
        # 0. Permute to [Batch, Channels, Time] for Conv1d
        x = x.permute(0, 2, 1) 
        
        # 1. Conv Features
        x = self.conv_block1(x)
        x = self.conv_block2(x)
        # Shape: [Batch, 64, Reduced_Length]
 
        # 2. Global Max Pooling Branch (captures peak impact/velocity)
        x_max = self.global_max_pool(x).squeeze(2)  # [Batch, 64]
 
        # 3. Attention Branch
        # Permute back to [Batch, Time, Features] for attention
        x_for_attn = x.permute(0, 2, 1)  # [Batch, Reduced_Length, 64]
        
        # Adjust lengths for reduced temporal dimension
        reduced_lengths = (lengths // 4).clamp(min=1)
        
        # Apply attention - learns which timesteps matter most
        x_attn, attn_weights = self.attention(x_for_attn, reduced_lengths)  # [Batch, 64]
 
        # 4. Concatenate attention output with max pooling
        x_combined = torch.cat((x_attn, x_max), dim=1)  # [Batch, 128]
 
        # 5. Classifier
        x = self.fc1(x_combined)
        x = self.relu1(x)
        x = self.dropout1(x)
 
        x = self.fc2(x)
        x = self.relu2(x)
        x = self.dropout2(x)
 
        x = self.fc3(x)
        
        return x

def train_single_fold(X_train_list, y_train, X_val_list, y_val, config, verbose=False):

    aug_factor = config.get('augmentation_factor', 0)
    
    augmented_X_train = []
    augmented_y_train = []
    
    for seq, label in zip(X_train_list, y_train):
        augmented_X_train.append(seq)
        augmented_y_train.append(label)
        for _ in range(aug_factor):
            augmented_X_train.append(augment_sequence(seq))
            augmented_y_train.append(label)

    train_ds = variable_length_dataset(augmented_X_train, augmented_y_train)
    
    # Validation should strictly NOT be augmented
    val_ds = variable_length_dataset(X_val_list, y_val)

    train_loader = DataLoader(train_ds, batch_size=config['batch_size'], shuffle=True, collate_fn=collate_fn)
    val_loader = DataLoader(val_ds, batch_size=config['batch_size'], shuffle=False, collate_fn=collate_fn)

    num_features = X_train_list[0].shape[1]
    model = FallDetectionCNN(num_features, config['hidden1'], config['hidden2'], 1)

    num_not_fall = sum(1 for label in y_train if label == 0)
    num_fall = sum(1 for label in y_train if label == 1)
    pos_weight = torch.tensor( 1 , dtype=torch.float32)
    criterion = nn.BCEWithLogitsLoss(pos_weight=pos_weight)

    optimizer = torch.optim.Adam(model.parameters(), lr=config['lr'], weight_decay=config['weight_decay'])
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, mode='min', patience=config['LSpatience'], factor=0.5)
    
    best_val_loss = float('inf')
    patience_counter = 0
    best_model_state = None
    train_loss = []
    val_loss = []
    
    for epoch in range(config['epochs']):
        #train
        epoch_train_loss = 0
        model.train()
        for sequences, labels, lengths in train_loader:
            outputs = model(sequences, lengths)
            loss = criterion(outputs, labels)
            epoch_train_loss += loss.item()
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
        avg_train_loss = epoch_train_loss / len(train_loader)
        train_loss.append(avg_train_loss)
        
        #validate
        model.eval()
        epoch_val_loss = 0
        with torch.no_grad():
            for sequences, labels, lengths in val_loader:
                outputs = model(sequences, lengths)
                loss = criterion(outputs, labels)
                epoch_val_loss += loss.item()
        
        avg_val_loss = epoch_val_loss / len(val_loader)
        val_loss.append(avg_val_loss)
        scheduler.step(avg_val_loss)

        if verbose:
            current_lr = optimizer.param_groups[0]['lr']
            print(f" Epoch {epoch+1}/{config['epochs']} | Train Loss: {avg_train_loss:.4f} | Val Loss: {avg_val_loss:.4f} | LR: {current_lr:.6f}")
        
        if avg_val_loss < best_val_loss:
            best_val_loss = avg_val_loss
            patience_counter = 0
            best_model_state = model.state_dict().copy()
        else:
            patience_counter += 1
        
        if patience_counter >= config['patience']:
            if verbose:
                print(f" Early stopping at epoch {epoch+1}")
            break
    
    #find best model and save it
    if best_model_state is not None:
        model.load_state_dict(best_model_state)
    
    model.eval()
    with torch.no_grad():
        #training acc
        train_preds, train_labels = [], []
        for sequences, labels, lengths in train_loader:
            outputs = model(sequences, lengths)
            predicted = (torch.sigmoid(outputs) > config['threshold']).float()
            train_preds.extend(predicted.numpy())
            train_labels.extend(labels.numpy())
        train_acc = accuracy_score(train_labels, train_preds)
        
        #validation acc
        val_preds, val_labels = [], []
        for sequences, labels, lengths in val_loader:
            outputs = model(sequences, lengths)
            predicted = (torch.sigmoid(outputs) > config['threshold']).float()
            val_preds.extend(predicted.numpy())
            val_labels.extend(labels.numpy())
        val_acc = accuracy_score(val_labels, val_preds)
        val_cm = confusion_matrix(val_labels, val_preds)
    
    return {
        'train_acc': train_acc,
        'val_acc': val_acc,
        'val_loss': best_val_loss,
        'all_train_loss': train_loss,
        'all_val_loss': val_loss,
        'confusion_matrix': val_cm,
        'model_state': best_model_state,
        'model': model
    }