import os
import ast
import numpy as np
import matplotlib.pyplot as plt
from scipy.stats import wasserstein_distance
from scipy.spatial.distance import jensenshannon
import math
from matplotlib.ticker import FuncFormatter

#ARCHIVO PARA SACAR EL GRÁFICO DE BARRAS DE CUALQUIER CIRCUITO QUE SE DESEE EN LA CARPETA resultadosTodos ALGUNOS CIRCUITOS SELECCIONADOS EN CONCRETO

BASE_DIR = "resultadosTodos"
#BATCH_DIR = os.path.join(BASE_DIR, "resultadosIBM_505_batch")
BATCH_DIR = os.path.join(BASE_DIR, "resultadosIBM_grafica_todos")
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
# ESCALA COMPRIMIDA
# ===========================
def compress_y(y):
    y = np.array(y)
    return np.where(y <= 0.5, y, 0.5 + (y - 0.5)/4)

def decompress_y(y_scaled):
    y_scaled = np.array(y_scaled)
    return np.where(y_scaled <= 0.5, y_scaled, 0.5 + (y_scaled - 0.5)*4)

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
    distances = {"Wasserstein": [], "Jensen-Shannon": []}  # Solo estas dos
    for b in batches_all.values():
        d1, d2 = add_missing_keys(b, baseline)
        p, q = dict_to_prob(d1), dict_to_prob(d2)
        distances["Wasserstein"].append(wasserstein(p,q))
        distances["Jensen-Shannon"].append(jensen_shannon_divergence(p,q))
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
            continue
        batches = load_batch(c)
        if not batches:
            continue
        means = compute_means(individual, batches)
        all_means[c] = means
        print(f"Procesado circuito: {c}")
        print(f"Medias: {means}")

    # ===========================
    # Calcular media global
    # ===========================
    if all_means:
        metrics = ["Wasserstein", "Jensen-Shannon"]  # Solo estas dos

        global_means = {}
        for metric in metrics:
            values = [all_means[c][metric] for c in all_means]
            global_means[metric] = np.mean(values)

        print("\n📊 MEDIA GLOBAL DE TODA LA GRÁFICA:")
        for metric, value in global_means.items():
            print(f"   {metric}: {value:.6f}")

    # ===========================
    # Gráfico de barras
    # ===========================
    if all_means:
        labels = list(all_means.keys())

        # Mapeo de nombres originales -> nombres personalizados
        label_mapping = {
            "20qbt_4cyc_8gn_1.0p2_0_vq.py": "Combinational Mapping",
            "dj_indep_4_mqt.py": "Deutsch-Jozsa",
            "adder_n4_vq.py": "Adder", 
            "bv_3_vq.py": "Bernstein-Vazirani",
            "grover_3_vq.py": "Grover",
            "kickback_7_vq.py": "Kickback",
            "phase_estimation_qcraft.py": "Phase Estimation",
            "qft_3_vq.py": "QFT",
            "shor_mod15_mqt.py": "Shor",
            "simon_qcraft.py": "Simon",
            "tsp_indep_4_mqt.py": "TSP",
            "reversible_5_adder_vq.py": "Reversible",
            "su2random_4_mqt.py": "Sudorandom",
            "qaoa_indep_4_mqt.py": "QAOA",
            "qwalk-v-chain_3_mqt.py": "QWalk"
        }

        # Crear etiquetas reemplazadas
        labels_mapped = [label_mapping.get(l.lower(), l) for l in labels]

        metrics = ["Wasserstein", "Jensen-Shannon"]  # Solo estas dos
        colors = {
            "Wasserstein": "#f4b054",
            "Jensen-Shannon": "#9d4748"
        }

        x = np.arange(len(labels))
        width = 0.35  # Un poco más ancho al tener solo 2 métricas

        plt.figure(figsize=(14, 7))
        
        # Aplicar escala comprimida a los valores
        for i, metric in enumerate(metrics):
            values = [compress_y(all_means[c][metric]) for c in labels]
            plt.bar(x + i*width, values, width=width, label=metric, color=colors[metric])

        # =======================
        # LÍNEAS DE MEDIA GLOBAL (CON LEYENDA)
        # =======================
        for i, metric in enumerate(metrics):
            mean_global = compress_y(global_means[metric])
            plt.axhline(
                y=mean_global, 
                color=colors[metric], 
                linestyle='--', 
                alpha=0.8, 
                label=f"Mean {metric}",  # etiqueta que aparecerá en la leyenda
                zorder=5
            )


        # =======================
        # CONFIGURACIÓN DEL EJE Y
        # =======================
        plt.ylim(0, compress_y(1))
        plt.ylabel("Mean Distance", fontsize=16)
        
        # Configurar ticks del eje Y con escala comprimida
        yticks_real = np.concatenate((np.arange(0, 0.6, 0.1), [1.0]))
        plt.yticks(compress_y(yticks_real))
        plt.gca().yaxis.set_major_formatter(FuncFormatter(lambda val, _: f"{decompress_y(val):.1f}"))

        plt.xticks(x + width/2, labels_mapped, rotation=45, ha='right', fontsize=14)
        plt.yticks(fontsize=14)
        
        # =======================
        # LEYENDA SIMPLE Y ORDENADA
        # =======================
        plt.legend(fontsize=14, loc='best')
        
        plt.grid(axis='y', linestyle='--', alpha=0.4)

        # =======================
        # LÍNEAS DE CORTE DIAGONALES
        # =======================
        ax = plt.gca()
        
        # Posiciones más juntas en el eje Y (escala comprimida)
        y_positions = [compress_y(0.7), compress_y(0.8)]
        
        # Dibujar líneas diagonales en el eje Y
        for y_pos in y_positions:
            # Líneas diagonales (de abajo-izquierda a arriba-derecha)
            ax.plot([-0.015, 0.015], [y_pos-0.005, y_pos+0.005], transform=ax.get_yaxis_transform(), 
                    color='k', lw=1.5, clip_on=False)

        plt.tight_layout()

        os.makedirs("plot", exist_ok=True)
        save_path = "plot/medias_todos_circuitos.png"
        plt.savefig(save_path, dpi=300)
        print(f"\n[✅] Gráfico de medias guardado en: {save_path}")
        plt.show()