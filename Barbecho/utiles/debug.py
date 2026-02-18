# debug_utils.py
import matplotlib.pyplot as plt
import networkx as nx
from matplotlib import cm

def mostrar_grafo(coupling_map):
    print("\n🔗 Conexiones del grafo:")
    for edge in coupling_map:
        print(f"Qubit {edge[0]} <--> Qubit {edge[1]}")
    nodos = set()
    for edge in coupling_map:
        nodos.update(edge)
    print(f"Total de nodos: {len(nodos)}")
    print(f"Total de aristas: {len(coupling_map)}")


def mostrar_propiedades(properties):
    print("\n📊 Propiedades de cada qubit:")
    for i, qubit in enumerate(properties["qubits"]):
        t1 = qubit[0]["value"]
        t2 = qubit[1]["value"]
        error = qubit[5]["value"]
        print(f"Qubit {i}: T1={t1:.2e}, T2={t2:.2e}, Error de lectura={error:.4f}")


def mostrar_asignaciones(placements, total):
    print("\n📦 Resultado de asignaciones:")
    if not placements:
        print("❌ Ningún circuito fue asignado.")
    else:
        for cid, nodes in placements:
            print(f"✅ Circuito {cid} asignado a qubits: {nodes}")
    
    if len(placements) < total:
        print(f"\n⚠️ Se asignaron solo {len(placements)} de {total} circuitos.")

def mostrar_correspondencia_logico_fisico(asignaciones):
    """
    Muestra qué qubits lógicos se asignaron a qué qubits físicos en cada circuito.

    :param asignaciones: lista de tuplas (circuit_id, lista_de_qubits_físicos)
    """
    print("\n🔄 Correspondencia de qubits lógicos → físicos:")
    for circuito_id, qubits_fisicos in asignaciones:
        print(f"\n🧪 {circuito_id}:")
        for i, qubit_fisico in enumerate(qubits_fisicos):
            print(f"  Lógico {i} → Físico {qubit_fisico}")

def calcular_ruido_total(G, asignaciones):
    """
    Calcula el ruido total acumulado de todos los qubits físicos usados en la asignación.

    :param G: Grafo de qubits físicos con atributo 'noise' en cada nodo
    :param asignaciones: lista de tuplas (circuit_id, lista_de_qubits_físicos)
    :return: ruido total acumulado (float)
    """
    qubits_utilizados = set()

    for _, qubits_fisicos in asignaciones:
        qubits_utilizados.update(qubits_fisicos)

    ruido_total = sum(G.nodes[q]['noise'] for q in qubits_utilizados)
    return ruido_total

def estimar_swap_noise(q0, q1, gate_props):
    """
    Estima el ruido de una puerta SWAP entre dos qubits basándose en el error de CNOT.

    :param q0: Qubit físico 1
    :param q1: Qubit físico 2
    :param gate_props: Lista de propiedades de puertas (backend.properties().gates)
    :return: ruido estimado de la SWAP
    """
    for gate in gate_props:
        if gate.name == "cx" and set(gate.qubits) == set([q0, q1]):
            cnot_error = gate.parameters[0].value  # Suponemos que es el error
            return 3 * cnot_error  # 3 CNOTs en una SWAP

    return float("inf")  # No conectados directamente: alto coste



