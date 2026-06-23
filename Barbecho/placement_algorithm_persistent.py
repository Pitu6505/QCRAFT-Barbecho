# placement_algorithm_persistent.py
# Algoritmo de colocación con vector de visitados persistente para procesamiento de colas enormes

from config import MAX_NOISE_THRESHOLD, Porcentaje_util
import networkx as nx
from networkx.algorithms import isomorphism
from collections import deque
import time
import json
import os
import hashlib
from datetime import datetime
import math

PERSISTENT_DATA_DIR = "persistent_data"

def calculate_dynamic_noise_threshold(G, percentile=Porcentaje_util):
    """
    Calcula un umbral dinámico de ruido basado en los percentiles de la máquina.
    """
    noise_values = [G.nodes[n]['noise'] for n in G.nodes()]
    noise_values.sort()
    index = int(len(noise_values) * percentile / 100)
    dynamic_threshold = noise_values[min(index, len(noise_values) - 1)]
    print(f"🎯 Umbral dinámico calculado: {dynamic_threshold:.4f} (percentil {percentile})")
    return dynamic_threshold

def calculate_dynamic_distance(circuits, fixed_distance: int | None = None):
    """
    Calcula la distancia entre circuitos.

    - Si fixed_distance está definido → usa ese valor.
    - Si no → calcula dinámicamente usando la media de tamaños (ceil).
    """

    # 🔒 Si viene forzada desde el Job híbrido
    if fixed_distance is not None:
        print(f"🔒 Distancia fija utilizada para este Job: {fixed_distance}")
        return fixed_distance

    # ⚠️ Seguridad
    if not circuits:
        print("📏 Distancia por defecto usada: 1 (cola vacía)")
        return 1

    # 📏 Cálculo dinámico normal
    avg_size = sum(c['size'] for c in circuits) / len(circuits)
    dynamic_distance = math.ceil(avg_size)

    print(f"📏 Distancia dinámica calculada: {dynamic_distance} (media de tamaños: {avg_size:.2f})")
    return dynamic_distance

def get_calibration_id(backend_name, platform, backend_obj=None, properties=None):
    """
    Obtiene un ID único de calibración según la plataforma.
    
    Args:
        backend_name: Nombre del backend
        platform: "IBM" o "AWS"
        backend_obj: Objeto backend (para IBM)
        properties: Propiedades del backend (para AWS fallback)
    
    Returns:
        str: ID de calibración único
    """
    if platform == "IBM" and backend_obj is not None:
        try:
            last_update = backend_obj.properties().last_update_date
            # Convertir a string ISO format
            calib_id = last_update.isoformat() if hasattr(last_update, 'isoformat') else str(last_update)
            print(f"📅 Calibración IBM detectada: {calib_id}")
            return calib_id
        except Exception as e:
            print(f"⚠️ No se pudo obtener fecha de calibración IBM: {e}")
    
    # Fallback para AWS o si falla IBM: hash de valores de ruido
    if properties is not None:
        try:
            noise_values = []
            for qubit in properties.get('qubits', []):
                if qubit and len(qubit) > 5:
                    # Tomar readout error como referencia
                    if qubit[5] and 'value' in qubit[5]:
                        noise_values.append(qubit[5]['value'])
            
            # Crear hash de los primeros 10 valores (suficiente para detectar cambios)
            hash_input = str(sorted(noise_values[:10]))
            calib_hash = hashlib.md5(hash_input.encode()).hexdigest()[:16]
            print(f"🔐 Calibración detectada por hash: {calib_hash}")
            return calib_hash
        except Exception as e:
            print(f"⚠️ No se pudo generar hash de calibración: {e}")
            return "unknown"
    
    return "unknown"

PERSISTENT_DATA_DIR = "persistent_data"


