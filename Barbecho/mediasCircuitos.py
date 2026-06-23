import os
import ast
import numpy as np
from scipy.stats import wasserstein_distance
from scipy.spatial.distance import jensenshannon

##################################
# CONFIGURACIÓN
##################################
BASE_DIR = "resultadosTodos"
CARPETA_TARGET = os.path.join(BASE_DIR, "resultadosIBM_147_Torino")
ARCHIVO_SALIDA = "medias_147_repeticion_tortino.txt"

def jensen_shannon_divergence(p, q):
    # jensenshannon de scipy da la raíz, la elevamos al cuadrado para la divergencia
    return jensenshannon(p, q) ** 2

def dict_to_prob_aligned(dict_target, dict_ref, all_keys):
    """Convierte un diccionario a lista de probabilidades alineada con las llaves globales"""
    p = [dict_target.get(k, 0) for k in all_keys]
    q = [dict_ref.get(k, 0) for k in all_keys]
    
    total_p = sum(p)
    total_q = sum(q)
    
    list_p = [val / total_p for val in p] if total_p > 0 else [0] * len(all_keys)
    list_q = [val / total_q for val in q] if total_q > 0 else [0] * len(all_keys)
    
    return list_p, list_q

def procesar_medias_distancias_internas():
    if not os.path.exists(CARPETA_TARGET):
        print(f"❌ No existe: {CARPETA_TARGET}")
        return

    circuitos = [d for d in os.listdir(CARPETA_TARGET) if os.path.isdir(os.path.join(CARPETA_TARGET, d))]
    resultados_finales = []

    for nombre_circuito in circuitos:
        ruta = os.path.join(CARPETA_TARGET, nombre_circuito)
        archivos = [f for f in os.listdir(ruta) if f.startswith("result_")]
        
        if len(archivos) < 2: continue # Necesitamos al menos 2 para comparar

        # 1. Cargar todos los datos primero para sacar la MEDIA de la carpeta
        todos_los_batches = []
        conteo_global = {}
        todas_las_keys = set()

        for f_name in archivos:
            try:
                with open(os.path.join(ruta, f_name), "r") as f:
                    data = ast.literal_eval(f.readline().strip())
                    todos_los_batches.append(data)
                    todas_las_keys.update(data.keys())
                    for k, v in data.items():
                        conteo_global[k] = conteo_global.get(k, 0) + v
            except: continue

        # 2. Definir la distribución de REFERENCIA (la media de todos los lotes)
        total_shots = sum(conteo_global.values())
        distribucion_referencia = {k: v / total_shots for k, v in conteo_global.items()}
        all_keys_sorted = sorted(list(todas_las_keys))

        # 3. Calcular distancias de cada batch contra la media
        js_list = []
        wass_list = []

        for batch in todos_los_batches:
            p, q = dict_to_prob_aligned(batch, distribucion_referencia, all_keys_sorted)
            
            if any(p) and any(q):
                js_list.append(jensen_shannon_divergence(p, q))
                wass_list.append(wasserstein_distance(p, q))

        # 4. Guardar medias de las distancias
        if js_list:
            resultados_finales.append({
                'circuito': nombre_circuito,
                'js_media': np.mean(js_list),
                'wass_media': np.mean(wass_list),
                'n': len(archivos)
            })
            print(f"✅ Calculada estabilidad de: {nombre_circuito}")

    # 5. Guardar en el archivo TXT
    with open(ARCHIVO_SALIDA, "w") as out:
        out.write(f"{'Circuito':<40} | {'Media JS':<15} | {'Media Wass':<15} | {'Batches'}\n")
        out.write("-" * 85 + "\n")
        for r in resultados_finales:
            out.write(f"{r['circuito']:<40} | {r['js_media']:<15.6f} | {r['wass_media']:<15.6f} | {r['n']}\n")

    print(f"\n✨ Archivo guardado: {ARCHIVO_SALIDA}")

if __name__ == "__main__":
    procesar_medias_distancias_internas()