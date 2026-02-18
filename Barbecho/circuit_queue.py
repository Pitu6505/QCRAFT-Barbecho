class CircuitQueue:
    def __init__(self):
        self.queue = []

    def add_circuit(self, circuit_id, required_qubits, edges=None):
        circuit = {
            "id": circuit_id,
            "size": required_qubits
        }
        if edges:
            circuit["edges"] = edges
        self.queue.append(circuit)

    def get_queue(self):
        return self.queue