def append_history(backend_name, mensaje):
    """
    Añade una entrada al historial de eventos del backend.
    """
    os.makedirs(PERSISTENT_DATA_DIR, exist_ok=True)

    history_file = os.path.join(
        PERSISTENT_DATA_DIR,
        f"{backend_name}_history.txt"
    )

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with open(history_file, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {mensaje}\n")


def load_usage_vector(backend_name, num_qubits, calibration_id):
    """
    Carga el vector de visitados desde archivo si existe y es válido.

    Returns:
        tuple: (usage_vector, loaded_successfully)
    """
    os.makedirs(PERSISTENT_DATA_DIR, exist_ok=True)

    filepath = os.path.join(
        PERSISTENT_DATA_DIR,
        f"{backend_name}_usage.json"
    )

    if not os.path.exists(filepath):
        print(f"📝 Creando nuevo vector de visitados para {backend_name}")

        append_history(
            backend_name,
            "Creado nuevo vector de visitados"
        )

        return [0] * num_qubits, False

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Validar backend
        if data.get('backend_name') != backend_name:
            print("⚠️ Backend diferente detectado. Reiniciando vector.")

            append_history(
                backend_name,
                "Backend diferente detectado. Vector reiniciado."
            )

            return [0] * num_qubits, False

        # Validar número de qubits
        if data.get('num_qubits') != num_qubits:
            print(
                f"⚠️ Número de qubits cambió "
                f"({data.get('num_qubits')} -> {num_qubits}). "
                f"Reiniciando vector."
            )

            append_history(
                backend_name,
                f"Número de qubits cambió "
                f"({data.get('num_qubits')} -> {num_qubits}). "
                f"Vector reiniciado."
            )

            return [0] * num_qubits, False

        # Validar calibración
        if data.get('calibration_id') != calibration_id:
            print("⚠️ Nueva calibración detectada. Reiniciando vector.")
            print(f"   Anterior: {data.get('calibration_id')}")
            print(f"   Actual: {calibration_id}")

            append_history(
                backend_name,
                f"Nueva calibración detectada. "
                f"Anterior={data.get('calibration_id')} "
                f"Actual={calibration_id}"
            )

            return [0] * num_qubits, False

        # Cargar vector válido
        usage_vector = data.get(
            'usage_vector',
            [0] * num_qubits
        )

        last_updated = data.get(
            'last_updated',
            'unknown'
        )

        print("✅ Vector de visitados cargado exitosamente")
        print(f"   Última actualización: {last_updated}")
        print(f"   Total de usos: {sum(usage_vector)}")

        append_history(
            backend_name,
            f"Vector cargado correctamente. "
            f"Total usos={sum(usage_vector)}"
        )

        return usage_vector, True

    except Exception as e:
        print(f"⚠️ Error al cargar vector de visitados: {e}")

        append_history(
            backend_name,
            f"ERROR al cargar vector: {e}"
        )

        return [0] * num_qubits, False


def save_usage_vector(
    backend_name,
    num_qubits,
    calibration_id,
    usage_vector
):
    """
    Guarda el vector de visitados en JSON y añade
    una entrada al historial.
    """
    os.makedirs(PERSISTENT_DATA_DIR, exist_ok=True)

    filepath = os.path.join(
        PERSISTENT_DATA_DIR,
        f"{backend_name}_usage.json"
    )

    data = {
        "backend_name": backend_name,
        "calibration_id": calibration_id,
        "num_qubits": num_qubits,
        "usage_vector": usage_vector,
        "last_updated": datetime.now().isoformat(),
        "total_uses": sum(usage_vector)
    }

    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)

        print(f"💾 Vector de visitados guardado en {filepath}")
        print(f"   Total de usos registrados: {sum(usage_vector)}")

        append_history(
            backend_name,
            f"Guardado vector. "
            f"Total usos={sum(usage_vector)} "
            f"Vector={usage_vector}"
        )

    except Exception as e:
        print(f"⚠️ Error al guardar vector de visitados: {e}")

        append_history(
            backend_name,
            f"ERROR al guardar vector: {e}"
        )


def is_far_enough(
    G,
    candidate_nodes,
    used_nodes,
    min_distance
):
    """
    Verifica que los nodos candidatos estén
    suficientemente lejos de los usados.
    """
    for u in candidate_nodes:
        for v in used_nodes:
            try:
                if nx.shortest_path_length(
                    G,
                    u,
                    v
                ) <= min_distance:
                    return False

            except nx.NetworkXNoPath:
                continue

    return True



def save_noise_profile(G, backend_name, calibration_id):
    """
    Guarda el valor de ruido de cada qubit en un archivo de texto histórico.
    """
    os.makedirs(PERSISTENT_DATA_DIR, exist_ok=True)
    
    filepath = os.path.join(
        PERSISTENT_DATA_DIR, 
        f"{backend_name}_noise_history.txt"
    )
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    with open(filepath, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] Calibración: {calibration_id}\n")
        
        # Extraer y ordenar los nodos para que salgan en orden (0, 1, 2...)
        sorted_nodes = sorted(G.nodes())
        for node in sorted_nodes:
            noise_val = G.nodes[node].get('noise', float('inf'))
            # Si el ruido es infinito (qubit roto/desconectado), lo marcamos
            if noise_val == float('inf'):
                f.write(f"  Qubit {node:03d}: INF (Inutilizable)\n")
            else:
                f.write(f"  Qubit {node:03d}: {noise_val:.6f}\n")
                
        f.write("-" * 50 + "\n")

# def load_usage_vector(backend_name, num_qubits, calibration_id):
#     """
#     Carga el vector de visitados desde archivo si existe y es válido.
    
#     Returns:
#         list: Vector de uso (todos 0 si es nuevo) y bool indicando si se cargó
#     """
#     os.makedirs(PERSISTENT_DATA_DIR, exist_ok=True)
#     filepath = os.path.join(PERSISTENT_DATA_DIR, f"{backend_name}_usage.json")
    
#     if not os.path.exists(filepath):
#         print(f"📝 Creando nuevo vector de visitados para {backend_name}")
#         return [0] * num_qubits, False
    
#     try:
#         with open(filepath, 'r') as f:
#             data = json.load(f)
        
#         # Validar que sea la misma máquina y calibración
#         if data.get('backend_name') != backend_name:
#             print(f"⚠️ Backend diferente detectado. Reiniciando vector.")
#             return [0] * num_qubits, False
        
#         if data.get('num_qubits') != num_qubits:
#             print(f"⚠️ Número de qubits cambió ({data.get('num_qubits')} -> {num_qubits}). Reiniciando vector.")
#             return [0] * num_qubits, False
        
