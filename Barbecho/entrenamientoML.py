import itertools
import torch
import torch.nn as nn
import torch.optim as optim
import numpy as np
import random
import string
from queue import PriorityQueue
import os


CARPETA_SALIDAS = os.path.join("Scheduler-Horizontal", "QCRAFT-Scheduler", "salidas")
MODEL_PATH = os.path.join(CARPETA_SALIDAS, "knapsack_model_improved.pth")

def knapsack_dp(values, capacity):
    n = len(values)
    dp = [[0] * (capacity + 1) for _ in range(n + 1)]
    keep = [[0] * (capacity + 1) for _ in range(n + 1)]

    for i in range(1, n + 1):
        for w in range(capacity + 1):
            if values[i-1] <= w:
                if dp[i-1][w - values[i-1]] + values[i-1] > dp[i-1][w]:
                    dp[i][w] = dp[i-1][w - values[i-1]] + values[i-1]
                    keep[i][w] = 1
                else:
                    dp[i][w] = dp[i-1][w]
            else:
                dp[i][w] = dp[i-1][w]

    res = []
    w = capacity
    for i in range(n, 0, -1):
        if keep[i][w]:
            res.append(i-1)
            w -= values[i-1]
    return res

def generate_training_data(max_items=2000, samples=2000):
    training_data = []
    labels = []

    for _ in range(samples):
        num_items = random.randint(100, max_items)
        items = np.random.randint(1, 20, size=num_items)
        capacity = 156

        best_comb = knapsack_dp(items.tolist(), capacity)
        
        # Asegurarnos de que la solución sea óptima
        total = sum(items[i] for i in best_comb)
        if total < capacity:
            # Intentar mejorar la solución si no alcanza la capacidad máxima
            remaining = capacity - total
            for i in range(num_items):
                if i not in best_comb and items[i] <= remaining:
                    best_comb.append(i)
                    remaining -= items[i]
                    if remaining == 0:
                        break

        binary_labels = np.zeros(max_items)
        for idx in best_comb:
            binary_labels[idx] = 1

        padded_items = np.pad(items, (0, max_items - len(items)), 'constant')
        training_data.append(padded_items)
        labels.append(binary_labels)

    return np.array(training_data, dtype=np.float32), np.array(labels, dtype=np.float32)

class ImprovedKnapsackNN(nn.Module):
    def __init__(self, input_size=2000):
        super(ImprovedKnapsackNN, self).__init__()
        self.fc1 = nn.Linear(input_size, 2048)
        self.bn1 = nn.BatchNorm1d(2048)
        self.fc2 = nn.Linear(2048, 1024)
        self.bn2 = nn.BatchNorm1d(1024)
        self.fc3 = nn.Linear(1024, 512)
        self.bn3 = nn.BatchNorm1d(512)
        self.fc4 = nn.Linear(512, input_size)
        self.dropout = nn.Dropout(0.4)
        self.sigmoid = nn.Sigmoid()

    def forward(self, x):
        x = torch.relu(self.bn1(self.fc1(x)))
        x = self.dropout(x)
        x = torch.relu(self.bn2(self.fc2(x)))
        x = self.dropout(x)
        x = torch.relu(self.bn3(self.fc3(x)))
        x = self.dropout(x)
        x = self.sigmoid(self.fc4(x))
        return x

def train_model(input_size=2000):
    model = ImprovedKnapsackNN(input_size)
    criterion = nn.BCELoss()
    optimizer = optim.Adam(model.parameters(), lr=0.0005, weight_decay=1e-5)
    scheduler = optim.lr_scheduler.ReduceLROnPlateau(optimizer, 'min', patience=2, factor=0.5)

    X_train, y_train = generate_training_data(max_items=input_size, samples=3000)
    X_train = torch.tensor(X_train)
    y_train = torch.tensor(y_train)

    best_loss = float('inf')
    for epoch in range(30):
        model.train()
        optimizer.zero_grad()
        outputs = model(X_train)
        loss = criterion(outputs, y_train)
        loss.backward()
        optimizer.step()
        scheduler.step(loss)
        
        # Validación
        model.eval()
        with torch.no_grad():
            val_outputs = model(X_train[:500])  # Usamos un subconjunto para validación
            val_loss = criterion(val_outputs, y_train[:500])
        
        print(f"Epoch {epoch+1}/30 - Train Loss: {loss.item():.4f} - Val Loss: {val_loss.item():.4f}")
        
        if val_loss.item() < best_loss:
            best_loss = val_loss.item()
            torch.save(model.state_dict(), MODEL_PATH)

    return model

def load_model(path=MODEL_PATH, input_size=2000):
    model = ImprovedKnapsackNN(input_size)
    if os.path.exists(path):
        model.load_state_dict(torch.load(path))
        model.eval()
    else:
        print("⚠ No se encontró el modelo, entrenando uno nuevo...")
        model = train_model(input_size)
    return model