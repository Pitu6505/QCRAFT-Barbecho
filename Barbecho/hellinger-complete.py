import os
import json
import ast
import numpy as np
import matplotlib.pyplot as plt
from scipy.stats import wasserstein_distance
from scipy.spatial.distance import jensenshannon
import math

#######################
# FUNCIONES AUXILIARES
#######################

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
    for key in d1.keys():
        if key not in d2:
            d2[key] = 0
    for key in d2.keys():
        if key not in d1:
            d1[key] = 0
    d1 = dict(sorted(d1.items()))
    d2 = dict(sorted(d2.items()))
    return d1, d2

def dict_to_prob(d):
    total = sum(d.values())
    if total == 0:
        return [0]*len(d)
    return [count / total for count in d.values()]

#######################
# CARGA DE LOS TXT
#######################

def load_result_txt(path, circuit_name, normalize=False, target_total=33000):
    """Lee un txt de resultados y devuelve en formato {'circuit': name, 'value': {...}}.
       Si normalize=True, normaliza los conteos para que sumen target_total.
    """
    with open(path, "r") as f:
        lines = f.read().splitlines()
    result_dict = ast.literal_eval(lines[0].strip())

    if normalize:
        total = sum(result_dict.values())
        if total > 0:
            factor = target_total / total
            result_dict = {k: int(round(v * factor)) for k, v in result_dict.items()}
            print(f"[INFO] Normalizado {circuit_name}: suma {sum(result_dict.values())} (antes {total})")

    return {"circuit": circuit_name, "value": result_dict}

##########################
# CÁLCULO DE DISTANCIAS
##########################

def compute_distances(policy_data, baseline_data):
    hellinger_list = []
    wasserstein_list = []
    jensen_list = []
    tv_distance_list = []
    qf_list = []

    for pol, ind in zip(policy_data, baseline_data):
        pol_val, ind_val = add_missing_keys(pol['value'], ind['value'])
        p_prob = dict_to_prob(pol_val)
        i_prob = dict_to_prob(ind_val)

        hell = hellinger(p_prob, i_prob)
        wass = wasserstein(p_prob, i_prob)
        jensen = jensen_shannon_divergence(p_prob, i_prob)
        tv_distance = total_variation_distance(p_prob, i_prob)
        qf_d = quantum_fidelity(p_prob, i_prob)

        hellinger_list.append(hell)
        wasserstein_list.append(wass)
        jensen_list.append(jensen)
        tv_distance_list.append(tv_distance)
        qf_list.append(qf_d)

    return hellinger_list, wasserstein_list, jensen_list, tv_distance_list, qf_list


########################################
# RUTAS DE LOS ARCHIVOS EL BASE, EL DE SIEMPRE
########################################

# baseline_path = "resultadosIBM_individuales/resultado_individual.txt"

# # cargar baseline SIN normalizar
# baseline_data = [load_result_txt(baseline_path, "baseline", normalize=False)]

# # cargar los 11 batches CON normalización a 26000
# all_batches = []
# for i in range(1, 12):
#     batch_path = f"resultadosIBM_{i}_batch/resultado_{i}_batch.txt"
#     batch_data = load_result_txt(batch_path, f"batch_{i}", normalize=True, target_total=26000)
#     all_batches.append([batch_data])  # en lista para mantener estructura


########################################
# RUTAS DE LOS ARCHIVOS PARA LAS PRUEBAS DE PHASE ESTIMATION
########################################

baseline_path = "resultadosPhaseEstimation/resultadosIBM_individuales/resultado_individual.txt"

# cargar baseline SIN normalizar
baseline_data = [load_result_txt(baseline_path, "baseline", normalize=False)]

# ahora defines qué batches usar (ej: 1, 2, 5, 9, 40, 75, 200, 400, 495)
batch_indices = [1, 2, 5, 9, 40, 75, 200, 400, 495]

# cargar esos batches CON normalización a 33000
all_batches = []
for i in batch_indices:
    batch_path = f"resultadosPhaseEstimation/resultadosIBM_{i}_batch/resultado_{i}_batch.txt"
    batch_data = load_result_txt(batch_path, f"batch_{i}", normalize=True, target_total=33000)
    all_batches.append([batch_data])  # en lista para mantener estructura


########################################
# CALCULAR DISTANCIAS
########################################

results = []
for batch_idx, batch in zip(batch_indices, all_batches):
    hell, wass, jensen, tv, qf = compute_distances(batch, baseline_data)
    results.append({
        "batch": batch_idx,   # usar el índice real (1,2,5,9)
        "hellinger": hell,
        "wasserstein": wass,
        "jensen": jensen,
        "tv": tv,
        "qf": qf
    })


########################################
# GRAFICAR
########################################

# incluir también el baseline en X=0
batches = [0] + [r["batch"] for r in results]
hell_means = [0] + [np.mean(r["hellinger"]) for r in results]
wass_means = [0] + [np.mean(r["wasserstein"]) for r in results]
jensen_means = [0] + [np.mean(r["jensen"]) for r in results]
tv_means = [0] + [np.mean(r["tv"]) for r in results]
qf_means = [1] + [np.mean(r["qf"]) for r in results]  # baseline vs sí mismo → fidelidad máxima = 1

plt.figure(figsize=(12,6))
plt.plot(batches, hell_means, marker="o", label="Hellinger")
plt.plot(batches, wass_means, marker="o", label="Wasserstein")
plt.plot(batches, jensen_means, marker="o", label="Jensen-Shannon")
plt.plot(batches, tv_means, marker="o", label="Total Variation")
#plt.plot(batches, qf_means, marker="o", label="Quantum Fidelity")
plt.xlabel("Batch")
plt.ylabel("Mean distance")
plt.title("Mean distances per batch vs baseline (normalized to 33000)")
plt.legend()
plt.tight_layout()
plt.savefig("plot/mean_distances_batches.png", dpi=300)
plt.show()


########################################
# MOSTRAR LOS VALORES DE LA GRÁFICA EN CONSOLA
########################################

print("\n=== Valores medios por batch (los mismos que en la gráfica) ===\n")
print("Batch | Hellinger | Wasserstein | Jensen-Shannon | Total Variation | Quantum Fidelity")
print("-"*80)
for i in range(len(batches)):
    print(f"{batches[i]:5d} | "
          f"{hell_means[i]:10.5f} | "
          f"{wass_means[i]:12.5f} | "
          f"{jensen_means[i]:14.5f} | "
          f"{tv_means[i]:16.5f} | "
          f"{qf_means[i]:17.5f}")
