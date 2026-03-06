"""
main_persistent.py

API reutilizable para asignar circuitos a qubits físicos minimizando ruido,
apoyándose en el algoritmo persistente de uso histórico.
"""

from graph_utils import build_graph
from circuit_queue import CircuitQueue
from placement_algorithm_persistent import (
    place_circuits_persistent,
    load_usage_vector,
    get_calibration_id
)
from config import USE_PARTITION, PARTITIONS, PARTITION_INDEX

DEFAULT_PLATFORM = "IBM"
DEFAULT_BACKEND_NAME = "ibm_fez"


def _normalize_provider(provider: str) -> str:
    if not provider:
        return DEFAULT_PLATFORM
    provider = provider.strip().upper()
    if provider == "IBM":
        return "IBM"
    if provider == "AWS":
        return "AWS"
    raise ValueError("provider debe ser 'ibm'/'IBM' o 'aws'/'AWS'")


def _resolve_backend_data(platform: str, backend_name: str | None):
    backend_obj = None

    if platform == "IBM":
        from ibm_api import get_backend_graph_with_backend

        resolved_backend_name = backend_name or DEFAULT_BACKEND_NAME
        result = get_backend_graph_with_backend(resolved_backend_name)
        if not result or result[0] is None:
            raise RuntimeError("No se pudieron obtener los datos del backend IBM")
        coupling_map, properties, _, backend_obj = result
        return coupling_map, properties, backend_obj, resolved_backend_name

    from aws_api import get_backend_graph_aws_with_device

    result = get_backend_graph_aws_with_device()
    if not result or result[0] is None:
        raise RuntimeError("No se pudieron obtener los datos del backend AWS")
    coupling_map, properties, _, _ = result
    resolved_backend_name = backend_name or "aws_ankaa3"
    return coupling_map, properties, None, resolved_backend_name


def _normalize_circuits(circuits):
    if hasattr(circuits, "get_queue"):
        circuits = circuits.get_queue()

    normalized = []
    for circuit in circuits:
        circuit_id = str(circuit["id"])
        size = int(circuit["size"])
        item = {"id": circuit_id, "size": size}
        if circuit.get("edges"):
            item["edges"] = circuit["edges"]
        normalized.append(item)

    return normalized
# ESTO ESTA BIEN

# def select_best_qubits_persistent(
#     circuits,
#     provider: str = "ibm",
#     backend_name: str | None = None,
#     noise_threshold: float | None = None,
#     max_time_seconds: int = 60,
#     fixed_distance: int | None = None, 
# ):
#     """
#     Selecciona qubits físicos para una cola de circuitos según ruido + uso histórico.

#     Args:
#         circuits: lista de dicts con llaves {id, size, edges?} o un CircuitQueue.
#         provider: "ibm" o "aws".
#         backend_name: backend a utilizar (opcional).
#         noise_threshold: umbral fijo de ruido (None = dinámico).
#         max_time_seconds: timeout del algoritmo de colocación.

#     Returns:
#         tuple:
#           - cola_procesada (list[dict]) -> [{"id", "size", "physical_qubits"}, ...]
#           - layout_fisico (dict[str, list[int]]) -> id_circuito -> qubits físicos
#           - errors (list[str])
#     """
#     platform = _normalize_provider(provider)
#     normalized_circuits = _normalize_circuits(circuits)

#     if not normalized_circuits:
#         return [], {}, []

#     coupling_map, properties, backend_obj, resolved_backend_name = _resolve_backend_data(
#         platform=platform,
#         backend_name=backend_name,
#     )

#     graph = build_graph(
#         coupling_map,
#         properties,
#         partition_mode=USE_PARTITION,
#         partition_index=PARTITION_INDEX,
#         partitions=PARTITIONS,
#         partition_ranges=None,
#     )

#     calibration_id = get_calibration_id(
#         backend_name=resolved_backend_name,
#         platform=platform,
#         backend_obj=backend_obj,
#         properties=properties,
#     )

#     usage_vector, _ = load_usage_vector(
#         resolved_backend_name,
#         graph.number_of_nodes(),
#         calibration_id,
#     )

