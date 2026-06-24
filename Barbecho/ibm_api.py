from qiskit_ibm_runtime import QiskitRuntimeService

API_KEY = ''
INSTANCE_CRN = ''


def get_backend_graph(backend_name="ibm_fez"):
    service = QiskitRuntimeService(
        channel="ibm_cloud",
        token=API_KEY,
        instance=INSTANCE_CRN
    )
    backend = service.backend(backend_name)
    properties = backend.properties()
    coupling_map = backend.configuration().coupling_map
    qubit_props = properties.to_dict()
    gate_props = properties.gates
    
    # Mostrar fecha de última calibración
    last_update = properties.last_update_date
    print(f"\n📅 Última calibración de {backend_name}: {last_update}")
    
    return coupling_map, qubit_props, gate_props

def get_backend_graph_with_backend(backend_name="ibm_fez"):
    """
    Similar a get_backend_graph pero también devuelve el objeto backend
    para acceder a información adicional (fecha de calibración, etc.)
    """
    service = QiskitRuntimeService(
        channel="ibm_cloud",
        token=API_KEY,
        instance=INSTANCE_CRN
    )
    backend = service.backend(backend_name)
    properties = backend.properties()
    coupling_map = backend.configuration().coupling_map
    qubit_props = properties.to_dict()
    gate_props = properties.gates
    
    # Mostrar fecha de última calibración
    last_update = properties.last_update_date
    print(f"\n📅 Última calibración de {backend_name}: {last_update}")
    
    return coupling_map, qubit_props, gate_props, backend