#         if data.get('calibration_id') != calibration_id:
#             print(f"⚠️ Nueva calibración detectada. Reiniciando vector.")
#             print(f"   Anterior: {data.get('calibration_id')}")
#             print(f"   Actual: {calibration_id}")
#             return [0] * num_qubits, False
        
#         # Todo válido, cargar vector
#         usage_vector = data.get('usage_vector', [0] * num_qubits)
#         last_updated = data.get('last_updated', 'unknown')
#         print(f"✅ Vector de visitados cargado exitosamente")
#         print(f"   Última actualización: {last_updated}")
#         print(f"   Total de usos: {sum(usage_vector)}")
        
#         return usage_vector, True
        
#     except Exception as e:
#         print(f"⚠️ Error al cargar vector de visitados: {e}")
#         return [0] * num_qubits, False

# def save_usage_vector(backend_name, num_qubits, calibration_id, usage_vector):
#     """
#     Guarda el vector de visitados en archivo JSON.
#     """
#     os.makedirs(PERSISTENT_DATA_DIR, exist_ok=True)
#     filepath = os.path.join(PERSISTENT_DATA_DIR, f"{backend_name}_usage.json")
    
#     data = {
#         "backend_name": backend_name,
#         "calibration_id": calibration_id,
#         "num_qubits": num_qubits,
#         "usage_vector": usage_vector,
#         "last_updated": datetime.now().isoformat(),
#         "total_uses": sum(usage_vector)
#     }
    
#     try:
#         with open(filepath, 'w') as f:
#             json.dump(data, f, indent=2)
#         print(f"💾 Vector de visitados guardado en {filepath}")
#         print(f"   Total de usos registrados: {sum(usage_vector)}")
#     except Exception as e:
#         print(f"⚠️ Error al guardar vector de visitados: {e}")

def is_far_enough(G, candidate_nodes, used_nodes, min_distance):
    """
    Verifica que los nodos candidatos estén suficientemente lejos de los usados.
    """
    for u in candidate_nodes:
        for v in used_nodes:
            try:
                if nx.shortest_path_length(G, u, v) <= min_distance:
                    return False
            except nx.NetworkXNoPath:
                continue
    return True
#esta bien
# def find_isomorphic_subgraph(G, logical_graph, used_nodes, usage_vector, noise_threshold, min_distance):
#     """
#     Encuentra un subgrafo isomorfo, priorizando qubits menos utilizados.
#     """
#     for nodes_subset in nx.algorithms.components.connected_components(G):
#         if len(nodes_subset) < logical_graph.number_of_nodes():
#             continue
#         subgraph = G.subgraph(nodes_subset)

#         matcher = isomorphism.GraphMatcher(
#             subgraph,
#             logical_graph,
#             node_match=lambda n1, n2: n1.get("noise", 0) <= noise_threshold
#         )
        
#         # Recolectar todos los matches posibles
#         all_matches = []
#         for match in matcher.subgraph_isomorphisms_iter():
#             candidate = list(match.keys())
#             if all(G.nodes[n]['noise'] <= noise_threshold for n in candidate):
#                 if is_far_enough(G, candidate, used_nodes, min_distance):
#                     # Calcular score basado en uso
#                     total_usage = sum(usage_vector[n] for n in candidate)
#                     all_matches.append((total_usage, candidate))
        
#         # Retornar el match con menor uso total
#         if all_matches:
#             all_matches.sort(key=lambda x: x[0])
#             return all_matches[0][1]
    
#     return None

#esta bien

# def bfs_connected_groups(G, start, size, used_nodes, usage_vector, noise_threshold, min_distance, max_solutions=3, max_iterations=1000):
#     """
#     BFS optimizado que considera el vector de visitados.
#     """
#     if start in used_nodes or G.nodes[start]['noise'] > noise_threshold:
#         return []
        
#     queue = deque([[start]])
#     groups = []
#     iterations = 0

#     while queue and len(groups) < max_solutions and iterations < max_iterations:
#         iterations += 1
#         path = queue.popleft()
        
#         if len(path) == size:
#             if all(G.nodes[n]['noise'] <= noise_threshold for n in path):
#                 if is_far_enough(G, path, used_nodes, min_distance):
#                     groups.append(list(path))
#                     if len(groups) >= max_solutions:
#                         break
#             continue

#         if len(path) < size:
#             # Ordenar vecinos por uso (menos usado primero)
#             neighbors = [(usage_vector[n], n) for n in G.neighbors(path[-1]) 
#                         if n not in path and n not in used_nodes 
#                         and G.nodes[n]['noise'] <= noise_threshold]
#             neighbors.sort()
            
#             for _, neighbor in neighbors:
#                 queue.append(path + [neighbor])
    
#     if iterations >= max_iterations and not groups:
#         print(f"⚠️ BFS timeout para size={size}")
    
#     return groups

def find_isomorphic_subgraph(G, logical_graph, forbidden_nodes, usage_vector, noise_threshold):
    """
    Encuentra un subgrafo isomorfo, evitando las zonas prohibidas.
    """
    for nodes_subset in nx.algorithms.components.connected_components(G):
        if len(nodes_subset) < logical_graph.number_of_nodes():
            continue
        subgraph = G.subgraph(nodes_subset)

        matcher = isomorphism.GraphMatcher(
            subgraph,
            logical_graph,
            node_match=lambda n1, n2: n1.get("noise", 0) <= noise_threshold
        )
        
        all_matches = []
        for match in matcher.subgraph_isomorphisms_iter():
            candidate = list(match.keys())
            # Verificación instantánea O(1) de la zona prohibida
            if all(G.nodes[n]['noise'] <= noise_threshold and n not in forbidden_nodes for n in candidate):
                total_usage = sum(usage_vector[n] for n in candidate)
                all_matches.append((total_usage, candidate))
        
        if all_matches:
            all_matches.sort(key=lambda x: x[0])
            return all_matches[0][1]
    
    return None

