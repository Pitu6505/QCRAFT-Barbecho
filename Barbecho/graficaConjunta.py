import os
import ast
import numpy as np
import matplotlib.pyplot as plt
from scipy.stats import wasserstein_distance
from scipy.spatial.distance import jensenshannon
import math
from matplotlib.ticker import FuncFormatter
import matplotlib.patches as mpatches
import matplotlib.lines as mlines

#ARCHIVO PARA COMPARAR LAS GRÁFICAS DE PHASE ESTIMATION AUTOESCHEDULER CON PHASE ESTIMATION CON TODOS

##################################
# CONFIGURACIÓN
##################################

SALIDA_BIN_PATH = "resultadosPhaseEstimation/resultadosIBM_495_batch/salidaBin.txt"
RESULTADOS_BATCH_DIR = "resultadosTodos/resultadosIBM_505_batch/phase_estimation_qcraft"

BLOCK_SIZE = 4       # cantidad de bits por bloque
STEP_SIZE = 132      # salto entre bloques

##################################
# FUNCIONES AUXILIARES
##################################

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

##################################
# PARSEO DE salidaBin.txt sin invertir
##################################

def parse_salida_bin(path):
    """Lee los bits del archivo y genera un conteo de bloques de 4 bits cada 133 posiciones desde el final (sin invertir nada)."""
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        text = f.read()

    # Extraer solo los bits antes del ':'
    bits = ""
    for line in text.splitlines():
        if "':" in line:
            part = line.split("':")[0].strip().replace("'", "")
            bits += part

    # Procesar desde el final sin invertir la cadena
    counts = {}
    i = len(bits) - BLOCK_SIZE
    while i >= 0:
        block = bits[i:i + BLOCK_SIZE]  # toma los bits tal cual
        counts[block] = counts.get(block, 0) + 1
        i -= STEP_SIZE  # retrocede 133 posiciones

    print("\n=== CONTEO DE BLOQUES (4 bits cada 133 desde el final) ===\n")
    print(counts)
    print(f"\nSuma total: {sum(counts.values())}\n")

    return counts

##################################
# CARGA DE RESULTADOS result_X.txt
##################################

def load_batch_results(batch_dir):
    """Carga todos los result_X.txt en orden numérico."""
    batches = {}
    for file in sorted(os.listdir(batch_dir)):
        if not file.startswith("result_") or not file.endswith(".txt"):
            continue
        try:
            num = int(file.split("_")[1].split(".")[0])
        except:
            continue
        path = os.path.join(batch_dir, file)
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            line = f.readline().strip()
        try:
            data = ast.literal_eval(line)
            batches[num] = data
            print(f"[INFO] Cargado {file} con {len(data)} claves.")
        except Exception as e:
            print(f"[ERROR] en {file}: {e}")
    return dict(sorted(batches.items()))

##################################
# CÁLCULO DE DISTANCIAS
##################################

def compute_distances(reference, batches):
    distances = {"Hellinger": [], "Wasserstein": [], "Jensen-Shannon": [], "Total Variation": []}
    x = []
    for num, data in batches.items():
        d1, d2 = add_missing_keys(data, reference)
        p, q = dict_to_prob(d1), dict_to_prob(d2)
        distances["Hellinger"].append(hellinger(p, q))
        distances["Wasserstein"].append(wasserstein(p, q))
        distances["Jensen-Shannon"].append(jensen_shannon_divergence(p, q))
        distances["Total Variation"].append(total_variation_distance(p, q))
        x.append(num)
    return x, distances

##################################
# ESCALA COMPRIMIDA
##################################

def compress_y(y):
    y = np.array(y)
    return np.where(y <= 0.5, y, 0.5 + (y - 0.5)/4)

def decompress_y(y_scaled):
    y_scaled = np.array(y_scaled)
    return np.where(y_scaled <= 0.5, y_scaled, 0.5 + (y_scaled - 0.5)*4)

##################################
# GRAFICADO
##################################

def plot_distances(x, distances):
    plt.figure(figsize=(12, 6))

    colors = {
        "Wasserstein": "#f4b054",
        "Jensen-Shannon": "#9d4748"
    }

    metrics_to_plot = ["Wasserstein", "Jensen-Shannon"]

    # =======================
    # Dibujar curvas y líneas de media
    # =======================
    lines = []
    for k in metrics_to_plot:
        v = distances[k]
        v_compressed = compress_y(np.array(v))
        plt.plot(x, v_compressed, marker='o', label=k, color=colors[k])
        # Línea de media
        mean_val = np.mean(v)
        line = plt.axhline(compress_y(mean_val), color=colors[k], linestyle='--', alpha=0.8, zorder=5)
        lines.append(line)

    # =======================
    # Configuración de ejes
    # =======================
    plt.ylim(0, compress_y(1))
    plt.xlabel("Batch", fontsize=16)
    plt.ylabel("Distance", fontsize=16)
    plt.tick_params(axis='x', labelsize=14)
    plt.tick_params(axis='y', labelsize=14)

    yticks_real = np.concatenate((np.arange(0, 0.6, 0.1), [1.0]))
    plt.yticks(compress_y(yticks_real))
    plt.gca().yaxis.set_major_formatter(FuncFormatter(lambda val, _: f"{decompress_y(val):.1f}"))

    # =======================
    # Líneas diagonales para romper eje
    # =======================
    ax = plt.gca()
    y_positions = [compress_y(0.7), compress_y(0.8)]
    for y_pos in y_positions:
        ax.plot([-0.015, 0.015], [y_pos-0.005, y_pos+0.005], transform=ax.get_yaxis_transform(),
                color='k', lw=1.5, clip_on=False)

    # =======================
    # Leyenda personalizada en orden Wasser, Mean Wasser, Jensen, Mean Jensen
    # =======================
    legend_handles = [
        mpatches.Patch(color=colors["Wasserstein"], label="Wasserstein"),
        mlines.Line2D([], [], color=colors["Wasserstein"], linestyle='--', label="Mean Wasserstein"),
        mpatches.Patch(color=colors["Jensen-Shannon"], label="Jensen-Shannon"),
        mlines.Line2D([], [], color=colors["Jensen-Shannon"], linestyle='--', label="Mean Jensen-Shannon"),
    ]
    plt.legend(handles=legend_handles, fontsize=14, loc='best')

    # Cuadrícula y layout
    plt.grid(True, linestyle='--', alpha=0.4)
    plt.tight_layout()

    # Guardar gráfico
    os.makedirs("plot", exist_ok=True)
    save_path = "plot/distancias_phase_estimation_wasser_jensen.png"
    plt.savefig(save_path, dpi=300)
    print(f"[✅] Graph saved in: {save_path}")

    plt.show()

##################################
# MAIN
##################################

if __name__ == "__main__":
    print("\n🔍 Procesando salidaBin.txt y comparando con TODOS los batches...\n")

    ref = parse_salida_bin(SALIDA_BIN_PATH)
    batches = load_batch_results(RESULTADOS_BATCH_DIR)

    if not batches:
        print("[ERROR] No hay resultados en el batch folder.")
        exit(1)

    x, distances = compute_distances(ref, batches)

    print("\n=== MEDIAS DE DISTANCIAS ===\n")
    for k in ["Wasserstein", "Jensen-Shannon"]:
        print(f"{k:15s}: {np.mean(distances[k]):.5f}")

    plot_distances(x, distances)