#     placements, errors = place_circuits_persistent(
#         G=graph,
#         circuits=normalized_circuits,
#         usage_vector=usage_vector,
#         backend_name=resolved_backend_name,
#         calibration_id=calibration_id,
#         noise_threshold=noise_threshold,
#         max_time_seconds=max_time_seconds,
#     )

#     sizes_by_id = {str(c["id"]): c["size"] for c in normalized_circuits}
#     cola_procesada = []
#     layout_fisico = {}

#     for circuit_id, physical_qubits in placements:
#         cid = str(circuit_id)
#         layout_fisico[cid] = physical_qubits
#         cola_procesada.append(
#             {
#                 "id": cid,
#                 "size": sizes_by_id.get(cid, len(physical_qubits)),
#                 "physical_qubits": physical_qubits,
#             }
#         )

#     return cola_procesada, layout_fisico, errors

def select_best_qubits_persistent(
    circuits,
    provider: str = "ibm",
    backend_name: str | None = None,
    noise_threshold: float | None = None,
    max_time_seconds: int = 60,
    fixed_distance: int | None = None, 
):
    """
    Selecciona qubits físicos para una cola de circuitos según ruido + uso histórico.

    Args:
        circuits: lista de dicts con llaves {id, size, edges?} o un CircuitQueue.
        provider: "ibm" o "aws".
        backend_name: backend a utilizar (opcional).
        noise_threshold: umbral fijo de ruido (None = dinámico).
        max_time_seconds: timeout del algoritmo de colocación.

    Returns:
        tuple:
          - cola_procesada (list[dict]) -> [{"id", "size", "physical_qubits"}, ...]
          - layout_fisico (dict[str, list[int]]) -> id_circuito -> qubits físicos
          - errors (list[str])
    """
    platform = _normalize_provider(provider)
    normalized_circuits = _normalize_circuits(circuits)

    if not normalized_circuits:
        return [], {}, []

    coupling_map, properties, backend_obj, resolved_backend_name = _resolve_backend_data(
        platform=platform,
        backend_name=backend_name,
    )

    graph = build_graph(
        coupling_map,
        properties,
        partition_mode=USE_PARTITION,
        partition_index=PARTITION_INDEX,
        partitions=PARTITIONS,
        partition_ranges=None,
    )

    calibration_id = get_calibration_id(
        backend_name=resolved_backend_name,
        platform=platform,
        backend_obj=backend_obj,
        properties=properties,
    )

    usage_vector, _ = load_usage_vector(
        resolved_backend_name,
        graph.number_of_nodes(),
        calibration_id,
    )

    placements, errors = place_circuits_persistent(
        G=graph,
        circuits=normalized_circuits,
        usage_vector=usage_vector,
        backend_name=resolved_backend_name,
        calibration_id=calibration_id,
        noise_threshold=noise_threshold,
        fixed_distance=fixed_distance
    )

    sizes_by_id = {str(c["id"]): c["size"] for c in normalized_circuits}
    cola_procesada = []
    layout_fisico = {}

    for circuit_id, physical_qubits in placements:
        cid = str(circuit_id)
        layout_fisico[cid] = physical_qubits
        cola_procesada.append(
            {
                "id": cid,
                "size": sizes_by_id.get(cid, len(physical_qubits)),
                "physical_qubits": physical_qubits,
            }
        )

    return cola_procesada, layout_fisico, errors



def _demo_run():
    from utiles.debug import mostrar_asignaciones

    queue = CircuitQueue()
    queue.add_circuit("demo_2", 2, edges=[(0, 1)])
    queue.add_circuit("demo_3", 3, edges=[(0, 1), (1, 2)])
    queue.add_circuit("demo_4", 4, edges=[(0, 1), (0, 2), (0, 3)])

    cola_procesada, layout_fisico, errors = select_best_qubits_persistent(
        circuits=queue,
        provider="ibm",
        backend_name=DEFAULT_BACKEND_NAME,
        noise_threshold=None,
        max_time_seconds=60,
    )

    placements = [(item["id"], item["physical_qubits"]) for item in cola_procesada]
    mostrar_asignaciones(placements, len(queue.get_queue()))

    if errors:
        print("\n🚫 Circuitos no asignados:")
        for err in errors:
            print(f"   • {err}")

    print("\nLayout físico:")
    print(layout_fisico)


if __name__ == "__main__":
    _demo_run()