def bfs_connected_groups(G, start, size, forbidden_nodes, usage_vector, noise_threshold, max_solutions=3, max_iterations=1000):
    """
    BFS optimizado usando zonas prohibidas precalculadas.
    """
    if start in forbidden_nodes or G.nodes[start]['noise'] > noise_threshold:
        return []
        
    queue = deque([[start]])
    groups = []
    iterations = 0

    while queue and len(groups) < max_solutions and iterations < max_iterations:
        iterations += 1
        path = queue.popleft()
        
        if len(path) == size:
            if all(G.nodes[n]['noise'] <= noise_threshold for n in path):
                groups.append(list(path))
                if len(groups) >= max_solutions:
                    break
            continue

        if len(path) < size:
            # Solo miramos vecinos que NO estén en la zona prohibida
            neighbors = [(usage_vector[n], n) for n in G.neighbors(path[-1]) 
                        if n not in path and n not in forbidden_nodes 
                        and G.nodes[n]['noise'] <= noise_threshold]
            neighbors.sort()
            
            for _, neighbor in neighbors:
                queue.append(path + [neighbor])
    
    return groups
def place_circuits_persistent(G, circuits, usage_vector, backend_name, calibration_id, 
                              noise_threshold=None, max_time_seconds=60, fixed_distance=None):
    """
    Asigna circuitos usando el vector de visitados y zonas prohibidas en O(1).
    Asegura que no se asignen qubits físicos duplicados a un mismo circuito.
    """
    placed = []
    errors = []
    used_nodes = set()
    forbidden_nodes = set()
    start_time = time.time()  # Reiniciamos el tiempo para cada iteración de capa
    
    if noise_threshold is None:
        noise_threshold = calculate_dynamic_noise_threshold(G, percentile=Porcentaje_util)
    
    min_circuit_distance = calculate_dynamic_distance(circuits, fixed_distance=fixed_distance)
    
    print(f"🔧 Configuración:")
    print(f"   - Umbral de ruido: {noise_threshold:.4f}")
    print(f"   - Distancia mínima: {min_circuit_distance}")
    print(f"   - Circuitos en cola: {len(circuits)}")
    print(f"   - Uso actual del backend: {sum(usage_vector)} asignaciones previas")


    save_noise_profile(G, backend_name, calibration_id)

    def update_forbidden_zones(assigned_nodes):
        for node in assigned_nodes:
            reachable = nx.single_source_shortest_path_length(G, node, cutoff=min_circuit_distance)
            forbidden_nodes.update(reachable.keys())

    for idx, circuit in enumerate(circuits):
        elapsed = time.time() - start_time
        if elapsed > max_time_seconds:
            print(f"⏱️ TIMEOUT GLOBAL: {elapsed:.2f}s > {max_time_seconds}s")
            remaining = [c['id'] for c in circuits if c['id'] not in [p[0] for p in placed]]
            for cid in remaining:
                errors.append(f"Circuito {cid} no procesado por timeout global")
            break
        
        size = circuit['size']
        
        available_nodes = [n for n in G.nodes if n not in forbidden_nodes and G.nodes[n]['noise'] <= noise_threshold]
        if len(available_nodes) < size:
            errors.append(f"Circuito {circuit['id']} no procesado: No queda espacio libre por la distancia de {min_circuit_distance}.")
            continue

        # 4️⃣ Intento rápido: isomorfismo (circuitos pequeños)
        mapped = False
        if 'edges' in circuit and circuit['edges'] and size <= 4:
            logical_graph = nx.Graph()
            logical_graph.add_nodes_from(range(size))
            logical_graph.add_edges_from(circuit['edges'])
            
            mapping = find_isomorphic_subgraph(G, logical_graph, forbidden_nodes, usage_vector, noise_threshold)

            # Validar que no haya duplicados
            if mapping and len(set(mapping)) == size:
                used_nodes.update(mapping)
                for node in mapping:
                    usage_vector[node] += 1
                update_forbidden_zones(mapping)
                placed.append((circuit['id'], mapping))
                mapped = True

        if mapped:
            continue

        # 5️⃣ Manejo de componentes desconectados
        if 'edges' in circuit and circuit['edges']:
            logical_graph = nx.Graph()
            logical_graph.add_nodes_from(range(size))
            logical_graph.add_edges_from(circuit['edges'])
            components = list(nx.connected_components(logical_graph))

            if len(components) > 1:
                all_assigned = []
                success = True
                temp_forbidden = set(forbidden_nodes)
                
                for component in components:
                    comp_size = len(component)
                    
                    if comp_size == 1:
                        best_node = None
                        best_score = float('inf')
                        
                        for node in G.nodes:
                            # Verificamos temp_forbidden y que no se haya asignado ya a esta componente
                            if node in temp_forbidden or node in all_assigned or G.nodes[node]['noise'] > noise_threshold:
                                continue
                            
                            score = usage_vector[node] * 1000 + G.nodes[node]['noise']
                            if score < best_score:
                                best_score = score
                                best_node = node
                        
                        if best_node is not None:
                            all_assigned.append(best_node)
                            reach = nx.single_source_shortest_path_length(G, best_node, cutoff=min_circuit_distance)
                            temp_forbidden.update(reach.keys())
                        else:
                            success = False
                            break
                    else:
                        best_group = None
                        best_score = float('inf')
                        
                        sorted_nodes = sorted(
                            [n for n in G.nodes if n not in temp_forbidden and n not in all_assigned and G.nodes[n]['noise'] <= noise_threshold],
                            key=lambda n: (usage_vector[n], G.nodes[n]['noise'])
                        )
                        max_nodes_to_explore = min(10, len(sorted_nodes))
                        
                        for node in sorted_nodes[:max_nodes_to_explore]:
                            candidate_groups = bfs_connected_groups(
                                G, node, comp_size, temp_forbidden, usage_vector, 
                                noise_threshold, max_solutions=3
                            )
                            
                            for group in candidate_groups:
                                # Asegurar que el grupo no contenga nodos ya asignados
                                if any(n in all_assigned for n in group):
                                    continue
                                usage_score = sum(usage_vector[n] for n in group)
                                noise_score = sum(G.nodes[n]['noise'] for n in group)
                                total_score = usage_score * 1000 + noise_score
                                
                                if total_score < best_score:
                                    best_score = total_score
                                    best_group = group
                            
                            if best_group:
                                break
                        
                        if best_group:
                            all_assigned.extend(best_group)
                            for n in best_group:
                                reach = nx.single_source_shortest_path_length(G, n, cutoff=min_circuit_distance)
                                temp_forbidden.update(reach.keys())
                        else:
                            success = False
                            break
                            
                # Validar longitud y duplicados antes de confirmar
                if success and len(all_assigned) == size and len(set(all_assigned)) == size:
                    used_nodes.update(all_assigned)
                    for node in all_assigned:
                        usage_vector[node] += 1
                    update_forbidden_zones(all_assigned)
                    placed.append((circuit['id'], all_assigned))
                    mapped = True

        if mapped:
            continue
        
        # 6️⃣ Mapeo estándar final (fallback general)
        best_group = None
        best_score = float('inf')

        sorted_nodes = sorted(
            [n for n in G.nodes if n not in forbidden_nodes and G.nodes[n]['noise'] <= noise_threshold],
            key=lambda n: (usage_vector[n], G.nodes[n]['noise'])
        )
        
        max_nodes_to_explore = min(15, len(sorted_nodes))
        
        for node in sorted_nodes[:max_nodes_to_explore]:
            candidate_groups = bfs_connected_groups(
                G, node, size, forbidden_nodes, usage_vector, 
                noise_threshold, max_solutions=3
            )

            for group in candidate_groups:
                if len(set(group)) != size: # Evitar duplicados
                    continue
                usage_score = sum(usage_vector[n] for n in group)
                noise_score = sum(G.nodes[n]['noise'] for n in group)
                total_score = usage_score * 1000 + noise_score
                
                if total_score < best_score:
                    best_score = total_score
                    best_group = group
            
            if best_group:
                break

        if best_group and len(set(best_group)) == size:
            used_nodes.update(best_group)
            for node in best_group:
                usage_vector[node] += 1
            update_forbidden_zones(best_group)
            placed.append((circuit['id'], best_group))
        else:
            reason = f"Circuito {circuit['id']} no se pudo asignar: "
            reason += f"no hay {size} qubits disponibles por el límite de ruido o distancia."
            errors.append(reason)

    # Guardar vector actualizado
    save_usage_vector(backend_name, len(usage_vector), calibration_id, usage_vector)
    
    return placed, errors


