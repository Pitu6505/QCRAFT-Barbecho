# ARCHIVO: aws_api.py (COMPLETAMENTE CORREGIDO)

import networkx as nx
from braket.aws import AwsDevice
from braket.devices import Devices, LocalSimulator

# --- INICIO DE CORRECCIÓN 1: Clase Simulada ---
# Simula la estructura del objeto Gate de Qiskit
# que 'utiles/metrics.py' espera.
class SimulatedGate:
    def __init__(self, gate_name, qubits, error_value):
        self.gate = gate_name
        self.qubits = qubits
        # Simulamos la estructura de parámetros que espera
        # el código de métricas
        self.parameters = [
             {'name': 'gate_error', 'value': error_value}
        ]
# --- FIN DE CORRECCIÓN 1 ---


def get_backend_graph_aws():
    """
    Obtiene los datos de calibración de AWS Braket (Ankaa-3)
    y los formatea para que sean compatibles con la estructura
    de datos esperada por el proyecto de IBM (graph_utils.py).
    """
    print("🛰️  Conectando a AWS Braket para obtener datos de Ankaa-3...")
    
    try:
        device = AwsDevice(Devices.Rigetti.Ankaa3)
        properties_aws = device.properties
    except Exception as e:
        print(f"Error al conectar con AWS Braket: {e}")
        print("Asegúrate de que tus credenciales de AWS están configuradas.")
        return None, None, None

    calibration_data = properties_aws.standardized.dict()
    aws_qubit_props = calibration_data.get('oneQubitProperties', {})
    aws_gate_props = calibration_data.get('twoQubitProperties', {})
    
