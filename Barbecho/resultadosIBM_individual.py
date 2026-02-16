import os

def merge_individual_results(folder_path="resultadosIBM_individuales"):
    merged_counts = {}

    # Recorremos todos los ficheros .txt
    for filename in sorted(os.listdir(folder_path)):
        if filename.endswith(".txt"):
            file_path = os.path.join(folder_path, filename)
            with open(file_path, "r") as f:
                lines = f.read().strip().splitlines()
                if len(lines) < 2:
                    continue
                dict_str = lines[1]  # El diccionario está en la segunda línea
                counts = eval(dict_str)  # convertir string a dict de Python

            # Fusionar con el acumulado
            for bitstr, value in counts.items():
                merged_counts[bitstr] = merged_counts.get(bitstr, 0) + value

    # Calcular la suma total
    total_sum = sum(merged_counts.values())

    # Guardar en un único archivo
    output_path = os.path.join(folder_path, "resultado_individual.txt")
    with open(output_path, "w") as f:
        f.write(str(merged_counts) + "\n")
        f.write(f"Suma total: {total_sum}\n")

    print(f"✅ Resultados fusionados guardados en {output_path}")
    print(f"🔢 Total de cuentas sumadas: {total_sum}")

# -------------------------
# USO REAL
# -------------------------
merge_individual_results("resultadosIBM_individuales")