#ESTE ESAT AUN MEJOR

# def place_circuits_persistent(G, circuits, usage_vector, backend_name, calibration_id, 
#                               noise_threshold=None, max_time_seconds=60, fixed_distance=None):
#     """
#     Asigna circuitos usando el vector de visitados y zonas prohibidas en O(1).
#     """
#     placed = []
#     errors = []
#     used_nodes = set()
#     forbidden_nodes = set() # 👈 Zonas prohibidas
#     start_time = time.time()
    
#     if noise_threshold is None:
#         noise_threshold = calculate_dynamic_noise_threshold(G, percentile=Porcentaje_util)
    
#     min_circuit_distance = calculate_dynamic_distance(circuits, fixed_distance=fixed_distance)
    
#     print(f"🔧 Configuración:")
#     print(f"   - Umbral de ruido: {noise_threshold:.4f}")
#     print(f"   - Distancia mínima: {min_circuit_distance}")
#     print(f"   - Circuitos en cola: {len(circuits)}")
#     print(f"   - Uso actual del backend: {sum(usage_vector)} asignaciones previas")

#     # Función auxiliar para tachar el grafo rápidamente
#     def update_forbidden_zones(assigned_nodes):
#         for node in assigned_nodes:
#             # Calcula todos los vecinos a 'min_circuit_distance' saltos de golpe
#             reachable = nx.single_source_shortest_path_length(G, node, cutoff=min_circuit_distance)
#             forbidden_nodes.update(reachable.keys())

