from qiskit_ibm_runtime import QiskitRuntimeService

API_KEY = ""
INSTANCE_CRN = ""

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
    return coupling_map, qubit_props, gate_props
