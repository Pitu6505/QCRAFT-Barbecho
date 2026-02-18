# Distancia mínima entre circuitos (número de nodos)
MIN_CIRCUIT_DISTANCE = 1

# Umbral máximo aceptable de ruido/temperatura para usar un nodo
MAX_NOISE_THRESHOLD = 470.00  #0.02
# Número de qubits con peor ruido a excluir automáticamente
# Por ejemplo, 20 excluye los 20 qubits con mayor ruido
# 0 = no excluir ninguno
EXCLUDE_WORST_QUBITS = 30
# Porcentaje de qubits a utilizar basado en percentil de ruido dinámico
# Por ejemplo, 95 permite usar el 95% de los qubits con menor ruido
Porcentaje_util = 95
# Configuración de particionado del grafo
USE_PARTITION = False       # True para activar particionado
PARTITIONS = 4             # número de particiones si se usa particionado uniforme
PARTITION_INDEX = 1        # índice 1-based de la partición a ejecutar ahora
# Ejemplo de ranges personalizados (opcional). Cada tupla es (start, end) inclusive.
# Si lo defines, se usa esta lista y se ignora PARTITIONS.
PARTITION_RANGES = [
    (0, 31),   # partición 1: nodos 0..31
    (32, 63),  # partición 2: nodos 32..63
    (64, 95),  # partición 3: nodos 64..95
    (96, 126)  # partición 4: nodos 96..126
]

# Configuración del modelo de Machine Learning
# Especifica la ruta al modelo entrenado que quieras usar
# Opciones:
#   - None: Usa el modelo por defecto (training/models/placement_model.pth)
#   - "training/models/placement_model.pth": Modelo actual
#   - "training/models/mi_modelo_custom.pth": Modelo personalizado
ML_MODEL_PATH = "training/models/Distancia1_IBM.pth"
# Si quieres usar un modelo específico, descomenta y edita:
# ML_MODEL_PATH = "training/models/placement_model.pth"