#     for idx, circuit in enumerate(circuits):
#         elapsed = time.time() - start_time
#         if elapsed > max_time_seconds:
#             print(f"⏱️ TIMEOUT GLOBAL: {elapsed:.2f}s > {max_time_seconds}s")
#             print(f"   Procesados {len(placed)}/{len(circuits)} circuitos.")
#             remaining = [c['id'] for c in circuits if c['id'] not in [p[0] for p in placed]]
#             for cid in remaining:
#                 errors.append(f"Circuito {cid} no procesado por timeout global")
#             break
        
#         if idx % 10 == 0:
#             print(f"📊 Progreso: {idx}/{len(circuits)} ({elapsed:.1f}s)")

#         size = circuit['size']
        
#         # 🚀 FAIL FAST: Si ya no hay nodos libres en todo el grafo, saltamos circuito
#         available_nodes = [n for n in G.nodes if n not in forbidden_nodes and G.nodes[n]['noise'] <= noise_threshold]
#         if len(available_nodes) < size:
#             errors.append(f"Circuito {circuit['id']} no procesado: No queda espacio libre por la distancia de {min_circuit_distance}.")
#             continue

#         # 4️⃣ Intento rápido: isomorfismo (circuitos pequeños)
#         if 'edges' in circuit and circuit['edges'] and size <= 4:
#             logical_graph = nx.Graph()
#             logical_graph.add_nodes_from(range(size))
#             logical_graph.add_edges_from(circuit['edges'])
            
#             mapping = find_isomorphic_subgraph(G, logical_graph, forbidden_nodes, usage_vector, noise_threshold)

#             if mapping:
#                 used_nodes.update(mapping)
#                 for node in mapping:
#                     usage_vector[node] += 1
#                 update_forbidden_zones(mapping)
#                 placed.append((circuit['id'], mapping))
#                 continue

#         # 5️⃣ Manejo de componentes desconectados
#         if 'edges' in circuit and circuit['edges']:
#             logical_graph = nx.Graph()
#             logical_graph.add_nodes_from(range(size))
#             logical_graph.add_edges_from(circuit['edges'])
#             components = list(nx.connected_components(logical_graph))

#             if len(components) > 1:
#                 all_assigned = []
#                 success = True
#                 temp_forbidden = set(forbidden_nodes) # Clonamos para poder revertir si falla
                
#                 for component in components:
#                     comp_size = len(component)
                    
#                     if comp_size == 1:
#                         best_node = None
#                         best_score = float('inf')
                        
#                         for node in G.nodes:
#                             if node in temp_forbidden or G.nodes[node]['noise'] > noise_threshold:
#                                 continue
                            
#                             score = usage_vector[node] * 1000 + G.nodes[node]['noise']
#                             if score < best_score:
#                                 best_score = score
#                                 best_node = node
                        
#                         if best_node is not None:
#                             all_assigned.append(best_node)
#                             reach = nx.single_source_shortest_path_length(G, best_node, cutoff=min_circuit_distance)
#                             temp_forbidden.update(reach.keys())
#                         else:
#                             success = False
#                             break
#                     else:
#                         best_group = None
#                         best_score = float('inf')
                        
#                         sorted_nodes = sorted(
#                             [n for n in G.nodes if n not in temp_forbidden and G.nodes[n]['noise'] <= noise_threshold],
#                             key=lambda n: (usage_vector[n], G.nodes[n]['noise'])
#                         )
#                         max_nodes_to_explore = min(10, len(sorted_nodes))
                        
#                         for node in sorted_nodes[:max_nodes_to_explore]:
#                             candidate_groups = bfs_connected_groups(
#                                 G, node, comp_size, temp_forbidden, usage_vector, 
#                                 noise_threshold, max_solutions=3
#                             )
                            
#                             for group in candidate_groups:
#                                 usage_score = sum(usage_vector[n] for n in group)
#                                 noise_score = sum(G.nodes[n]['noise'] for n in group)
#                                 total_score = usage_score * 1000 + noise_score
                                
#                                 if total_score < best_score:
#                                     best_score = total_score
#                                     best_group = group
                            
#                             if best_group:
#                                 break
                        
#                         if best_group:
#                             all_assigned.extend(best_group)
#                             for n in best_group:
#                                 reach = nx.single_source_shortest_path_length(G, n, cutoff=min_circuit_distance)
#                                 temp_forbidden.update(reach.keys())
#                         else:
#                             success = False
#                             break
                            
#                 if success:
#                     used_nodes.update(all_assigned)
#                     for node in all_assigned:
#                         usage_vector[node] += 1
#                     update_forbidden_zones(all_assigned)
#                     placed.append((circuit['id'], all_assigned))
#                     continue
#                 else:
#                     # Fallback natural, continuamos al paso 6
#                     pass
        
#         # 6️⃣ Mapeo estándar final (fallback general)
#         best_group = None
#         best_score = float('inf')

#         sorted_nodes = sorted(
#             [n for n in G.nodes if n not in forbidden_nodes and G.nodes[n]['noise'] <= noise_threshold],
#             key=lambda n: (usage_vector[n], G.nodes[n]['noise'])
#         )
        
