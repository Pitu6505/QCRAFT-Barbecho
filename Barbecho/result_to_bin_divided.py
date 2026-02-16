import os
from qiskit_ibm_runtime import QiskitRuntimeService

def divide_to_5bit_groups(counts_dict):
    """
    Divide strings de múltiplos de 4 bits en grupos de 4 bits.
    Si un grupo no tiene datos, se ignora y no se devuelve vacío.
    """
    max_len = max(len(k) for k in counts_dict)
    groups_total = max_len // 4
    result = []

    for full_binary_string, count_value in counts_dict.items():
        if len(full_binary_string) % 4 != 0:
            print(f"⚠️ Warning: {full_binary_string} tiene longitud {len(full_binary_string)}, no divisible entre 4")
            continue

        groups = len(full_binary_string) // 4
        for group_idx in range(groups):
            start_bit = group_idx * 4
            end_bit = start_bit + 4
            five_bit_string = full_binary_string[start_bit:end_bit]

            # Si aún no existe un dict para este grupo, lo creamos
            if len(result) <= group_idx:
                result.append({})

            # Guardamos solo si hay algo
            if count_value > 0:
                result[group_idx][five_bit_string] = result[group_idx].get(five_bit_string, 0) + count_value

    # Filtrar los grupos vacíos
    result = [grupo for grupo in result if len(grupo) > 0]

    return result

def procesar_job(job_id, folder_path="resultadosIBM_495_batch"):
    service = QiskitRuntimeService(
        channel='',
        token='',
        instance=''
    )

    job = service.job(job_id)
    result = job.result()

    merged_counts = {}

    print(result[0])

    ruta_carpeta = 'resultadosPhaseEstimation/resultadosIBM_495_batch'
    archivo_salida = 'salidaBin.txt'

    # Crear la carpeta si no existe
    os.makedirs(ruta_carpeta, exist_ok=True)

    # Ruta completa del archivo
    ruta_completa = os.path.join(ruta_carpeta, archivo_salida)
    

    #Guardar los resultados
    with open(ruta_completa, 'w') as f:
        print(result[0].data.creg_c.get_counts(), file=f)

    # for circ_idx, res in enumerate(result):
    #     counts = res.data.creg_c.get_counts()
    #     print(counts)
    #     grupos = divide_to_5bit_groups(counts)

    #     print(f"➡️ Circuit {circ_idx+1} dividido en {len(grupos)} grupos de 4 bits (sin vacíos)")

    #     for g_idx, grupo in enumerate(grupos):
    #         for bitstr, value in grupo.items():
    #             merged_counts[bitstr] = merged_counts.get(bitstr, 0) + value

    # total_sum = sum(merged_counts.values())

    # os.makedirs(folder_path, exist_ok=True)
    # output_path = os.path.join(folder_path, "resultado_495_batch.txt")

    # with open(output_path, "w") as f:
    #     f.write(str(merged_counts) + "\n")
    #     f.write(f"Suma total: {total_sum}\n")

    # print(f"✅ Resultados fusionados guardados en {output_path}")
    # print(f"🔢 Total de cuentas sumadas: {total_sum}")


# -------------------------
# USO REAL
# -------------------------
job_id = "d3id2ks1nk1s739pcec0"  # <-- cambia por el id real
procesar_job(job_id)