# --- FORMATEAR COUPLING_MAP ---
    g_temp = nx.Graph(properties_aws.paradigm.connectivity.connectivityGraph)
    
    # --- INICIO DE CORRECCIÓN ---
    # El grafo de AWS usa strings ('0', '1'). Debemos convertirlos a enteros.
    coupling_map = [[int(q1), int(q2)] for q1, q2 in g_temp.edges()]
    # --- FIN DE CORRECCIÓN ---

    # --- FORMATEAR PROPERTIES ---

    # --- INICIO DE CORRECCIÓN 2: Inicialización de Lista ---
    # 1. Encontramos el ID de qubit más alto (en el grafo o en las props)
    
    # Ahora 'coupling_map' SÍ tiene enteros, por lo que esto funciona.
    max_id_from_graph = max(q for edge in coupling_map for q in edge) if coupling_map else 0
    
    # Esto ya funcionaba y devolvía un 'int'
    max_id_from_props = max(int(q_id) for q_id in aws_qubit_props.keys()) if aws_qubit_props else 0
    
    # Ahora ambos son 'int' y 'max()' funciona.
    max_qubit_id = max(max_id_from_graph, max_id_from_props)

    # 2. El tamaño de la lista debe ser 1 + el ID más grande
    list_size = max_qubit_id + 1

    # 3. Creamos una lista "dummy" que graph_utils.py pueda
    #    procesar y asignar 'noise=inf' de forma segura.
    #    (T1=0, T2=0, ReadoutErr=1.0)
    dummy_q_props = [
        {'value': 0.0},  # T1 = 0
        {'value': 0.0},  # T2 = 0
        None,
        None,
        None,
        {'value': 1.0}   # Readout Error = 1.0
    ]
    
    # 4. Creamos la lista con el tamaño correcto, llena de dummies
    formatted_qubit_list = [dummy_q_props.copy() for _ in range(list_size)]
    
    # --- FIN DE CORRECCIÓN 2 ---

    # Ahora, rellenamos la lista con los datos REALES donde existan
    for q_id_str, props in aws_qubit_props.items():
        try:
            q_id = int(q_id_str)
        except ValueError:
            continue
            
        # Si el qubit 83 (o más) existe en props pero no en el grafo,
        # la lista podría ser demasiado pequeña. La expandimos si es necesario.
        while q_id >= len(formatted_qubit_list):
            formatted_qubit_list.append(dummy_q_props.copy())

        # Inicializamos la lista de propiedades "estilo IBM" con Nones
        ibm_style_list = [None] * 6 # Solo necesitamos índices 0, 1, 5

        # T1 (Índice 0) - DEJAR EN SEGUNDOS
        t1_s = props.get('T1', {}).get('value', 1e-9)
        ibm_style_list[0] = {'value': t1_s} # <-- ¡Error corregido! No convertir a ms.

        # T2 (Índice 1) - DEJAR EN SEGUNDOS
        t2_s = props.get('T2', {}).get('value', 1e-9)
        ibm_style_list[1] = {'value': t2_s} # <-- ¡Error corregido! No convertir a ms.
        
        # Readout Error (Índice 5)
        readout_fidelity = None
        for item in props.get('oneQubitFidelity', []):
            if item.get('fidelityType', {}).get('name') == 'READOUT':
                readout_fidelity = item.get('fidelity', 1.0)
                break
        
        readout_error = 1.0 - readout_fidelity if readout_fidelity is not None else 1.0
        ibm_style_list[5] = {'value': readout_error}
        
        # Asignar la lista formateada al índice del qubit
        formatted_qubit_list[q_id] = ibm_style_list

    properties = {'qubits': formatted_qubit_list}

    # --- FORMATEAR GATE_PROPS ---
    
    # --- INICIO DE CORRECCIÓN 3: Formato de Lista de Objetos ---
    # utiles/metrics.py espera una LISTA de objetos Gate
    
    gate_props_list = [] # <-- Cambiado a una lista
    
    for pair_str, props in aws_gate_props.items():
        try:
            q_pair = tuple(map(int, pair_str.strip("()").split(",")))
        except ValueError:
            continue

        cx_fidelity = None
        gate_name_from_aws = None
        for item in props.get('twoQubitFidelity', []):
            if item.get('fidelityType', {}).get('name') == 'CX':
                cx_fidelity = item.get('fidelity', 1.0)
                gate_name_from_aws = 'cx'
                break
        
        if cx_fidelity is None:
             for item in props.get('twoQubitFidelity', []):
                if item.get('fidelityType', {}).get('name') == 'CZ':
                    cx_fidelity = item.get('fidelity', 1.0)
                    gate_name_from_aws = 'cx' # Mapeamos CZ a 'cx'
                    break
        
        if gate_name_from_aws:
            cx_error = 1.0 - cx_fidelity if cx_fidelity is not None else 1.0
            
            # Creamos el objeto simulado
            sim_gate = SimulatedGate(
                gate_name=gate_name_from_aws,
                qubits=list(q_pair),
                error_value=cx_error
            )
            gate_props_list.append(sim_gate)
    # --- FIN DE CORRECCIÓN 3 ---

    print("✅ Datos de AWS Braket obtenidos y formateados.")
    # Devolvemos la LISTA, no el diccionario
    return coupling_map, properties, gate_props_list

def get_backend_graph_aws_with_device():
    """
    Similar a get_backend_graph_aws pero también devuelve el objeto device
    para acceder a información adicional.
    """
    print("🛰️  Conectando a AWS Braket para obtener datos de Ankaa-3...")
    
    try:
        device = AwsDevice(Devices.Rigetti.Ankaa3)
        properties_aws = device.properties
    except Exception as e:
        print(f"Error al conectar con AWS Braket: {e}")
        print("Asegúrate de que tus credenciales de AWS están configuradas.")
        return None, None, None, None

    calibration_data = properties_aws.standardized.dict()
    aws_qubit_props = calibration_data.get('oneQubitProperties', {})
    aws_gate_props = calibration_data.get('twoQubitProperties', {})
    
    # Reutilizar lógica de get_backend_graph_aws
    result = get_backend_graph_aws()
    if result[0] is None:
        return None, None, None, None
    
    coupling_map, properties, gate_props_list = result
    
    return coupling_map, properties, gate_props_list, device