#         max_nodes_to_explore = min(15, len(sorted_nodes))
        
#         for node in sorted_nodes[:max_nodes_to_explore]:
#             candidate_groups = bfs_connected_groups(
#                 G, node, size, forbidden_nodes, usage_vector, 
#                 noise_threshold, max_solutions=3
#             )

#             for group in candidate_groups:
#                 usage_score = sum(usage_vector[n] for n in group)
#                 noise_score = sum(G.nodes[n]['noise'] for n in group)
#                 total_score = usage_score * 1000 + noise_score
                
#                 if total_score < best_score:
#                     best_score = total_score
#                     best_group = group
            
#             if best_group:
#                 break

#         if best_group:
#             used_nodes.update(best_group)
#             for node in best_group:
#                 usage_vector[node] += 1
#             update_forbidden_zones(best_group)
#             placed.append((circuit['id'], best_group))
#         else:
#             reason = f"Circuito {circuit['id']} no se pudo asignar: "
#             reason += f"no hay {size} qubits disponibles por el límite de ruido o distancia."
#             errors.append(reason)

#     # Guardar vector actualizado
#     save_usage_vector(backend_name, len(usage_vector), calibration_id, usage_vector)
    
#     return placed, errors

#esta bien

# def place_circuits_persistent(G, circuits, usage_vector, backend_name, calibration_id, 
#                               noise_threshold=None, max_time_seconds=60, fixed_distance=None,):
#     """
#     Asigna circuitos usando el vector de visitados para optimizar el uso de qubits.
    
#     Args:
#         G: Grafo de qubits
#         circuits: Lista de circuitos a colocar
#         usage_vector: Vector de uso de qubits (modificado in-place)
#         backend_name: Nombre del backend
#         calibration_id: ID de calibración
#         noise_threshold: Umbral de ruido (None = calcular dinámicamente)
#         max_time_seconds: Timeout global
    
#     Returns:
#         (placements, errors): Tupla con asignaciones y errores
#     """
#     placed = []
#     errors = []
#     used_nodes = set()
#     start_time = time.time()
    
#     # ------------------------------------------------------------
#     # 1️⃣ Calcular umbral dinámico de ruido si no se proporciona
#     # ------------------------------------------------------------
#     # Se calcula un percentil del ruido del backend.
#     # Solo se permitirán qubits con ruido <= noise_threshold
#     if noise_threshold is None:
#         noise_threshold = calculate_dynamic_noise_threshold(G, percentile=Porcentaje_util)
    
#     # ------------------------------------------------------------
#     # 2️⃣ Calcular distancia mínima entre circuitos
#     # ------------------------------------------------------------
#     # Esta distancia evita que dos grupos asignados queden demasiado cerca.
#     # Puede ser dinámica (media de tamaños) o fija (si se pasa fixed_distance).
#     min_circuit_distance = calculate_dynamic_distance(
#     circuits,
#     fixed_distance=fixed_distance   # 👈 ESTA ES LA CLAVE
# )
    
#     print(f"🔧 Configuración:")
#     print(f"   - Umbral de ruido: {noise_threshold:.4f}")
#     print(f"   - Distancia entre circuitos: {min_circuit_distance}")
#     print(f"   - Circuitos en cola: {len(circuits)}")
#     print(f"   - Uso actual del backend: {sum(usage_vector)} asignaciones previas")

#     # ------------------------------------------------------------
#     # 3️⃣ Bucle principal: recorrer circuitos uno a uno
#     # ------------------------------------------------------------
#     for idx, circuit in enumerate(circuits):
#         # Verificar timeout global
#         elapsed = time.time() - start_time
#         if elapsed > max_time_seconds:
#             print(f"⏱️ TIMEOUT GLOBAL: {elapsed:.2f}s > {max_time_seconds}s")
#             print(f"   Procesados {len(placed)}/{len(circuits)} circuitos.")
#             remaining = [c['id'] for c in circuits if c['id'] not in [p[0] for p in placed]]
#             for cid in remaining:
#                 errors.append(f"Circuito {cid} no procesado por timeout global")
#             break
        
#         # Indicador de progreso cada 10 circuitos
#         if idx % 10 == 0:
#             print(f"📊 Progreso: {idx}/{len(circuits)} ({elapsed:.1f}s)")

#         # --------------------------------------------------------
#         # 4️⃣ Intento rápido: isomorfismo (circuitos pequeños)
#         # --------------------------------------------------------
#         # Si el circuito es pequeño (≤4 qubits), intentamos
#         # encontrar un subgrafo isomorfo exacto en el hardware.
#         # Esto preserva mejor la estructura lógica.
#         if 'edges' in circuit and circuit['edges'] and circuit['size'] <= 4:
#             logical_graph = nx.Graph()
#             logical_graph.add_nodes_from(range(circuit['size']))
#             logical_graph.add_edges_from(circuit['edges'])
#             mapping = find_isomorphic_subgraph(G, logical_graph, used_nodes, usage_vector, 
#                                               noise_threshold, min_circuit_distance)

#             if mapping:
#                 used_nodes.update(mapping)
#                 # Actualizar vector de visitados
#                 for node in mapping:
#                     usage_vector[node] += 1
#                 placed.append((circuit['id'], mapping))
#                 continue

