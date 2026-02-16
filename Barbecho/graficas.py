import os
import ast
import numpy as np
import matplotlib.pyplot as plt
from scipy.stats import wasserstein_distance
from scipy.spatial.distance import jensenshannon
import math
from matplotlib.ticker import FuncFormatter


#ARCHIVO PARA SACAR LAS GRAFICAS DE CUALQUIER CIRCUITO QUE SE DESEE EN LA CARPETA resultadosTodos

##################################
# CONFIGURACIÓN PRINCIPAL
##################################

# 🔧 Circuito a comparar (nombre EXACTO como aparece en los ficheros)
CIRCUITO_OBJETIVO = "phase_estimation_qcraft.py"

# Carpeta raíz
BASE_DIR = "resultadosTodos"

# Solo se normaliza el individual
NORMALIZAR_INDIVIDUAL_A = 1000


##################################
# FUNCIONES AUXILIARES
##################################

def hellinger(p, q):
    return math.sqrt(sum((math.sqrt(p_i) - math.sqrt(q_i))**2 for p_i, q_i in zip(p, q)) / 2)

def wasserstein(p, q):
    return wasserstein_distance(p, q)

def jensen_shannon_divergence(p, q):
    return jensenshannon(p, q) ** 2

def quantum_fidelity(p, q):
    p = np.array(p)
    q = np.array(q)
    return np.sum(np.sqrt(p * q))

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
    return [count / total for count in d.values()]

def normalize_dict(d, target_total=NORMALIZAR_INDIVIDUAL_A):
    total = sum(d.values())
    if total == 0:
        return d
    factor = target_total / total
    return {k: v * factor for k, v in d.items()}


##################################
# CARGA DE DATOS
##################################

def load_individual_circuit(base_dir, circuito):
    """Carga el circuito individual desde circuits-code-time-individual.txt"""
    file_path = os.path.join(base_dir, "resultadosIBM_individuales", "circuits-code-time-individual.txt")
    if not os.path.exists(file_path):
        print(f"[ERROR] No se encontró el archivo individual: {file_path}")
        return None

    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if f'"circuit": "{circuito}"' in line:
                try:
                    data = ast.literal_eval(line.strip())
                    d = data.get("value", {})
                    d = normalize_dict(d, target_total=NORMALIZAR_INDIVIDUAL_A)
                    print(f"[INFO] Circuito individual cargado correctamente ({circuito}) con {len(d)} claves.")
                    return d
                except Exception as e:
                    print(f"[ERROR] Al parsear circuito individual: {e}")
                    return None

    print(f"[ADVERTENCIA] No se encontró el circuito {circuito} en el archivo individual.")
    return None


def load_batch6_circuit(base_dir, circuito):
    """Carga los resultados del circuito en la carpeta resultadosIBM_506_batch"""
    batch_folder = os.path.join(base_dir, "resultadosIBM_505_batch")
    if not os.path.isdir(batch_folder):
        print("[ERROR] No existe la carpeta resultadosIBM_6_batch.")
        return {}

    circuit_folder = os.path.join(batch_folder, circuito.replace(".py", ""))
    if not os.path.isdir(circuit_folder):
        print(f"[ADVERTENCIA] No existe carpeta para el circuito {circuito} en batch 6.")
        return {}

    batches = {}
    result_files = [f for f in os.listdir(circuit_folder) if f.startswith("result_") and f.endswith(".txt")]
    for file in result_files:
        try:
            result_num = int(file.split("_")[1].split(".")[0])
        except:
            continue

        file_path = os.path.join(circuit_folder, file)
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.read().splitlines()

        if not lines:
            continue

        try:
            # solo la primera línea contiene el diccionario real
            data_line = lines[0].strip()
            if data_line.startswith("{") or data_line.startswith("{'"):
                data = ast.literal_eval(data_line)
                batches[result_num] = data  # ⚠️ sin normalizar
                print(f"[INFO] Cargado result_{result_num} del circuito '{circuito}' en batch 6 ({len(data)} claves).")
            else:
                print(f"[ADVERTENCIA] Formato inesperado en {file_path}")
        except Exception as e:
            print(f"[ERROR] Al parsear {file_path}: {e}")
            continue

    return dict(sorted(batches.items()))


##################################
# CÁLCULO DE DISTANCIAS
##################################

##################################
# CÁLCULO DE DISTANCIAS (AJUSTADO)
##################################

