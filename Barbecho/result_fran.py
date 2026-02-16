import os
import re
import ast
from qiskit_ibm_runtime import QiskitRuntimeService

# ---------------------------
# CONFIGURACIÓN
# ---------------------------
JOB_ID = "d3p0gbjld2is73ffe0m0"  # Cambia por el job real
BASE_PATH = "resultadosTodos/resultadosIBM_505_batch"
INFO_FILE = os.path.join(BASE_PATH, "info_505.txt")

# ---------------------------
# FUNCIONES AUXILIARES
# ---------------------------

def parse_info_file(path):
    """Lee el info.txt y devuelve una lista con info de cada circuito."""
    circuits = []

    # Intentamos leer con utf-8 y si falla, con latin1
    try:
        f = open(path, "r", encoding="utf-8")
        lines = f.readlines()
        f.close()
    except UnicodeDecodeError:
        f = open(path, "r", encoding="latin1")
        lines = f.readlines()
        f.close()

    for line in lines:
        m = re.match(
            r"Circuito:\s*(.*?)\s*\|\s*Registros cl\S+:\s*c(\d+)\s*-\s*c(\d+)\s*\|\s*Iteraci\S+:\s*(\d+)\s*\|\s*Batch:\s*(\d+)",
            line.strip()
        )
        if m:
            circuits.append({
                "nombre": m.group(1).strip().replace(".py", ""),
                "c_inicio": int(m.group(2)),
                "c_fin": int(m.group(3)),
                "iter": int(m.group(4)),
                "batch": int(m.group(5))
            })
    return circuits



def extraer_bits_por_rango(counts, c_inicio, c_fin):
    """
    Extrae solo los bits de los índices [c_inicio, c_fin] (de derecha a izquierda)
    de cada key en counts y suma los valores.
    """
    result = {}
    for bitstring, count in counts.items():
        # Aseguramos que el bitstring tenga la longitud necesaria
        bitstring = bitstring.zfill(c_fin + 1)
        # Invertimos para que c0 sea el bit más a la derecha
        bits_reversed = bitstring[::-1]
        sub_bits = bits_reversed[c_inicio:c_fin + 1]
        sub_bits = sub_bits[::-1]  # Volvemos al orden original

        result[sub_bits] = result.get(sub_bits, 0) + count

    return result


# ---------------------------
# MAIN
# ---------------------------

def procesar_resultados():
    # 1️⃣ Conectar al servicio y obtener resultados del job
    service = QiskitRuntimeService(
        channel='',
        token="",
        instance=''
        
        )

    job = service.job(JOB_ID)
    result = job.result()

    # Fusionamos todos los counts
    merged_counts = {}
    for res in result:
        counts = res.data.creg_c.get_counts()
        for k, v in counts.items():
            merged_counts[k] = merged_counts.get(k, 0) + v

    # 2️⃣ Leer info.txt
    circuitos = parse_info_file(INFO_FILE)

    # 3️⃣ Procesar cada circuito
    for c in circuitos:
        circ_name = c["nombre"]
        start, end, batch = c["c_inicio"], c["c_fin"], c["batch"]

        circ_dir = os.path.join(BASE_PATH, circ_name)
        os.makedirs(circ_dir, exist_ok=True)

        out_path = os.path.join(circ_dir, f"result_{batch}.txt")

        # 4️⃣ Extraer bits correspondientes
        filtered_counts = extraer_bits_por_rango(merged_counts, start, end)
        total = sum(filtered_counts.values())

        # 5️⃣ Guardar
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(str(filtered_counts) + "\n")
            f.write(f"Suma total: {total}\n")

        print(f"✅ Guardado {circ_name}/result_{batch}.txt ({len(filtered_counts)} entradas)")

    print("🎉 Todo listo.")


# ---------------------------
# EJECUCIÓN
# ---------------------------
if __name__ == "__main__":
    procesar_resultados()
