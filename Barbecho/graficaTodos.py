import os
import ast
import numpy as np
import matplotlib.pyplot as plt
from scipy.stats import wasserstein_distance
from scipy.spatial.distance import jensenshannon
import math


#ARCHIVO PARA SACAR EL GRÁFICO DE BARRAS DE CUALQUIER CIRCUITO QUE SE DESEE EN LA CARPETA resultadosTodos

BASE_DIR = "resultadosTodos"
BATCH_DIR = os.path.join(BASE_DIR, "resultadosIBM_505_batch")
#BATCH_DIR = os.path.join(BASE_DIR, "resultadosIBM_grafica_todos")
INDIVIDUAL_FILE = os.path.join(BASE_DIR, "resultadosIBM_individuales", "circuits-code-time-individual.txt")
NORMALIZAR_INDIVIDUAL_A = 1000

# ===========================
# Funciones auxiliares
# ===========================

def hellinger(p, q):
    return math.sqrt(sum((math.sqrt(p_i) - math.sqrt(q_i))**2 for p_i, q_i in zip(p, q)) / 2)

def wasserstein(p, q):
    return wasserstein_distance(p, q)

def jensen_shannon_divergence(p, q):
    return jensenshannon(p, q) ** 2

def total_variation_distance(p, q):
    return 0.5 * sum(abs(p_i - q_i) for p_i, q_i in zip(p, q))

def add_missing_keys(d1, d2):
    all_keys = set(d1.keys()) | set(d2.keys())
    d1_full = {k: d1.get(k, 0) for k in sorted(all_keys)}
    d2_full = {k: d2.get(k, 0) for k in sorted(all_keys)}
    return d1_full, d2_full

def dict_to_prob(d):
    total = sum(d.values())
    if total == 0:
        return [0]*len(d)
    return [v / total for v in d.values()]

def normalize_dict(d, target_total=NORMALIZAR_INDIVIDUAL_A):
    total = sum(d.values())
    if total == 0:
        return d
    factor = target_total / total
    return {k: v * factor for k, v in d.items()}

# ===========================
# Cargar individual
# ===========================
# ===========================
# Cargar individual
# ===========================
def load_individual(circuit_name):
    circuit_name_clean = circuit_name.strip().lower()
    with open(INDIVIDUAL_FILE, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            try:
                data = ast.literal_eval(line.strip())
                individual_name = str(data.get("circuit","")).strip().lower()
                if individual_name == circuit_name_clean:
                    d = data.get("value", {})
                    return normalize_dict(d)
            except:
                continue
    return None




# ===========================
# Cargar resultados batch
# ===========================
def load_batch(circuit_name):
    circuit_folder = os.path.join(BATCH_DIR, circuit_name.replace(".py",""))
    if not os.path.isdir(circuit_folder):
        return {}
    batches = {}
    for file in os.listdir(circuit_folder):
        if file.startswith("result_") and file.endswith(".txt"):
            try:
                num = int(file.split("_")[1].split(".")[0])
            except:
                continue
            path = os.path.join(circuit_folder, file)
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                line = f.readline().strip()
                try:
                    data = ast.literal_eval(line)
                    batches[num] = data
                except:
                    continue
    return dict(sorted(batches.items()))

# ===========================
# Calcular distancias y medias
# ===========================
def compute_means(individual, batches):
    batches_all = {0: individual}
    batches_all.update(batches)
    baseline = batches_all[0]
    batches_all.pop(0)
    distances = {"Hellinger": [], "Wasserstein": [], "Jensen-Shannon": [], "Total Variation": []}
    for b in batches_all.values():
        d1, d2 = add_missing_keys(b, baseline)
        p, q = dict_to_prob(d1), dict_to_prob(d2)
        distances["Hellinger"].append(hellinger(p,q))
        distances["Wasserstein"].append(wasserstein(p,q))
        distances["Jensen-Shannon"].append(jensen_shannon_divergence(p,q))
        distances["Total Variation"].append(total_variation_distance(p,q))
    means = {k: np.mean(v) for k,v in distances.items()}
    return means

# ===========================
# MAIN
# ===========================
if __name__ == "__main__":
    # Primero extraemos todos los circuitos del archivo individual
    circuits = []
    with open(INDIVIDUAL_FILE, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            try:
                data = ast.literal_eval(line.strip())
                circuits.append(data["circuit"])
            except:
                continue

    all_means = {}
    for c in circuits:
        individual = load_individual(c)
        if individual is None:
            # Simplemente saltar sin advertencia
            continue
        batches = load_batch(c)
        if not batches:
            continue
        means = compute_means(individual, batches)
        all_means[c] = means
        print(f"Procesado circuito: {c}")
        print(f"Medias: {means}")

    # ===========================
    # Gráfico de barras
    # ===========================
    if all_means:
        labels = list(all_means.keys())
        metrics = ["Hellinger","Wasserstein","Jensen-Shannon","Total Variation"]
        colors = {
            "Hellinger": "#477b9d",
            "Wasserstein": "#f4b054",
            "Jensen-Shannon": "#9d4748", 
            "Total Variation": "#94ab91"
        }

        x = np.arange(len(labels))
        width = 0.2

        plt.figure(figsize=(12,6))
        for i, metric in enumerate(metrics):
            values = [all_means[c][metric] for c in labels]
            plt.bar(x + i*width, values, width=width, label=metric, color=colors[metric])

        plt.ylabel("Mean Distance", fontsize=16)
        plt.xticks(x + width*1.5, labels, rotation=45, ha='right', fontsize=14)
        plt.yticks(fontsize=14)
        plt.legend(fontsize=14)
        plt.grid(axis='y', linestyle='--', alpha=0.4)
        plt.tight_layout()

        os.makedirs("plot", exist_ok=True)
        save_path = "plot/medias_todos_circuitos.png"
        plt.savefig(save_path, dpi=300)
        print(f"\n[✅] Gráfico de medias guardado en: {save_path}")
        plt.show()