def compute_distances(batches):
    baseline = batches[0]
    batches.pop(0)  # eliminar individual para solo tener batches
    batch_nums = sorted(batches.keys())  # incluir 0 también
    print(batches.keys())
    distances = {"Hellinger": [], "Wasserstein": [], "Jensen-Shannon": [], "Total Variation": []}  # sin Quantum Fidelity
    x = []

    for b in batch_nums:
        d1, d2 = add_missing_keys(batches[b], baseline)
        p, q = dict_to_prob(d1), dict_to_prob(d2)

        # Para el batch 0 (individual), calculamos la distancia real con algo de "ruido" si quieres
        # Aquí simplemente usamos la misma probabilidad vs probabilidad (puedes añadir ruido si quieres)
        distances["Hellinger"].append(hellinger(p, q))
        distances["Wasserstein"].append(wasserstein(p, q))
        distances["Jensen-Shannon"].append(jensen_shannon_divergence(p, q))
        distances["Total Variation"].append(total_variation_distance(p, q))
        x.append(b)

    return x, distances


##################################
# GRAFICADO (AJUSTADO)
##################################

# def plot_distances(circuit_name, x, distances):
#     plt.figure(figsize=(12,6))

#     colors = {
#         "Hellinger": "#477b9d",
#         "Wasserstein": "#f4b054",
#         "Jensen-Shannon": "#9d4748",
#         "Total Variation": "#94ab91"
#     }

#     # Pinta las líneas con colores fijos
#     for k, v in distances.items():
#         plt.plot(x, v, marker='o', label=k, color=colors[k])

#     # Ejes en inglés con etiquetas más grandes
#     plt.xlabel("Batch", fontsize=16)     
#     plt.ylabel("Distance", fontsize=16)  

#     # Tamaño de los números del eje X e Y
#     plt.tick_params(axis='x', labelsize=14)
#     plt.tick_params(axis='y', labelsize=14)

#     # Leyenda con fuente más grande
#     plt.legend(fontsize=14)

#     # Cuadrícula
#     plt.grid(True, linestyle='--', alpha=0.4)
#     plt.tight_layout()

#     # Guardar gráfico
#     os.makedirs("plot", exist_ok=True)
#     save_path = f"plot/distancias_batch6_{circuit_name.replace('.py','')}.png"
#     plt.savefig(save_path, dpi=300)
#     print(f"[✅] Gráfica guardada en: {save_path}")

#     plt.show()

def plot_distances(circuit_name, x, distances):
  

    colors = {
        "Hellinger": "#477b9d",
        "Wasserstein": "#f4b054", 
        "Jensen-Shannon": "#9d4748",
        "Total Variation": "#94ab91"
    }

    plt.figure(figsize=(12, 6))

    # =======================
    # ESCALA COMPRIMIDA
    # =======================
    def compress_y(y):
        y = np.array(y)
        return np.where(y <= 0.5, y, 0.5 + (y - 0.5)/4)

    def decompress_y(y_scaled):
        y_scaled = np.array(y_scaled)
        return np.where(y_scaled <= 0.5, y_scaled, 0.5 + (y_scaled - 0.5)*4)

    # =======================
    # DIBUJAR CURVAS
    # =======================
    for k in ["Wasserstein", "Jensen-Shannon"]:
        v = np.array(distances[k])
        plt.plot(x, compress_y(v), marker='o', label=k, color=colors[k])
        mean_val = np.mean(v)
        plt.axhline(compress_y(mean_val), color=colors[k], linestyle='--', alpha=0.6,
                    label=f"Mean {k}")

    # =======================
    # CONFIGURACIÓN DEL EJE Y
    # =======================
    plt.ylim(0, compress_y(1))
    plt.xlabel("Batch", fontsize=16)
    plt.ylabel("Distance", fontsize=16)

    yticks_real = np.concatenate((np.arange(0, 0.6, 0.1), [1.0]))
    plt.yticks(compress_y(yticks_real))
    plt.gca().yaxis.set_major_formatter(FuncFormatter(lambda val, _: f"{decompress_y(val):.1f}"))

    # =======================
    # LÍNEAS DE CORTE DIAGONALES Y MÁS JUNTAS
    # =======================
    ax = plt.gca()
    
    # Posiciones más juntas en el eje Y (escala comprimida)
    y_positions = [compress_y(0.7), compress_y(0.8)]
    
    # Dibujar líneas diagonales en el eje Y
    for y_pos in y_positions:
        # Líneas diagonales (de abajo-izquierda a arriba-derecha)
        ax.plot([-0.015, 0.015], [y_pos-0.005, y_pos+0.005], transform=ax.get_yaxis_transform(), 
                color='k', lw=1.5, clip_on=False)

    # =======================
    # LEYENDA Y ESTILO
    # =======================
    plt.legend(fontsize=14)
    plt.grid(True, linestyle='--', alpha=0.4)
    plt.tight_layout()

    os.makedirs("plot", exist_ok=True)
    save_path = f"plot/distancias_batch6_{circuit_name.replace('.py','')}.png"
    plt.savefig(save_path, dpi=300)
    print(f"[✅] Gráfica guardada en: {save_path}")
    plt.show()