#         # --------------------------------------------------------
#         # 5️⃣ Manejo de componentes desconectados
#         # --------------------------------------------------------
#         size = circuit['size']
        
      
#         if 'edges' in circuit and circuit['edges']:
#             logical_graph = nx.Graph()
#             logical_graph.add_nodes_from(range(size))
#             logical_graph.add_edges_from(circuit['edges'])
#             components = list(nx.connected_components(logical_graph))

#             # Si el circuito tiene múltiples componentes
#             if len(components) > 1:
#                 all_assigned = []
#                 success = True
                
#                 for component in components:
#                     comp_size = len(component)
#                     # ------------------------------------------------
#                     # Caso A: nodo aislado
#                     # ------------------------------------------------
#                     if comp_size == 1:
#                         best_node = None
#                         best_score = float('inf')
                        
#                         for node in G.nodes:
#                             # Restricciones duras
#                             if node in used_nodes:
#                                 continue
#                             if G.nodes[node]['noise'] > noise_threshold:
#                                 continue
#                             if not is_far_enough(G, [node], used_nodes, min_circuit_distance):
#                                 continue
                            
#                             # Score jerárquico:
#                             # 1️⃣ Minimizar uso histórico
#                             # 2️⃣ Minimizar ruido
#                             score = usage_vector[node] * 1000 + G.nodes[node]['noise']
#                             if score < best_score:
#                                 best_score = score
#                                 best_node = node
                        
#                         if best_node is not None:
#                             used_nodes.add(best_node)
#                             usage_vector[best_node] += 1
#                             all_assigned.append(best_node)
#                         else:
#                             success = False
#                             break
#                     # ------------------------------------------------
#                     # Caso B: componente conectada (>1)
#                     # ------------------------------------------------
#                     else:
#                         # Componente conectado
#                         best_group = None
#                         best_score = float('inf')
                        
#                         # Ordenar nodos por uso + ruido
#                         sorted_nodes = sorted(
#                             [n for n in G.nodes if n not in used_nodes and G.nodes[n]['noise'] <= noise_threshold],
#                             key=lambda n: (usage_vector[n], G.nodes[n]['noise'])
#                         )
#                         # Limitar exploración para evitar explosión combinatoria
#                         max_nodes_to_explore = min(10, len(sorted_nodes))
                        
#                         for node in sorted_nodes[:max_nodes_to_explore]:
#                             # Buscar grupos conectados vía BFS
#                             candidate_groups = bfs_connected_groups(
#                                 G, node, comp_size, used_nodes, usage_vector, 
#                                 noise_threshold, min_circuit_distance, max_solutions=3
#                             )
                            
#                             for group in candidate_groups:
#                                 # Score: suma de usos + ruido
#                                 usage_score = sum(usage_vector[n] for n in group)
#                                 noise_score = sum(G.nodes[n]['noise'] for n in group)
#                                 total_score = usage_score * 1000 + noise_score
                                
#                                 if total_score < best_score:
#                                     best_score = total_score
#                                     best_group = group
                            
#                             if best_group:
#                                 break
                        
#                         if best_group:
#                             used_nodes.update(best_group)
#                             for node in best_group:
#                                 usage_vector[node] += 1
#                             all_assigned.extend(best_group)
#                         else:
#                             success = False
#                             break
#                 # Si todas las componentes fueron asignadas correctamente
#                 if success:
#                     placed.append((circuit['id'], all_assigned))
#                     continue
#                 else:
#                     # Revertir cambios
#                     for node in all_assigned:
#                         used_nodes.discard(node)
#                         usage_vector[node] = max(0, usage_vector[node] - 1)
        
#         # ------------------------------------------------------------
#         # 6️⃣ Mapeo estándar final (fallback general)
#         # ------------------------------------------------------------
#         best_group = None
#         best_score = float('inf')

#         # Ordenar nodos por uso + ruido
#         sorted_nodes = sorted(
#             [n for n in G.nodes if n not in used_nodes and G.nodes[n]['noise'] <= noise_threshold],
#             key=lambda n: (usage_vector[n], G.nodes[n]['noise'])
#         )
        
#         max_nodes_to_explore = min(15, len(sorted_nodes))
        
#         for node in sorted_nodes[:max_nodes_to_explore]:
#             candidate_groups = bfs_connected_groups(
#                 G, node, size, used_nodes, usage_vector, 
#                 noise_threshold, min_circuit_distance, max_solutions=3
#             )

#             for group in candidate_groups:
#                 usage_score = sum(usage_vector[n] for n in group)
#                 noise_score = sum(G.nodes[n]['noise'] for n in group)
#                 total_score = usage_score * 1000 + noise_score
                
#                 if total_score < best_score:
#                     best_score = total_score
#                     best_group = group
            
#             if best_group:
#                 break

#         if best_group:
#             used_nodes.update(best_group)
#             for node in best_group:
#                 usage_vector[node] += 1
#             placed.append((circuit['id'], best_group))
#         else:
#             reason = f"Circuito {circuit['id']} no se pudo asignar: "
#             reason += f"no hay {size} qubits disponibles con las restricciones actuales"
#             errors.append(reason)

#     # Guardar vector actualizado
#     save_usage_vector(backend_name, len(usage_vector), calibration_id, usage_vector)
    
#     return placed, errors