##################################
# IMPRESIÓN DE RESULTADOS (AJUSTADO)
##################################

def print_results(x, distances):
    print("\n=== RESULTADOS NUMÉRICOS ===\n")
    print("Batch | Hellinger | Wasserstein | Jensen-Shannon | Total Variation")
    print("-"*75)
    for i, b in enumerate(x):
        print(f"{b:5d} | {distances['Hellinger'][i]:10.5f} | "
              f"{distances['Wasserstein'][i]:12.5f} | "
              f"{distances['Jensen-Shannon'][i]:14.5f} | "
              f"{distances['Total Variation'][i]:16.5f}")



##################################
# GRAFICADO
##################################

# def plot_distances(circuit_name, x, distances):
#     plt.figure(figsize=(12,6))

#     # Pinta las líneas
#     for k, v in distances.items():
#         plt.plot(x, v, marker='o', label=k)

#     # Marca explícitamente el batch 0 (individual)
#     plt.axvline(x=0, color='gray', linestyle='--', linewidth=1)
#     plt.scatter(0, 0, color='red', s=80, label="Individual (Batch 0)")

#     plt.xlabel("Batch")
#     plt.ylabel("Distance")
#     plt.title(f"Comparación Individual vs Batch 6 — {circuit_name}")
#     plt.legend()
#     plt.grid(True, linestyle='--', alpha=0.4)
#     plt.tight_layout()

#     os.makedirs("plot", exist_ok=True)
#     save_path = f"plot/distancias_batch6_{circuit_name.replace('.py','')}.png"
#     plt.savefig(save_path, dpi=300)
#     print(f"[✅] Gráfica guardada en: {save_path}")
#     plt.show()


##################################
# MAIN
##################################

if __name__ == "__main__":
    print(f"\n🔍 Comparando circuito: {CIRCUITO_OBJETIVO} (individual vs batch 6)\n")

    individual = load_individual_circuit(BASE_DIR, CIRCUITO_OBJETIVO)
    if individual is None:
        exit(1)

    batch6 = load_batch6_circuit(BASE_DIR, CIRCUITO_OBJETIVO)
    if not batch6:
        print("[ERROR] No hay resultados para batch 6.")
        exit(1)

    # Unir ambos (batch 0 = individual)
    batches = {0: individual}
    batches.update(batch6)

    # =======================
    # CALCULAR DISTANCIAS
    # =======================
    x, distances = compute_distances(batches)

    # =======================
    # CALCULAR MEDIAS ANTES DE LA GRAFICA
    # =======================
    print("\n=== MEDIAS DE DISTANCIAS ===\n")
    for k, v in distances.items():
        mean_val = np.mean(v)
        print(f"{k:15s}: {mean_val:.5f}")

    # =======================
    # GRAFICAR
    # =======================
    plot_distances(CIRCUITO_OBJETIVO, x, distances)

    # =======================
    # IMPRIMIR RESULTADOS NUMÉRICOS
    # =======================
    print("\n=== RESULTADOS NUMÉRICOS ===\n")
    print("Batch | Hellinger | Wasserstein | Jensen-Shannon | Total Variation")
    print("-"*75)
    for i, b in enumerate(x):
        print(f"{b:5d} | {distances['Hellinger'][i]:10.5f} | "
              f"{distances['Wasserstein'][i]:12.5f} | "
              f"{distances['Jensen-Shannon'][i]:14.5f} | "
              f"{distances['Total Variation'][i]:16.5f}")

              #f"{distances['Quantum Fidelity'][i]:17.5f}")
    
