import json
import math
from platform import machine
from platform import machine
import queue
import requests
from flask import request
import re
from circuit_queue import CircuitQueue
from main_persistent import select_best_qubits_persistent
from executeCircuitIBM import executeCircuitIBM
from executeCircuitAWS import runAWS, runAWS_save, code_to_circuit_aws, AWS 
from ResettableTimer import ResettableTimer
from threading import Thread, Lock
from typing import Callable
import time
from entrenamientoML import load_model
#from gestionarDispositivo import actualizar_dispositivos, actualizar_dispositivo_en_archivo
import os
import ast

import torch
import torch.nn as nn
import torch.optim as optim
import numpy as np
from qiskit_ibm_runtime import QiskitRuntimeService, SamplerV2 as Sampler, Batch
from qiskit import QuantumCircuit

from itertools import combinations

from collections import deque
import subprocess

import sys


    # LO QUE HACE BARBECHO
    #Cola original
    #     ↓
    # Congelar distancia
    #     ↓
    # Formatear cola → CircuitQueue
    #     ↓
    # Llamar al colocador persistente
    #     ↓
    # Extraer circuitos colocados
    #     ↓
    # Crear nueva capa horizontal
    #     ↓
    # Repetir hasta llenar o vaciar
    #     ↓
    # Ejecutar Job final

    
CARPETA_SALIDAS = os.path.join("Barbecho", "salidas")
class Policy:
    """
    Class to store the queues and timers of a policy
    """
    def __init__(self, policy, max_qubits, time_limit_seconds, executeCircuit, aws_machine, ibm_machine):
        """
        Attributes:
            queues (dict): The queues of the policy
            timers (dict): The timers of the policy
        """
        self.queues = {'ibm': [], 'aws': []}
        self.timers = {'ibm': ResettableTimer(time_limit_seconds, lambda: policy(self.queues['ibm'], max_qubits, 'ibm', executeCircuit, ibm_machine)),
                       'aws': ResettableTimer(time_limit_seconds, lambda: policy(self.queues['aws'], max_qubits, 'aws', executeCircuit, aws_machine))}

class SchedulerPolicies:
    """
    Class to manage the policies of the scheduler

    Methods:
    --------
    service(service_name) 
        The request handler, adding the circuit to the selected queue
    
    executeCircuit(data,qb,shots,provider,urls)
        Executes the circuit in the selected provider
    
    most_repetitive(array)
        Returns the most repetitive element in an array
    
    create_circuit(urls,code,qb,provider)
        Creates the circuit to execute based on the URLs
    
    send_shots_optimized(queue, max_qubits, provider, executeCircuit, machine)
        Sends the URLs to the server with the minimum number of shots using the shots_optimized policy
    
    send_shots_depth(queue, max_qubits, provider, executeCircuit, machine)
        Sends the URLs to the server with the minimum number of shots and similar depth using the shots_depth policy
    
    send_depth(queue, max_qubits, provider, executeCircuit, machine)
        Sends the URLs to the server with the most similar depth using the depth policy
    
    send_shots(queue, max_qubits, provider, executeCircuit, machine)
        Sends the URLs to the server with the minimum number of shots using the shots policy
    
    send(queue, max_qubits, provider, executeCircuit, machine)
        Sends the URLs to the server using the time policy
    """
    def __init__(self, app):
        """
        Initializes the SchedulerPolicies class

        Attributes:
            app (Flask): The Flask app            
            time_limit_seconds (int): The time limit in seconds            
            max_qubits (int): The maximum number of qubits            
            machine_ibm (str): The IBM machine            
            machine_aws (str): The AWS machine            
            services (dict): The services of the scheduler            
            translator (str): The URL of the translator            
            unscheduler (str): The URL of the unscheduler
        """
   
        self.eliminar_archivos_si_existen()
        self.iteracion = 0
        self.it = 0
        self.iteracion_tiempo = 0
        self.iteracion_ML = 0
        self.app = app
        self.time_limit_seconds = 50#500#300 #estaba en 600
        self.executeCircuitIBM = executeCircuitIBM()
        
        self.setMaxQubits()
        self.max_qubits = 312 #312 #254 o 266
        self.max_qubits_send = 156 #156 #127 o 133
        self.machine_ibm = 'ibm_kingston' # ibm_brisbane o ibm_torino o ibm_marrakesh o ibm_fez ibm_kingston
        self.machine_aws = 'local'
        

        self.services = {'time': Policy(self.send, self.max_qubits_send, self.time_limit_seconds, self.executeCircuit, self.machine_aws, self.machine_ibm),
                        'multibatch': Policy(self.send, self.max_qubits_send, self.time_limit_seconds, self.executeCircuit, self.machine_aws, self.machine_ibm),
                        'shots': Policy(self.send_shots, self.max_qubits, self.time_limit_seconds, self.executeCircuit, self.machine_aws, self.machine_ibm),
                        'depth': Policy(self.send_depth, self.max_qubits, self.time_limit_seconds, self.executeCircuit, self.machine_aws, self.machine_ibm),
                        'shots_depth': Policy(self.send_shots_depth, self.max_qubits, self.time_limit_seconds, self.executeCircuit, self.machine_aws, self.machine_ibm),
                        'shots_optimized': Policy(self.send_shots_optimized, self.max_qubits, self.time_limit_seconds, self.executeCircuit, self.machine_aws, self.machine_ibm),
                        'MaxML' : Policy(self.mainML, self.max_qubits, self.time_limit_seconds, self.executeCircuit, self.machine_aws, self.machine_ibm),
                        'MaxPD' : Policy(self.mainPD, self.max_qubits, self.time_limit_seconds, self.executeCircuit, self.machine_aws, self.machine_ibm),
                        'time_maquinas' : Policy(self.send_maquinas, self.max_qubits, self.time_limit_seconds, self.executeCircuit, self.machine_aws, self.machine_ibm),
                        'batch' : Policy(self.send_individual_batches, self.max_qubits, self.time_limit_seconds, self.executeCircuit, self.machine_aws, self.machine_ibm),
                        'Islas_Cuanticas_Edges': Policy(self.send_graph_placement_edges, self.max_qubits, self.time_limit_seconds, self.executeCircuit, self.machine_aws, self.machine_ibm),
                        'barbecho': Policy(self.send_combined_graph_horizontal, self.max_qubits, self.time_limit_seconds, self.executeCircuit, self.machine_aws, self.machine_ibm)}

        self.islas_cuanticas_lock = Lock()
        
        
        
        self.translator = f"http://{self.app.config['TRANSLATOR']}:{self.app.config['TRANSLATOR_PORT']}/code/"
        self.unscheduler = f"http://{self.app.config['HOST']}:{self.app.config['PORT']}/unscheduler"
        self.app.route('/service/<service_name>', methods=['POST'])(self.service)


    
    
    def eliminar_archivos_si_existen(self):
        
        """Comprueba si los archivos existen y los elimina si es así."""
        ARCHIVOS_A_ELIMINAR = [
        "criterio_1_MaxPD.txt",
        "criterio_2_MaxPD.txt",
        "criterio_3_MaxPD.txt",
        "criterio_1_MaxML.txt",
        "criterio_2_MaxML.txt",
        "criterio_3_MaxML.txt",
        "criterio_1_tiempo.txt",
        "criterio_2_tiempo.txt",
        "criterio_3_tiempo.txt",
        "criterio_tiempo.txt",
    ]
        for nombre_archivo in ARCHIVOS_A_ELIMINAR:
            ruta_completa = os.path.join(CARPETA_SALIDAS, nombre_archivo)
            if os.path.exists(ruta_completa):
                try:
                    os.remove(ruta_completa)
                    print(f"🗑️ Archivo eliminado: {ruta_completa}")
                except Exception as e:
                    print(f"❌ Error al eliminar el archivo {ruta_completa}: {e}")
            else:
                print(f"📂 El archivo {ruta_completa} no existe, no se eliminó.")

    def service(self, service_name:str) -> tuple:
        """
        The request handler, adding the circuit to the selected queue

        Args:
            service_name (str): The name of the service

        Request Parameters:
            circuit (str): The circuit to execute
            num_qubits (int): The number of qubits of the circuit            
            shots (int): The number of shots of the circuit            
            user (str): The user that executed the circuit
            circuit_name (str): The name of the circuit            
            maxDepth (int): The depth of the circuit            
            provider (str): The provider of the circuit

        Returns:
            tuple: The response of the request
        """
        if service_name not in self.services:
            return 'This service does not exist', 404
        circuit = request.json['circuit']
        num_qubits = request.json['num_qubits']
        shots = request.json['shots']
        user = request.json['user']
        circuit_name = request.json['circuit_name']
        maxDepth = request.json['maxDepth']
        provider = request.json['provider']
        criterio = request.json['criterio']
        data = (circuit, num_qubits, shots, user, circuit_name, maxDepth,criterio)
        self.services[service_name].queues[provider].append(data)
        if not self.services[service_name].timers[provider].is_alive():
            self.services[service_name].timers[provider].start()
        n_qubits = sum(item[1] for item in self.services[service_name].queues[provider])
        if n_qubits >= 254 and (service_name != 'time_maquinas' and service_name != 'MaxML' and service_name != 'MaxPD' and service_name != 'time' and service_name != 'barbecho'): #es 127
           self.services[service_name].timers[provider].execute_and_reset()
        return 'Data received', 200
        
     #EL BUENO QUE HAY
    def _compose_initial_layout(self, urls: list, layout_fisico: dict | None):
        if not layout_fisico:
            return None

        initial_layout = []
        for item in urls:
            user_id = str(item[3])
            assigned = layout_fisico.get(user_id)
            if not assigned:
                return None
            initial_layout.extend(assigned)

        return initial_layout if initial_layout else None


#     def executeCircuit(self,data:dict,qb:list,shots:list,provider:str,urls:list, machine:str, layout_fisico:dict|None=None) -> None: #Data is the composed circuit to execute, qb is the number of qubits per circuit, shots is the number of shots per circut, provider is the provider of the circuit, urls is the array with data of each circuit (url, num_qubits, shots, user, circuit_name)
#         """
#         Executes the circuit in the selected provider

#         Args:
#             data (dict): The data of the circuit to execute            
#             qb (list): The number of qubits per circuit            
#             shots (list): The number of shots per circuit
#             provider (str): The provider of the circuit            
#             urls (list): The data of each circuit            
#             machine (str): The machine to execute the circuit

#         Raises:
#             Exception: If an error occurs during the execution of the circuit
#         """

#         circuit = ''
#         for data in json.loads(data)['code']:
#             circuit = circuit + data + '\n'
        
#         loc = {}
#         if provider == 'ibm':
#             loc['circuit'] = self.executeCircuitIBM.code_to_circuit_ibm(circuit)
#         else:
#             loc['circuit'] = code_to_circuit_aws(circuit)


#         #circuit = 'def circ():\n'
#         #f = json.loads(data)
#         #for line in f['code']: #Construir el circuito según lo obtenido del traductor
#         #    circuit = circuit + '\t' + line + '\n'
# #
#         #circuit = circuit + 'circuit = circ()'
# #
#         #print(circuit)
# #
#         #loc = {}
#         #exec(circuit,globals(),loc) #Recuperar el objeto circuito que se obtiene, cuidado porque si el código del circuito no está controlado, esto es muy peligroso
#         # Aquí se podría comprobar la mejor máquina para ejecutar el circuito
#         print('_____________________________________________________________________')
#         #print(loc['circuit'])
#         print('_____________________________________________________________________')
#         try:
#             if provider == 'ibm':
#                 initial_layout = self._compose_initial_layout(urls, layout_fisico)
#                 #backend = least_busy_backend_ibm(sum(qb))
#                 # TODO escoger el backend más adecuado para el circuito
#                 #counts = runIBM(self.machine_ibm,loc['circuit'],max(shots)) #Ejecutar el circuito y obtener el resultado
#                 counts = self.executeCircuitIBM.runIBM_save(machine,loc['circuit'],max(shots),[url[3] for url in urls],qb,[url[4] for url in urls], initial_layout=initial_layout) #Ejecutar el circuito y obtener el resultado
#             else:
#                 counts = runAWS_save(machine,loc['circuit'],max(shots),[url[3] for url in urls],qb,[url[4] for url in urls],'') #Ejecutar el circuito y obtener el resultado
#         except Exception as e:
#             print(f"Error executing circuit: {e}")

#         #print(counts.items())

#         data = {"counts": counts, "shots": shots, "provider": provider, "qb": qb, "users": [url[3] for url in urls], "circuit_names": [url[4] for url in urls]}

#         requests.post(self.unscheduler, json=data)


    def executeCircuit(
    self,
    data: dict,
    qb: list,
    shots: list,
    provider: str,
    urls: list,
    machine: str,
    layout_fisico: dict | list | None = None
) -> None:

        """
        Executes the circuit in the selected provider.
        Compatible with both vertical and horizontal batching.
        """

        # -------------------------------
        # 1️⃣ Reconstrucción del código
        # -------------------------------
        circuit_code = ''
        for line in json.loads(data)['code']:
            circuit_code += line + '\n'

        # -------------------------------
        # 2️⃣ Conversión a objeto circuito
        # -------------------------------
        try:
            if provider == 'ibm':
                circuit_obj = self.executeCircuitIBM.code_to_circuit_ibm(circuit_code)
            else:
                circuit_obj = code_to_circuit_aws(circuit_code)
        except Exception as e:
            print(f"❌ Error parsing circuit code: {e}")
            return   # 👈 IMPORTANTE: salir si falla aquí

        print('_____________________________________________________________________')
        print(circuit_obj)
        print('_____________________________________________________________________')

        # -------------------------------
        # 3️⃣ Ejecución real
        # -------------------------------
        try:
            if provider == 'ibm':

                # 👉 Solo construir initial_layout si existe y es dict
                if layout_fisico is not None and isinstance(layout_fisico, dict):
                    initial_layout = self._compose_initial_layout(urls, layout_fisico)
                    preserve_layout = initial_layout is not None
                elif layout_fisico is not None and isinstance(layout_fisico, list):
                    # En política híbrida, el circuito ya se construye usando índices físicos.
                    # Forzamos mapeo estricto identidad para que IBM use esos mismos qubits.
                    initial_layout = list(range(circuit_obj.num_qubits))
                    preserve_layout = True
                else:
                    initial_layout = None
                    preserve_layout = False

                try:
                    ibm_result = self.executeCircuitIBM.runIBM_save(
                        machine,
                        circuit_obj,
                        max(shots),
                        [url[3] for url in urls],  # users
                        qb,
                        [url[4] for url in urls],  # circuit names
                        initial_layout=initial_layout,
                        preserve_layout=preserve_layout
                    )
                except Exception as strict_error:
                    if preserve_layout:
                        print(f"⚠️ Layout estricto no enrutable. Reintentando con routing IBM: {strict_error}")
                        ibm_result = self.executeCircuitIBM.runIBM_save(
                            machine,
                            circuit_obj,
                            max(shots),
                            [url[3] for url in urls],
                            qb,
                            [url[4] for url in urls],
                            initial_layout=initial_layout,
                            preserve_layout=False
                        )
                    else:
                        raise

                if isinstance(ibm_result, tuple):
                    counts, execution_metadata = ibm_result
                else:
                    counts = ibm_result
                    execution_metadata = {}

                if isinstance(layout_fisico, list):
                    virtual_to_physical = execution_metadata.get("virtual_to_physical", [])
                    job_id = execution_metadata.get("job_id")
                    preserve_used = execution_metadata.get("preserve_layout")
                    if virtual_to_physical:
                        self.log_hibrido_layout_real(layout_fisico, virtual_to_physical, job_id, preserve_used)

            else:
                counts = runAWS_save(
                    machine,
                    circuit_obj,
                    max(shots),
                    [url[3] for url in urls],
                    qb,
                    [url[4] for url in urls],
                    ''
                )

        except Exception as e:
            print(f"❌ Error executing circuit on provider: {e}")
            return   # 👈 MUY IMPORTANTE: evitar usar counts si falla

        # -------------------------------
        # 4️⃣ Envío al unscheduler
        # -------------------------------
        result_payload = {
            "counts": counts,
            "shots": shots,
            "provider": provider,
            "qb": qb,
            "users": [url[3] for url in urls],
            "circuit_names": [url[4] for url in urls]
        }

        try:
            requests.post(self.unscheduler, json=result_payload)
        except Exception as e:
            print(f"⚠️ Error sending results to unscheduler: {e}")

    def most_repetitive(self, array:list) -> int: #Check the most repetitive element in an array and if there are more than one, return the smallest
        """
        Returns the most repetitive element in an array

        Args:
            array (list): The array to check
        
        Returns:
            int: The most repetitive element in the array
        """
        count_dict = {}
        for element in array: #Hashing the elements and counting them
            if element in count_dict:
                count_dict[element] += 1
            else:
                count_dict[element] = 1

        max_count = 0
        max_element = None
        for element, count in count_dict.items(): #Simple search for the higher element in the hash. If two elements have the same count, the smallest is returned
            if count > max_count or (count == max_count and element < max_element):
                max_count = count
                max_element = element

        return max_element


    #def create_circuit(self, urls: list, code: list, qb: list, provider: str) -> None:

    
    def create_circuit(self, urls: list, code: list, qb: list, provider: str) -> None:

        """
        Creates the circuit with barriers between individual circuits and batches.
        """
        composition_qubits = 0
        composition_classical_registers = 0
        max_qb = max(url[1] for url in urls) #Get the maximum number of qubits in the urls
        total_classical_registers = sum(url[1] for url in urls) #Get the total number of qubits in the urls

        if provider == 'ibm':
            # Preámbulo para IBM
            code.insert(0, "circuit = QuantumCircuit(qreg_q, creg_c)")
            code.insert(0, f"creg_c = ClassicalRegister({total_classical_registers}, 'c')")
            code.insert(0, f"qreg_q = QuantumRegister({max_qb}, 'q')")
            code.insert(0, "from numpy import pi")
            code.insert(0, "import numpy as np")
            code.insert(0, "from qiskit import QuantumRegister, ClassicalRegister, QuantumCircuit")
            code.insert(0, "from qiskit.circuit.library import MCXGate, MCMT, XGate, YGate, ZGate")

        elif provider == 'aws':
            # Preámbulo para AWS
            code.insert(0, "circuit = Circuit()")
            code.insert(0, "from numpy import pi")
            code.insert(0, "import numpy as np")
            code.insert(0, "from collections import Counter")
            code.insert(0, "from braket.circuits import Circuit")

        normalized_urls = urls
        if urls and len(urls[0]) >= 7:
            normalized_urls = [(urls, sum(url[1] for url in urls), 1)]

        for batch_idx, batch in enumerate(normalized_urls):
            urls_batch, sumQb, batchNr = batch
            print("DEBUG urls_batch:", urls_batch)

            for url, num_qubits, shots, uid, filename, lineno, flag in urls_batch:
                if 'algassert' in url:
                    try:
                        x = requests.post(self.translator + provider + '/individual', json={'url': url, 'd': composition_qubits})
                        data = json.loads(x.text)
                        for elem in data['code']:
                            code.append(elem)
                    except Exception as e:
                        print(f"Error translating circuit {url}: {e}")
                        continue
                else:
                    lines = url.split('\n')
                    for line in lines:
                        if provider == 'ibm':
                            line = line.replace('qreg_q[', f'qreg_q[{composition_qubits}+')
                            line = line.replace('creg_c[', f'creg_c[{composition_classical_registers}+')
                        elif provider == 'aws':
                            gate_name = re.search(r'circuit\.(.*?)\(', line).group(1) if 'circuit.' in line else None
                            if gate_name in ['rx', 'ry', 'rz', 'gpi', 'gpi2', 'phaseshift']:
                                line = re.sub(rf'{gate_name}\(\s*(\d+)', lambda m: f"{gate_name}({int(m.group(1)) + composition_qubits}", line, count=1)
                            elif gate_name in ['xx', 'yy', 'zz', 'ms'] or 'cphase' in gate_name:
                                line = re.sub(rf'{gate_name}\((\d+),\s*(\d+)', lambda m: f"{gate_name}({int(m.group(1)) + composition_qubits},{int(m.group(2)) + composition_qubits}", line, count=1)
                            else:
                                line = re.sub(r'(\d+)', lambda m: str(int(m.group(1)) + composition_qubits), line)
                        code.append(line)

                # Añadir barrera después de cada circuito individual (solo para IBM)
                #if provider == 'ibm' and url_idx < len(urls) - 1:
                #    code.append(f"circuit.barrier(range({composition_qubits}, {composition_qubits + num_qubits}))")

                composition_qubits += num_qubits
                composition_classical_registers += num_qubits

                qb.append(num_qubits)


            if provider == 'ibm' and batch_idx < len(normalized_urls) - 1:
                code.append("circuit.barrier()")
                for i in range(composition_qubits):
                    code.append(f"circuit.reset(qreg_q[{i}])")
            composition_qubits = 0

        # Barrera global al final (para separar batches en IBM)
        
            

        code.append("return circuit")

   
    # def create_circuit_horizontal(self, all_batches_layout, code, qb, provider):
    #     if not all_batches_layout:
    #         return

    #     print("🧱 Construyendo circuito horizontal (Mapping de Grafos + Capas Temporales)...")

    #     # 1️⃣ Calcular qubits físicos totales necesarios (el máximo índice usado en el chip)
    #     max_physical_qubit = 0
    #     for capa in all_batches_layout:
    #         layout = capa["layout"]
    #         for phys_qubits in layout.values():
    #             max_physical_qubit = max(max_physical_qubit, max(phys_qubits))

    #     total_physical_qubits = max_physical_qubit + 1
    #     qb.append(total_physical_qubits)

    #     # 2️⃣ Preámbulo (Idéntico a tu política anterior para mantener compatibilidad)
    #     if provider == 'ibm':
    #         code.append("from qiskit import QuantumRegister, ClassicalRegister, QuantumCircuit")
    #         code.append("from qiskit.circuit.library import MCXGate, MCMT, XGate, YGate, ZGate")
    #         code.append("import numpy as np")
    #         code.append("from numpy import pi")
    #         code.append(f"qreg_q = QuantumRegister({total_physical_qubits}, 'q')")
    #         code.append(f"creg_c = ClassicalRegister({total_physical_qubits}, 'c')")
    #         code.append("circuit = QuantumCircuit(qreg_q, creg_c)")

    #     # 3️⃣ Construcción por capas temporales
    #     for idx, capa in enumerate(all_batches_layout):
    #         print(f"📦 Procesando capa horizontal {idx+1}")
    #         layout = capa["layout"]
    #         circuitos_info = capa["circuitos_info"]

    #         for circuit_id in layout:
    #             if circuit_id not in circuitos_info: continue
                
    #             physical_mapping = layout[circuit_id]
    #             raw_circuit_code = circuitos_info[circuit_id]["code"]
    #             num_logical_qb = circuitos_info[circuit_id]["qb"]
                
    #             # Dividir código en líneas
    #             lines = raw_circuit_code.split('\n')

    #             for line in lines:
    #                 # Omitir definiciones que ya están en el preámbulo o que romperían el flujo
    #                 if any(x in line for x in ["QuantumCircuit", "import", "return", "ClassicalRegister", "QuantumRegister", "qc ="]):
    #                     continue
                    
    #                 new_line = line
    #                 # Mapeo de qubits lógicos -> físicos mediante Regex
    #                 # Buscamos patrones como qreg_q[0] o q[0] y los convertimos a qreg_q[Fisico]
    #                 indices_logicos = sorted(range(num_logical_qb), reverse=True)
    #                 for l_idx in indices_logicos:
    #                     p_idx = physical_mapping[l_idx]
    #                     # Detecta cualquier variable seguida de [indice]
    #                     pattern = r'[a-zA-Z_][a-zA-Z0-9_]*\s*\[\s*' + str(l_idx) + r'\s*\]'
    #                     new_line = re.sub(pattern, f"qreg_q[{p_idx}]", new_line)

    #                 # Omitimos medidas individuales (las haremos globales por capa o al final)
    #                 if "measure" in new_line.lower():
    #                     continue

    #                 if new_line.strip():
    #                     code.append(new_line)

    #         # 4️⃣ Sincronización: Barrier + Reset (Solo si hay más capas después)
    #         if idx < len(all_batches_layout) - 1:
    #             code.append("circuit.barrier()")
    #             # Reseteamos solo los qubits que se usaron en esta capa para eficiencia, o todos:
    #             for q_idx in range(total_physical_qubits):
    #                 code.append(f"circuit.reset(qreg_q[{q_idx}])")

    #     # 5️⃣ Medición final global
    #     code.append("circuit.barrier()")
    #     for i in range(total_physical_qubits):
    #         code.append(f"circuit.measure(qreg_q[{i}], creg_c[{i}])")

    #     code.append("return circuit")

     #ESTABA PERFECTO pero era reseteando todos los qubit
    # def create_circuit_horizontal(self, all_batches_layout, code, qb, provider):
    #     if not all_batches_layout:
    #         return

    #     print("🧱 Construyendo circuito horizontal (Circuito -> Measure -> Barrier -> Reset)...")

    #     # 1️⃣ Calcular qubits físicos totales
    #     max_physical_qubit = 0
    #     for capa in all_batches_layout:
    #         layout = capa["layout"]
    #         for phys_qubits in layout.values():
    #             max_physical_qubit = max(max_physical_qubit, max(phys_qubits))

    #     total_physical_qubits = max_physical_qubit + 1
    #     qb.append(total_physical_qubits)

    #     # 2️⃣ Preámbulo IBM
    #     if provider == 'ibm':
    #         code.insert(0, "circuit = QuantumCircuit(qreg_q, creg_c)")
    #         code.insert(0, f"creg_c = ClassicalRegister({total_physical_qubits}, 'c')")
    #         code.insert(0, f"qreg_q = QuantumRegister({total_physical_qubits}, 'q')")
    #         code.insert(0, "from qiskit import QuantumRegister, ClassicalRegister, QuantumCircuit")
    #         code.insert(0, "from qiskit.circuit.library import MCXGate, MCMT, XGate, YGate, ZGate")
    #         code.insert(0, "import numpy as np")
    #         code.insert(0, "from numpy import pi")

    #     # 3️⃣ Construcción por capas
    #     for idx, capa in enumerate(all_batches_layout):
    #         print(f"📦 Procesando capa horizontal {idx+1}")
    #         layout = capa["layout"]
    #         circuitos_info = capa["circuitos_info"]

    #         # --- A: Puertas y Mediciones de los circuitos de la capa ---
    #         for circuit_id in layout:
    #             if circuit_id not in circuitos_info:
    #                 continue
                    
    #             physical_mapping = layout[circuit_id]
    #             raw_code = circuitos_info[circuit_id]["code"]
    #             num_qb = circuitos_info[circuit_id]["qb"]
    #             circuit_lines = raw_code.split('\n')

    #             mapped_slice = physical_mapping[:num_qb] if isinstance(physical_mapping, list) else physical_mapping
    #             if isinstance(mapped_slice, list) and len(mapped_slice) != len(set(mapped_slice)):
    #                 print(
    #                     f"⚠️ Layout con qubits físicos duplicados para circuito {circuit_id}: {mapped_slice}. "
    #                     "Se omitirán instrucciones inválidas tras el mapeo."
    #                 )

    #             for line in circuit_lines:
    #                 # Limpieza de definiciones
    #                 if any(x in line for x in ["QuantumCircuit", "import", "return", "ClassicalRegister", "QuantumRegister", "qc ="]):
    #                     continue
                    
    #                 new_line = line
    #                 # Reemplazo de índices lógicos a físicos (tanto para puertas como para medidas)
    #                 indices_logicos = sorted(range(num_qb), reverse=True)
    #                 for logical_idx in indices_logicos:
    #                     phys_idx = physical_mapping[logical_idx]
                        
    #                     # 1. Reemplazar solo registros cuánticos: qreg_q[0] / q[0] -> qreg_q[phys]
    #                     pattern_q = r'\b(?:qreg_q|q)\s*\[\s*' + str(logical_idx) + r'\s*\]'
    #                     new_line = re.sub(pattern_q, f"qreg_q[{phys_idx}]", new_line)
                        
    #                     # 2. Reemplazar registros clásicos: creg_c[0] / c[0] -> creg_c[phys]
    #                     # Esto asegura que el resultado del qubit físico se guarde en su bit correspondiente
    #                     pattern_c = r'\b(?:creg_c|c)\s*\[\s*' + str(logical_idx) + r'\s*\]'
    #                     new_line = re.sub(pattern_c, f"creg_c[{phys_idx}]", new_line)

    #                 # Evitar puertas multi-qubit inválidas como cx(q[i], q[i]) tras el mapeo lógico->físico.
    #                 # Si aparecen qubits físicos repetidos en la misma instrucción cuántica, se omite.
    #                 gate_match = re.match(r'\s*circuit\.(\w+)\s*\((.*)\)\s*$', new_line)
    #                 if gate_match:
    #                     gate_name = gate_match.group(1)
    #                     gate_args = gate_match.group(2)
    #                     mapped_qubits = re.findall(r'qreg_q\[\s*(\d+)\s*\]', gate_args)
    #                     if len(mapped_qubits) >= 2 and len(mapped_qubits) != len(set(mapped_qubits)):
    #                         print(
    #                             f"⚠️ Instrucción omitida por qubits duplicados tras mapeo en capa {idx+1}, "
    #                             f"circuito {circuit_id}: {new_line.strip()}"
    #                         )
    #                         continue

    #                 if new_line.strip():
    #                     code.append(new_line)

    #         # --- B: Barrera y Reset (Sincronización al final de la capa) ---
    #         # Añadimos una barrera siempre después de las medidas de la capa para separar del reset
    #         code.append("circuit.barrier()")
            
    #         # Si NO es la última capa, reseteamos para poder reutilizar los qubits
    #         if idx < len(all_batches_layout) - 1:
    #             for q in range(total_physical_qubits):
    #                 code.append(f"circuit.reset(qreg_q[{q}])")
    #             # Barrera opcional después del reset para mayor claridad visual
    #             code.append("circuit.barrier()")

    #     code.append("return circuit")
    #     print("✅ Circuito horizontal construido con mediciones intercaladas.")

    def create_circuit_horizontal(self, all_batches_layout, code, qb, provider):
        if not all_batches_layout:
            return

        print("🧱 Construyendo circuito horizontal acumulativo (Estilo antiguo)...")

        # 1️⃣ Calcular qubits físicos máximos para el QuantumRegister
        max_physical_qubit = 0
        total_mediciones_acumuladas = 0
        for capa in all_batches_layout:
            layout = capa["layout"]
            for circuit_id, phys_qubits in layout.items():
                max_physical_qubit = max(max_physical_qubit, max(phys_qubits))
                total_mediciones_acumuladas += len(phys_qubits) # Sumamos todos los bits necesarios

        total_physical_qubits = max_physical_qubit + 1
        qb.append(total_physical_qubits)

        # 2️⃣ Preámbulo IBM: Registro cuántico fijo, Registro clásico GIGANTE (acumulativo)
        if provider == 'ibm':
            code.insert(0, "circuit = QuantumCircuit(qreg_q, creg_c)")
            code.insert(0, f"creg_c = ClassicalRegister({total_mediciones_acumuladas}, 'c')")
            code.insert(0, f"qreg_q = QuantumRegister({total_physical_qubits}, 'q')")
            code.insert(0, "from qiskit import QuantumRegister, ClassicalRegister, QuantumCircuit")
            code.insert(0, "import numpy as np")
            code.insert(0, "from numpy import pi")

        # 3️⃣ Construcción por capas
        current_classical_offset = 0 # Esta variable imita tu código antiguo

        for idx, capa in enumerate(all_batches_layout):
            layout = capa["layout"]
            circuitos_info = capa["circuitos_info"]
            qubits_fisicos_usados_en_esta_capa = set()
            mediciones_en_esta_capa = 0

            for circuit_id in layout:
                if circuit_id not in circuitos_info:
                    continue
                    
                physical_mapping = layout[circuit_id]
                raw_code = circuitos_info[circuit_id]["code"]
                num_qb = circuitos_info[circuit_id]["qb"]
                circuit_lines = raw_code.split('\n')

                # Mapeo lógico -> físico
                indices_logicos = sorted(range(num_qb), reverse=True)
                for line in circuit_lines:
                    if any(x in line for x in ["QuantumCircuit", "import", "return", "ClassicalRegister", "QuantumRegister", "qc ="]):
                        continue
                    
                    new_line = line
                    for logical_idx in indices_logicos:
                        phys_idx = physical_mapping[logical_idx]
                        qubits_fisicos_usados_en_esta_capa.add(phys_idx)
                        
                        # REEMPLAZO CUÁNTICO (fijo al qubit físico)
                        new_line = re.sub(r'\b(?:qreg_q|q)\[\s*' + str(logical_idx) + r'\s*\]', f"qreg_q[{phys_idx}]", new_line)
                        
                        # REEMPLAZO CLÁSICO (acumulativo como en tu código viejo)
                        # En lugar de usar phys_idx, usamos el offset global para que no colisionen
                        target_c_bit = current_classical_offset + logical_idx
                        new_line = re.sub(r'\b(?:creg_c|c)\[\s*' + str(logical_idx) + r'\s*\]', f"creg_c[{target_c_bit}]", new_line)

                    # Validar duplicados físicos en la misma instrucción
                    qubits_en_linea = re.findall(r'qreg_q\[\s*(\d+)\s*\]', new_line)
                    if len(qubits_en_linea) != len(set(qubits_en_linea)):
                        continue

                    if new_line.strip():
                        code.append(new_line)
                
                # Al final de cada circuito dentro del batch, el offset avanza
                current_classical_offset += num_qb

            # --- B: Barrera y Reset Quirúrgico ---
            code.append("circuit.barrier()")
            
            if idx < len(all_batches_layout) - 1:
                # Reseteamos solo los qubits que han trabajado en esta capa
                for q_fisico in sorted(qubits_fisicos_usados_en_esta_capa):
                    code.append(f"circuit.reset(qreg_q[{q_fisico}])")
                code.append("circuit.barrier()")

        code.append("return circuit")
    #ESTA BIEN, RESETEA SOLO LOS QUBITS QUE SE HAN UTILIZADO EN EL BATCH ANTERIOR
    # def create_circuit_horizontal(self, all_batches_layout, code, qb, provider):
    #     if not all_batches_layout:
    #         return

    #     print("🧱 Construyendo circuito horizontal (Circuito -> Measure -> Barrier -> Reset)...")

    #     # 1️⃣ Calcular qubits físicos totales
    #     max_physical_qubit = 0
    #     for capa in all_batches_layout:
    #         layout = capa["layout"]
    #         for phys_qubits in layout.values():
    #             max_physical_qubit = max(max_physical_qubit, max(phys_qubits))
    #     total_physical_qubits = max_physical_qubit + 1
    #     qb.append(total_physical_qubits)

    #     # 2️⃣ Preámbulo IBM
    #     if provider == 'ibm':
    #         code.insert(0, "circuit = QuantumCircuit(qreg_q, creg_c)")
    #         code.insert(0, f"creg_c = ClassicalRegister({total_physical_qubits}, 'c')")
    #         code.insert(0, f"qreg_q = QuantumRegister({total_physical_qubits}, 'q')")
    #         code.insert(0, "from qiskit import QuantumRegister, ClassicalRegister, QuantumCircuit")
    #         code.insert(0, "from qiskit.circuit.library import MCXGate, MCMT, XGate, YGate, ZGate")
    #         code.insert(0, "import numpy as np")
    #         code.insert(0, "from numpy import pi")

    #     # 3️⃣ Construcción por capas
    #     for idx, capa in enumerate(all_batches_layout):
    #         print(f"📦 Procesando capa horizontal {idx+1}")
    #         layout = capa["layout"]
    #         circuitos_info = capa["circuitos_info"]

    #         # --- A: Puertas y Mediciones de los circuitos de la capa ---
    #         for circuit_id in layout:
    #             if circuit_id not in circuitos_info:
    #                 continue
                    
    #             physical_mapping = layout[circuit_id]
    #             raw_code = circuitos_info[circuit_id]["code"]
    #             num_qb = circuitos_info[circuit_id]["qb"]
    #             circuit_lines = raw_code.split('\n')

    #             mapped_slice = physical_mapping[:num_qb] if isinstance(physical_mapping, list) else physical_mapping
    #             if isinstance(mapped_slice, list) and len(mapped_slice) != len(set(mapped_slice)):
    #                 print(
    #                     f"⚠️ Layout con qubits físicos duplicados para circuito {circuit_id}: {mapped_slice}. "
    #                     "Se omitirán instrucciones inválidas tras el mapeo."
    #                 )

    #             for line in circuit_lines:
    #                 # Limpieza de definiciones
    #                 if any(x in line for x in ["QuantumCircuit", "import", "return", "ClassicalRegister", "QuantumRegister", "qc ="]):
    #                     continue
                    
    #                 new_line = line
    #                 # Reemplazo de índices lógicos a físicos (tanto para puertas como para medidas)
    #                 indices_logicos = sorted(range(num_qb), reverse=True)
    #                 for logical_idx in indices_logicos:
    #                     phys_idx = physical_mapping[logical_idx]
                        
    #                     # Reemplazar registros cuánticos
    #                     pattern_q = r'\b(?:qreg_q|q)\s*\[\s*' + str(logical_idx) + r'\s*\]'
    #                     new_line = re.sub(pattern_q, f"qreg_q[{phys_idx}]", new_line)
                        
    #                     # Reemplazar registros clásicos
    #                     pattern_c = r'\b(?:creg_c|c)\s*\[\s*' + str(logical_idx) + r'\s*\]'
    #                     new_line = re.sub(pattern_c, f"creg_c[{phys_idx}]", new_line)

    #                 # Evitar puertas multi-qubit inválidas
    #                 gate_match = re.match(r'\s*circuit\.(\w+)\s*\((.*)\)\s*$', new_line)
    #                 if gate_match:
    #                     gate_args = gate_match.group(2)
    #                     mapped_qubits = re.findall(r'qreg_q\[\s*(\d+)\s*\]', gate_args)
    #                     if len(mapped_qubits) >= 2 and len(mapped_qubits) != len(set(mapped_qubits)):
    #                         print(
    #                             f"⚠️ Instrucción omitida por qubits duplicados tras mapeo en capa {idx+1}, "
    #                             f"circuito {circuit_id}: {new_line.strip()}"
    #                         )
    #                         continue

    #                 if new_line.strip():
    #                     code.append(new_line)

    #         # --- B: Barrera y Reset (Solo qubits usados) ---
    #         code.append("circuit.barrier()")

    #         if idx < len(all_batches_layout) - 1:
    #             # Obtener qubits usados en esta capa
    #             used_qubits = set()
    #             for circuit_id in layout:
    #                 physical_mapping = layout[circuit_id]
    #                 num_qb = circuitos_info[circuit_id]["qb"]
    #                 mapped_slice = physical_mapping[:num_qb] if isinstance(physical_mapping, list) else physical_mapping
    #                 used_qubits.update(mapped_slice)

    #             for q in sorted(used_qubits):
    #                 code.append(f"circuit.reset(qreg_q[{q}])")

    #             code.append("circuit.barrier()")  # opcional después del reset

    #     code.append("return circuit")
    #     print("✅ Circuito horizontal construido con mediciones intercaladas y resets selectivos.")


   


    def read_circuit(self, circuit_name):
        """
        Busca el código del circuito. 
        Ajusta la lógica según dónde guardes tus archivos .py
        """
        # Si circuit_name es una ruta completa o solo el nombre del archivo
        import os
        
        # Ajusta esta ruta a la carpeta donde residen tus archivos de circuitos
        base_path = "./circuitos_originales" 
        path = os.path.join(base_path, circuit_name)
        
        if not os.path.exists(path):
            # Intento alternativo si el nombre ya es una ruta
            path = circuit_name

        try:
            with open(path, 'r') as f:
                lines = f.readlines()
            
            # Intentamos detectar el número de qubits buscando QuantumRegister o similares
            num_qb = 0
            for line in lines:
                if 'QuantumRegister' in line:
                    # Extrae el número dentro del paréntesis
                    match = re.search(r'QuantumRegister\((\d+)', line)
                    if match:
                        num_qb = int(match.group(1))
                        break
            
            return lines, num_qb
        except Exception as e:
            print(f"❌ Error leyendo el archivo {circuit_name}: {e}")
            return [], 0


    def send_combined_graph_horizontal(self, queue, max_qubits, provider, executeCircuit, machine):

        if not queue:
            print("\n✅ No hay circuitos en la cola.")
            return

        print(f"🚀 Iniciando política Híbrida (Grafo + Horizontal) en {machine}")

        # ------------------------------------------------------------
        # 📂 CONFIGURACIÓN DE SALIDA info.txt
        # ------------------------------------------------------------
        if not hasattr(self, "current_classical_index_global"):
            self.current_classical_index_global = 0

        if not hasattr(self, "iteracion_tiempo"):
            self.iteracion_tiempo = 1

        carpeta_resultados = os.path.join(os.getcwd(), "resultadosTodos")
        carpeta_info = os.path.join(carpeta_resultados, "resultadosIBM_1_Torino_repeticion_3")

        os.makedirs(carpeta_info, exist_ok=True)

        info_file = os.path.join(carpeta_info, "info_1_Torino_3.txt")

        if self.iteracion_tiempo == 1 and not os.path.exists(info_file):
            with open(info_file, "w") as f:
                f.write("=== Información de circuitos ejecutados ===\n")

        # ------------------------------------------------------------
        # 1️⃣ VARIABLES DE CONTROL
        # ------------------------------------------------------------

        remaining_queue = list(queue)

        all_batches_layout = []

        circuitos_para_ejecutar = []

        total_qubits_acumulados = 0

        LIMITE_GLOBAL_QUBITS = 70000

        iteracion_horizontal = 0

        backend_name = self.machine_ibm if provider == 'ibm' else None

        distancia_fija = None

        # ------------------------------------------------------------
        # LOOP PRINCIPAL
        # ------------------------------------------------------------

        while remaining_queue and total_qubits_acumulados < LIMITE_GLOBAL_QUBITS:

            iteracion_horizontal += 1

            if distancia_fija is None:
                tamanos_iniciales = [item[1] for item in remaining_queue]
                media = sum(tamanos_iniciales) / len(tamanos_iniciales)
                distancia_fija = math.ceil(media)

                print(f"🔒 Distancia congelada para todo el Job: {distancia_fija}")

            formatted_queue = CircuitQueue()

            for item in remaining_queue:

                edges = self.extract_edges_from_circuit(item[0])

                formatted_queue.add_circuit(
                    circuit_id=str(item[3]),
                    required_qubits=item[1],
                    edges=edges
                )

            cola_procesada, layout_fisico, _ = select_best_qubits_persistent(
                circuits=formatted_queue,
                provider=provider,
                backend_name=backend_name,
                noise_threshold=None,
                max_time_seconds=30,
                fixed_distance=distancia_fija
            )

            if not cola_procesada:
                break

            seleccionados_ids = {str(s['id']) for s in cola_procesada}

            capa_actual = []

            for item in list(remaining_queue):

                if str(item[3]) in seleccionados_ids:

                    capa_actual.append(item)

                    circuitos_para_ejecutar.append(item)

                    total_qubits_acumulados += item[1]

                    remaining_queue.remove(item)

                    # ------------------------------------------------------------
                    # 📝 GUARDAR INFO DEL CIRCUITO (info_506.txt)
                    # ------------------------------------------------------------

                    circuito_nombre = item[4]
                    num_qubits = item[1]

                    reg_inicio = f"c{self.current_classical_index_global}"
                    reg_final = f"c{self.current_classical_index_global + num_qubits - 1}"

                    with open(info_file, "a") as info:
                        info.write(
                            f"Circuito: {circuito_nombre} | "
                            f"Registros clásicos: {reg_inicio} - {reg_final} | "
                            f"Iteración: {self.iteracion_tiempo} | "
                            f"Batch: {iteracion_horizontal}\n"
                        )

                    self.current_classical_index_global += num_qubits

            all_batches_layout.append({

                'iteracion_temporal': iteracion_horizontal,

                'layout': layout_fisico,

                'circuitos_info': {

                    str(item[3]): {

                        "code": item[0],
                        "qb": item[1],
                        "name": item[4]

                    } for item in capa_actual

                },

                'distancia_usada': distancia_fija
            })

            print(
                f"✅ Verificación Capa {iteracion_horizontal}: "
                f"Circuitos asignados: {list(all_batches_layout[-1]['circuitos_info'].keys())}"
            )

            print(f"📦 Capa {iteracion_horizontal}: Colocados {len(capa_actual)} circuitos.")

        # ------------------------------------------------------------
        # 5️⃣ EJECUCIÓN FINAL
        # ------------------------------------------------------------

        if circuitos_para_ejecutar:

            print(f"⚡ Ejecutando Job compuesto por {len(all_batches_layout)} capas horizontales.")

            print("DEBUG: Voy a guardar resultados híbridos")

            self.log_hibrido_resultados(all_batches_layout, total_qubits_acumulados)

            code, qb = [], []

            shotsUsr = [item[2] for item in circuitos_para_ejecutar]

            self.create_circuit_horizontal(all_batches_layout, code, qb, provider)

            data = {"code": code}

            layout_fisico = all_batches_layout if all_batches_layout else None

            executeCircuit(
                json.dumps(data),
                qb,
                shotsUsr,
                provider,
                circuitos_para_ejecutar,
                machine,
                layout_fisico
            )

            queue[:] = remaining_queue

            self.iteracion_tiempo += 1

        else:
            print("⚠️ No se pudo colocar ningún circuito.")


    


    def log_hibrido_resultados(self, layouts, total_qb):
        os.makedirs("./resultadosTodos", exist_ok=True)

        with open("./resultadosTodos/resultadosIBM_1_Torino_repeticion_3/Salida_1_Torino_3.txt", 'a', encoding='utf-8') as f:
            f.write("\n=====================================================\n")
            f.write("🚀 Nueva Ejecución Híbrida (Grafo + Horizontal)\n")
            f.write("=====================================================\n")
            f.write(f"Total Qubits acumulados: {total_qb}\n")
            f.write(f"Total Capas Horizontales: {len(layouts)}\n\n")

            for capa in layouts:
                f.write(f"-----------------------------------------------------\n")
                f.write(f"Capa Temporal: {capa['iteracion_temporal']}\n")
                f.write(f"Distancia usada: {capa.get('distancia_usada')}\n")

                circuit_ids = list(capa['circuitos_info'].keys())
                circuit_names = [
                    capa['circuitos_info'][cid]['name']
                    for cid in circuit_ids
                ]

                f.write(f"Circuitos asignados (IDs): {circuit_ids}\n")
                f.write(f"Circuitos (nombres): {circuit_names}\n")
                f.write(f"Layout físico:\n")

                for cid, phys in capa['layout'].items():
                    f.write(f"   - Circuito {cid} → Qubits físicos {phys}\n")

                f.write("\n")

    def log_hibrido_layout_real(self, layouts, virtual_to_physical, job_id=None, preserve_layout_used=None):
        os.makedirs("./resultadosTodos", exist_ok=True)

        with open("./resultadosTodos/resultadosIBM_1_Torino_repeticion_3/Salida_1_Torino_3.txt", 'a', encoding='utf-8') as f:
            f.write("Layout IBM real (post-transpile):\n")
            if job_id:
                f.write(f"Job IBM: {job_id}\n")
            if preserve_layout_used is not None:
                modo = "ESTRICTO (sin routing)" if preserve_layout_used else "ENRUTADO (con routing)"
                f.write(f"Modo de transpilación IBM: {modo}\n")

            for capa in layouts:
                f.write(f"  Capa Temporal {capa['iteracion_temporal']}:\n")
                for cid, planned_phys in capa['layout'].items():
                    real_phys = [
                        virtual_to_physical[q] if isinstance(q, int) and q < len(virtual_to_physical) else q
                        for q in planned_phys
                    ]
                    f.write(f"   - Circuito {cid} → Qubits IBM reales {real_phys}\n")

            f.write("\n")


    # def log_hibrido_resultados(self, layouts, total_qb):
    #     os.makedirs("./resultados", exist_ok=True)
    #     with open("./resultados/SalidaHibrida.txt", 'a') as f:
    #         f.write(f"\n--- Nueva Ejecución Híbrida ---\n")
    #         f.write(f"Total Qubits: {total_qb}\n")
    #         for capa in layouts:
    #             # Extraemos los nombres de los circuitos desde 'circuitos_info'
    #             nombres_circuitos = [info['name'] for info in capa['circuitos_info'].values()]
                
    #             f.write(f"Capa {capa['iteracion_temporal']} | "
    #                     f"Layout: {capa['layout']} | "
    #                     f"Circuitos: {nombres_circuitos}\n")

    # def log_hibrido_resultados(self, layouts, total_qb):
    #     os.makedirs("./resultados", exist_ok=True)
    #     with open("./resultados/SalidaHibrida.txt", 'a') as f:
    #         f.write(f"\n--- Nueva Ejecución Híbrida ---\n")
    #         f.write(f"Total Qubits: {total_qb}\n")
    #         for capa in layouts:
    #             f.write(f"Capa {capa['iteracion_temporal']} | Layout: {capa['layout']} | Circuitos: {capa['circuitos']}\n")

    # def log_hibrido_resultados(self, layouts, total_qb):
    #     os.makedirs("./resultados", exist_ok=True)
    #     with open("./resultados/SalidaHibrida.txt", 'a') as f:
    #         f.write(f"\n--- Nueva Ejecución Híbrida ---\n")
    #         f.write(f"Total Qubits: {total_qb}\n")
    #         for capa in layouts:
    #             f.write(f"Capa {capa['iteracion_temporal']} | Layout: {capa['layout']} | Circuitos: {capa['circuitos']}\n")

    
    
    #ESTO ESTA BIEN
    # def send_combined_graph_horizontal(self, queue, max_qubits, provider, executeCircuit, machine):
    #     """
    #     Política Híbrida: Colocación inteligente por grafos + Extensión horizontal (Batching).
    #     Llena la máquina según conectividad, y cuando se agotan los qubits, añade una capa
    #     temporal (barrera + reset) y vuelve a empezar sobre los mismos qubits físicos.
    #     """
    #     if not queue:
    #         print("\n✅ No hay circuitos en la cola.")
    #         return

    #     print(f"🚀 Iniciando política Híbrida (Grafo + Horizontal) en {machine}")
        
    #     # 1. Preparación de variables de control
    #     remaining_queue = list(queue)
    #     all_batches_layout = [] # Guardará la info de cada "capa" horizontal
    #     circuitos_para_ejecutar = []
    #     total_qubits_acumulados = 0
    #     LIMITE_GLOBAL_QUBITS = 70000 # Límite de la política 'send' original
        
    #     iteracion_horizontal = 0
    #     backend_name = self.machine_ibm if provider == 'ibm' else None

    #     # Mientras queden circuitos y no superemos el límite de memoria del Job
    #     while remaining_queue and total_qubits_acumulados < LIMITE_GLOBAL_QUBITS:
    #         iteracion_horizontal += 1
            
    #         # Formatear lo que queda en la cola para el algoritmo de grafos
    #         formatted_queue = CircuitQueue()
    #         for item in remaining_queue:
    #             edges = self.extract_edges_from_circuit(item[0])
    #             formatted_queue.add_circuit(circuit_id=str(item[3]), required_qubits=item[1], edges=edges)

    #         # 2. Llamar al colocador (select_best_qubits_persistent)
    #         # Este nos dirá qué cabe en esta "capa" física de la máquina
    #         cola_procesada, layout_fisico, _ = select_best_qubits_persistent(
    #             circuits=formatted_queue,
    #             provider=provider,
    #             backend_name=backend_name,
    #             noise_threshold=None,
    #             max_time_seconds=30
    #         )

    #         if not cola_procesada:
    #             break # No cabe ni un circuito más o error de colocación

    #         # 3. Identificar circuitos seleccionados en esta capa
    #         seleccionados_ids = {str(s['id']) for s in cola_procesada}
            
    #         capa_actual = []
    #         for item in list(remaining_queue):
    #             if str(item[3]) in seleccionados_ids:
    #                 capa_actual.append(item)
    #                 circuitos_para_ejecutar.append(item)
    #                 total_qubits_acumulados += item[1]
    #                 remaining_queue.remove(item) # Los quitamos de la cola general

    #         # Guardamos el layout de esta capa específica
    #         all_batches_layout.append({
    #             'iteracion_temporal': iteracion_horizontal,
    #             'layout': layout_fisico,
    #             'circuitos': [item[4] for item in capa_actual]
    #         })

    #         print(f"📦 Capa {iteracion_horizontal}: Colocados {len(capa_actual)} circuitos.")

    #     # 4. Ejecución (Fuera del bucle while para que sea un solo JOB)
    #     if circuitos_para_ejecutar:
    #         print(f"⚡ Ejecutando Job compuesto por {len(all_batches_layout)} capas horizontales.")
            
    #         code, qb = [], []
    #         shotsUsr = [item[2] for item in circuitos_para_ejecutar]
            
    #         # NOTA: Tu método create_circuit debe estar preparado para recibir 
    #         # la lista de layouts o manejar las barreras/resets internamente 
    #         # basado en la estructura de capas.
            
    #         # self.create_circuit_horizontal(all_batches_layout, code, qb, provider)
            
    #         data = {"code": code}
    #         # executeCircuit(json.dumps(data), qb, shotsUsr, provider, circuitos_para_ejecutar, machine, all_batches_layout)
            
    #         # Actualizamos la cola original (pasada por referencia)
    #         queue[:] = remaining_queue
            
    #         # Log de resultados
    #         self.log_hibrido_resultados(all_batches_layout, total_qubits_acumulados)

    #     else:
    #         print("⚠️ No se pudo colocar ningún circuito.")
   
    def send(self, queue: list, max_qubits: int, provider: str, executeCircuit: Callable, machine: str) -> None:
        """
        Ejecuta batches normalmente, pero cada vez que la suma total de qubits acumulados
        supera el límite global, ejecuta inmediatamente y continúa con la siguiente tanda.
        Además, guarda información detallada de cada circuito ejecutado en 'resultadosTodos/info_1/info.txt'.
        """
        if not queue:
            print("\n✅ No hay más elementos en la cola. Programa finalizado.\n")
            return

        if not hasattr(self, "urls_ya_procesados"):
            self.urls_ya_procesados = set()

        if not hasattr(self, "current_classical_index_global"):
            self.current_classical_index_global = 0  # 🔹 contador global continuo de registros clásicos

        self.iteracion_tiempo += 1
        colas_sin_criterio = self.obtener_colas_sin_criterio(queue)

        # 🔹 Carpeta principal y subcarpeta personalizadas fuera de CARPETA_SALIDAS
        carpeta_resultados = os.path.join(os.getcwd(), "resultadosTodos")
        carpeta_info = os.path.join(carpeta_resultados, "resultadosIBM_506_batch")

        os.makedirs(carpeta_info, exist_ok=True)  # 🔹 Crea ambas carpetas si no existen

        # 🔹 Archivo de información
        info_file = os.path.join(carpeta_info, "info_506.txt")

        # 🔹 Archivo criterio_tiempo sigue en CARPETA_SALIDAS
        file_name = os.path.join(CARPETA_SALIDAS, "criterio_tiempo.txt")

        elementos_procesados_total = 0
        LIMITE_EJECUCION_QUBITS = 70000

        # 🔹 Reinicia el archivo info.txt solo la primera vez
        if self.iteracion_tiempo == 1:
            with open(info_file, "w") as f:
                f.write("=== Información de circuitos ejecutados ===\n")

        for criterio, cola_original in colas_sin_criterio.items():
            if not cola_original:
                continue

            cola = list(cola_original)
            batches = []
            sumQb_total = 0
            batch_counter = 1
            current_qubit_index = 0

            for url in list(cola):
                if url in self.urls_ya_procesados:
                    continue

                if not batches or (batches[-1][1] + url[1]) > max_qubits:
                    batches.append(([url], url[1], batch_counter))
                    batch_counter += 1
                    current_qubit_index = 0
                else:
                    batches[-1][0].append(url)
                    batches[-1] = (batches[-1][0], batches[-1][1] + url[1], batches[-1][2])

                self.urls_ya_procesados.add(url)
                if url in queue:
                    queue.remove(url)
                if url in cola_original:
                    cola_original.remove(url)

                sumQb_total += url[1]

                circuito_id = url[4]
                num_qubits = url[1]

                # 🔹 rango clásico continuo
                reg_inicio = f"c{self.current_classical_index_global}"
                reg_final = f"c{self.current_classical_index_global + num_qubits - 1}"

                # 🔹 escribir en info.txt (sin "Qubits usados")
                with open(info_file, "a") as info:
                    info.write(
                        f"Circuito: {circuito_id} | "
                        f"Registros clásicos: {reg_inicio} - {reg_final} | "
                        f"Iteración: {self.iteracion_tiempo} | Batch: {batch_counter - 1}\n"
                    )

                # avanzar índices
                self.current_classical_index_global += num_qubits
                current_qubit_index += 1

                # ⚡ Si superamos el límite global, ejecutar inmediatamente
                if sumQb_total >= LIMITE_EJECUCION_QUBITS:
                    with open(file_name, "a") as file:
                        file.write(f"\n Iteración {self.iteracion_tiempo} - Máquina: {machine} -- Límite ejecución: {LIMITE_EJECUCION_QUBITS} qubits\n")
                        for urls_batch, sumQb_b, batch_num_b in batches:
                            file.write(f"  Batch #{batch_num_b}: [")
                            for u in urls_batch:
                                file.write(f"('{u[4]}', {u[1]} qubits, shots={u[2]}), ")
                            file.write("]\n")
                            file.write(f"    Total qubits usados: {sumQb_b}\n")

                    code, qb = [], []
                    shotsUsr = [1000] * sum(len(batch[0]) for batch in batches)
                    #self.create_circuit(batches, code, qb, provider)

                    print(f"///////// EJECUTANDO ITERACIÓN {self.iteracion_tiempo} /////////")
                    data = {"code": code}
                    all_urls = [u for batch in batches for u in batch[0]]

                    #executeCircuit(json.dumps(data), qb, shotsUsr, provider, all_urls, machine)
                    elementos_procesados_total += len(all_urls)

                    # reinicios parciales
                    self.iteracion_tiempo += 1
                    batches = []
                    sumQb_total = 0
                    batch_counter = 1
                    current_qubit_index = 0

            # ⚠ ejecutar los que quedaron
            if batches:
                with open(file_name, "a") as file:
                    file.write(f"\n Iteración {self.iteracion_tiempo} - Máquina: {machine} -- Ejecución final parcial\n")
                    for urls_batch, sumQb_b, batch_num_b in batches:
                        file.write(f"  Batch #{batch_num_b}: [")
                        for u in urls_batch:
                            file.write(f"('{u[4]}', {u[1]} qubits, shots={u[2]}), ")
                        file.write("]\n")
                        file.write(f"    Total qubits usados: {sumQb_b}\n")

                code, qb = [], []
                shotsUsr = [1000] * sum(len(batch[0]) for batch in batches)
                #self.create_circuit(batches, code, qb, provider)

                print(f"///////// EJECUTANDO ITERACIÓN FINAL {self.iteracion_tiempo} /////////")
                data = {"code": code}
                all_urls = [u for batch in batches for u in batch[0]]

                #executeCircuit(json.dumps(data), qb, shotsUsr, provider, all_urls, machine)
                elementos_procesados_total += len(all_urls)

        if elementos_procesados_total == 0:
            print(f"\n⚠ Iteración {self.iteracion_tiempo} no generó batches (cola vacía o sin circuitos válidos).")
        else:
            print(f"\n✅ Iteraciones completadas. Circuitos totales procesados: {elementos_procesados_total}")
            print(f"📌 Total acumulado: {len(self.urls_ya_procesados)} circuitos únicos ejecutados.\n")


    def send_graph_placement_edges(self, queue, max_qubits, provider, executeCircuit, machine):
        """
        Política que asigna circuitos a qubits físicos usando el grafo + edges de los circuitos.
        """
        with self.islas_cuanticas_lock:
            print("Ejecutando política de Islas Cuánticas (con edges)...")
            start_time = time.process_time()

            if not queue:
                print("⚠️ La cola está vacía, deteniendo temporizador.")
                self.services['Islas_Cuanticas_Edges'].timers[provider].stop()
                return

            # Proveedor que se esta utilizando
            print(f"Proveedor seleccionado: {provider}")

            
            formatted_queue = CircuitQueue()
            for (circuit, num_qubits, shots, user, circuit_name, maxDepth, iteracion) in queue:
                #print("mostrando circuito:", circuit)
                edges = self.extract_edges_from_circuit(circuit) 
                formatted_queue.add_circuit(
                    circuit_id=str(user),
                    required_qubits=num_qubits,
                    edges=edges
                )
            print(f"Cola formateada con edges: {formatted_queue.get_queue()}")

            backend_name = self.machine_ibm if provider == 'ibm' else None
            cola_procesada, layout_fisico, placement_errors = select_best_qubits_persistent(
                circuits=formatted_queue,
                provider=provider,
                backend_name=backend_name,
                noise_threshold=None,
                max_time_seconds=60
            )
            print(f" Cola procesada: {cola_procesada}")
            print(f" Layout físico asignado: {layout_fisico}")
            if placement_errors:
                print(f" Errores de colocación: {placement_errors}")

            if not cola_procesada:
                print(" No se han seleccionado elementos, deteniendo ejecución.")
                self.services['Islas_Cuanticas_Edges'].timers[provider].stop()
                return

            seleccionados_ids = {str(s['id']) for s in cola_procesada}
            seleccionados_completos = [item for item in queue if str(item[3]) in seleccionados_ids]

            urls_for_create = [
                (circuit, num_qubits, shots, user, circuit_name, maxDepth, iteracion)
                for (circuit, num_qubits, shots, user, circuit_name, maxDepth, iteracion) in seleccionados_completos
            ]

            queue[:] = [
                (circuit, num_qubits, shots, user, circuit_name, maxDepth, iteracion + 1)
                for (circuit, num_qubits, shots, user, circuit_name, maxDepth, iteracion) in queue
                    if str(user) not in seleccionados_ids
            ]

            # if urls_for_create:
            #     total_qbits = sum(item[1] for item in urls_for_create)
            #     print(f"Suma total de qubits a ejecutar: {total_qbits}")
            #     code, qb = [], []
            #     shotsUsr = [item[2] for item in urls_for_create]
            #     self.create_circuit(urls_for_create, code, qb, provider)
            #     data = {"code": code}
            #     Thread(target=executeCircuit, args=(json.dumps(data), qb, shotsUsr, provider, urls_for_create, machine, layout_fisico)).start()

            end_time = time.process_time()
            elapsed_time = end_time - start_time
            print(f"Tiempo de ejecución de send_edges: {elapsed_time:.6f} segundos")

            # Crear carpeta de resultados si no existe
            os.makedirs("./resultados", exist_ok=True)
            
            with open("./resultados/SalidaIslasCuanticasEdges.txt", 'a') as file:
                file.write("Cola Formateada con edges:")
                file.write(str(formatted_queue))
                file.write("\n")
                file.write("Cola Seleccionada:")
                file.write(str(cola_procesada))
                file.write("\n")
                file.write("Layout Físico:")
                file.write(str(layout_fisico))
                file.write("\n")
                file.write("Tiempo Ejecucion:")
                file.write(str(elapsed_time))
                file.write("\n")

            if not queue:
                print(" Cola vacía después de ejecución, deteniendo temporizador.")
                self.services['Islas_Cuanticas_Edges'].timers[provider].stop()
            else:
                self.services['Islas_Cuanticas_Edges'].timers[provider].reset()

    def extract_edges_from_circuit(self, circuit_code: str):
        """
        Extrae las 'edges' (conexiones lógicas entre qubits) de un código Qiskit
        en formato de texto como los que tienes en la cola:
          circuit.cx(qreg_q[0], qreg_q[1])
          circuit.ccx(qreg_q[0], qreg_q[1], qreg_q[2])
          circuit.swap(qreg_q[3], qreg_q[4])
        Devuelve una lista de tuplas (q_phys_a, q_phys_b) con q_phys_a < q_phys_b.
        NO ejecuta el código del circuito.
        """
        if not circuit_code:
            return []

        edges = set()
        # Recorremos línea a línea
        for line in circuit_code.splitlines():
            line = line.strip()
            if not line:
                continue

            # Queremos sólo las llamadas tipo 'circuit.<gate>(...)'
            m = re.match(r'\s*circuit\.(\w+)\s*\((.*)\)\s*$', line)
            if not m:
                continue

            gate = m.group(1).lower()
            args = m.group(2)

            # Extraer ocurrencias de qubits tanto en qreg_q[...] como q[...]
            bracket_contents = re.findall(r'(?:qreg_q|q)\[\s*([^\]]+)\s*\]', args)
            qubits = []
            for inner in bracket_contents:
                # Extraemos todos los números dentro del interior del corchete
                nums = re.findall(r'(\d+)', inner)
                if not nums:
                    # Si no hay números, no podemos resolver el índice -> lo ignoramos
                    # (por ejemplo si aparece 'composition_qubits+X' sin valores numéricos)
                    continue
                # Sumamos los números que aparezcan en el interior (maneja '4+2' -> 6)
                idx = sum(int(n) for n in nums)
                qubits.append(idx)

            # Si hay >=2 qubits en la instrucción, agregamos las aristas (pares)
            if len(qubits) >= 2:
                for a, b in combinations(qubits, 2):
                    edges.add(tuple(sorted((a, b))))

            # Puertas de 1 qubit no generan edges (medida, h, x, y, z, t, ...)
            # Si deseas soportar puertas específicas que implican conectividad distinta,
            # añádelas aquí.

        # devolver como lista ordenada para estabilidad
        return sorted(edges)

        
    # def encontrar_mejor_batch(self, cola, max_qubits):
    #     mejor_batch = []
    #     mejor_suma = 0
    #     vistos = set()

    #     for r in range(1, len(cola) + 1):
    #         for combo in combinations(cola, r):
    #             ids = tuple(sorted(id(x) for x in combo))
    #             if ids in vistos:
    #                 continue
    #             vistos.add(ids)

    #             total = sum(x[1] for x in combo)
    #             if total <= max_qubits and total > mejor_suma:
    #                 mejor_batch = list(combo)
    #                 mejor_suma = total
    #                 if mejor_suma == max_qubits:
    #                     return mejor_batch
    #     return mejor_batch


    def send_shots_optimized(self,queue:list, max_qubits:int, provider:str, executeCircuit:Callable, machine:str) -> None:
        """
        Sends the URLs to the server with the minimum number of shots using the shots_optimized policy

        Args:
            queue (list): The waiting list
            max_qubits (int): The maximum number of qubits            
            provider (str): The provider of the circuit            
            executeCircuit (Callable): The function to execute the circuit            
            machine (str): The machine to execute the circuit
        """
        if len(queue) != 0:
            # Send the URLs to the server
            qb = []
            sumQb = 0
            urls = []
            iterator = queue.copy()
            iterator = sorted(iterator, key=lambda x: x[2]) #Sort the waiting list by shots ascending
            minShots = self.most_repetitive([url[2] for url in iterator]) #Get the most repetitive number of shots in the waiting list
            for url in iterator:
                if url[1]+sumQb <= max_qubits and url[2] >= minShots:
                    sumQb = sumQb + url[1]
                    urls.append(url)
                    index = queue.index(url)
                    #Reduce number of shots of the url in waiting_url instead of removing it
                    if queue[index][2] - minShots <= 0: #If the url has no shots left, remove it from the waiting list
                        queue.remove(url)
                    else:
                        old_tuple = queue[index]
                        new_tuple = old_tuple[:2] + (old_tuple[2] - minShots,) + old_tuple[3:]
                        queue[index] = new_tuple
            print(f"Sending {len(urls)} URLs to the server")
            print(urls)
            # Convert the dictionary to JSON
            code,qb = [],[]
            shotsUsr = [minShots] * len(urls) # The shots for all will be the most repetitive number of shots in the waiting list
            self.create_circuit(urls,code,qb,provider)
            data = {"code":code}
            #Thread(target=executeCircuit, args=(json.dumps(data),qb,shotsUsr,provider,urls,machine)).start()
            #executeCircuit(json.dumps(data),qb,shotsUsr,provider,urls)
            self.services['shots_optimized'].timers[provider].reset()

    def send_shots_depth(self,queue:list, max_qubits:int, provider:str, executeCircuit:Callable, machine:str) -> None:
        """
        Sends the URLs to the server with the minimum number of shots and similar depth using the shots_depth policy

        Args:
            queue (list): The waiting list            
            max_qubits (int): The maximum number of qubits            
            provider (str): The provider of the circuit            
            executeCircuit (Callable): The function to execute the circuit            
            machine (str): The machine to execute the circuit
        """
        # Send the URLs to the server
        if len(queue) != 0:
            qb = []
            sumQb = 0
            urls = []
            iterator = queue.copy()
            iterator = sorted(iterator, key=lambda x: x[2]) #Sort the waiting list by shots ascending
            minShots = iterator[0][2] #Get the minimum number of shots in the waiting list
            depth = iterator[0][5] #Get the depth of the first url in the waiting list
            for url in iterator:
                if url[1]+sumQb <= max_qubits and url[5] <= depth * 1.1 and url[5] >= depth * 0.9:
                    sumQb = sumQb + url[1]
                    urls.append(url)
                    index = queue.index(url)
                    #Reduce number of shots of the url in waiting_url instead of removing it
                    if queue[index][2] - minShots <= 0: #If the url has no shots left, remove it from the waiting list
                        queue.remove(url)
                    else:
                        old_tuple = queue[index]
                        new_tuple = old_tuple[:2] + (old_tuple[2] - minShots,) + old_tuple[3:]
                        queue[index] = new_tuple
            print(f"Sending {len(urls)} URLs to the server")
            print(urls)
            code,qb = [],[]
            shotsUsr = [minShots] * len(urls) # The shots for all will be the minimum number of shots in the waiting list
            self.create_circuit(urls,code,qb,provider)
            data = {"code":code}
            #Thread(target=executeCircuit, args=(json.dumps(data),qb,shotsUsr,provider,urls,machine)).start()
            #executeCircuit(json.dumps(data),qb,shotsUsr,provider,urls)
            self.services['shots_depth'].timers[provider].reset()

    def send_depth(self,queue:list, max_qubits:int, provider:str, executeCircuit:Callable, machine:str) -> None:
        """
        Sends the URLs to the server with the most similar depth using the depth policy

        Args:
            queue (list): The waiting list
            max_qubits (int): The maximum number of qubits            
            provider (str): The provider of the circuit            
            executeCircuit (Callable): The function to execute the circuit            
            machine (str): The machine to execute the circuit
        """
        # Send the URLs to the server
        if len(queue) != 0:
            print('Sent')
            qb = []
            # Convert the dictionary to JSON
            urls = []
            sumQb = 0
            depth = queue[0][5] #Get the depth of the first url in the waiting list
            iterator = queue.copy()
            iterator = iterator[:1] + sorted(iterator[1:], key=lambda x: abs(x[5] - depth)) #Sort the waiting list by difference in depth by the first circuit in the waiting list so it picks the most similar circuit (dont sort the first element because is the reference for the calculation)
            for url in iterator: #Add them to the valid_url only if they fit and are similar to the first circuit in the waiting list
                if url[1]+ sumQb <= max_qubits and url[5] <= depth * 1.1 and url[5] >= depth * 0.9:
                    urls.append(url)
                    sumQb += url[1]
                    queue.remove(url)
            print(f"Sending {len(urls)} URLs to the server")
            print(urls)
            code,qb = [],[]
            shotsUsr = [url[2] for url in urls] #Each one will have its own number of shots, a statistic will be used to get the results after
            self.create_circuit(urls,code,qb,provider)
            data = {"code":code}
            #Thread(target=executeCircuit, args=(json.dumps(data),qb,shotsUsr,provider,urls,machine)).start()
            #executeCircuit(json.dumps(data),qb,shotsUsr,provider,urls)
            self.services['depth'].timers[provider].reset()

    def send_shots(self,queue:list, max_qubits:int, provider:str, executeCircuit:Callable, machine:str) -> None:
        """
        Sends the URLs to the server with the minimum number of shots using the shots policy

        Args:
            queue (list): The waiting list            
            max_qubits (int): The maximum number of qubits            
            provider (str): The provider of the circuit            
            executeCircuit (Callable): The function to execute the circuit            
            machine (str): The machine to execute the circuit
        """
        # Send the URLs to the server
        if len(queue) != 0:
            print('Sent')
            qb = []
            sumQb = 0
            urls = []
            iterator = queue.copy()
            iterator = sorted(iterator, key=lambda x: x[2]) #Sort the waiting list by shots ascending
            minShots = iterator[0][2] #Get the minimum number of shots in the waiting list
            for url in iterator:
                if url[1]+sumQb <= max_qubits:
                    sumQb = sumQb + url[1]
                    urls.append(url)
                    print(url[1])
                    index = queue.index(url)
                    #Reduce number of shots of the url in waiting_url instead of removing it
                    if queue[index][2] - minShots <= 0: #If the url has no shots left, remove it from the waiting list
                        queue.remove(url)
                    else:
                        old_tuple = queue[index]
                        new_tuple = old_tuple[:2] + (old_tuple[2] - minShots,) + old_tuple[3:]
                        queue[index] = new_tuple
            code,qb = [],[]
            shotsUsr = [minShots] * len(urls) # All the urls will have the minimum number of shots in the waiting list
            self.create_circuit(urls,code,qb,provider)
            data = {"code":code}
            #Thread(target=executeCircuit, args=(json.dumps(data),qb,shotsUsr,provider,urls,machine)).start() #Parece que sin esto no se resetea el timer cuando termina de componer
            #executeCircuit(json.dumps(data),qb,shotsUsr,provider,urls)
            self.services['shots'].timers[provider].reset()

    def send_maquinas(self,queue:list, max_qubits:int, provider:str, executeCircuit:Callable, machine:str) -> None:
        """
        Sends the URLs to the server using the time policy

        Args:
            queue (list): The waiting list            
            max_qubits (int): The maximum number of qubits            
            provider (str): The provider of the circuit            
            executeCircuit (Callable): The function to execute the circuit            
            machine (str): The machine to execute the circuit
        """

        if not queue:
            print("\n✅ No hay más elementos en la cola. Programa finalizado de tiempo.\n")
            return
        politica = "tiempo"
        
        if len(queue) != 0:
            #capacidad_maxima = max(item[1] for item in queue)
            # llamo mejor maquina
            #obtengo los qubits de esa maquina
            #maxqubits = a los de la maquina
            
            print("\n📌 Máquinas disponibles:")
        
            self.it += 1  # Número de iteración
            self.setMaxQubits()

            # Organizar las colas en un diccionario por criterio
            print("\n Para el criterio 1 se va a priorizar la máquina con menor número de qubits en cola y, a igual número de qubits, mayor capacidad.")
            print(" Para el criterio 2 se va a priorizar la máquina con mayor capacidad y, a igual capacidad, menor número en la cola.")
            print(" Para el criterio 3 se va a priorizar la máquina con un balance entre capacidad y tamaño de la cola (50%-50%).")
        
            colas_por_criterio = self.organizar_colas_por_criterio(queue)

            # Procesar cada criterio
            for criterio, cola in colas_por_criterio.items():
                if not cola:
                    print(f"\n⚠ No hay elementos en la cola del criterio {criterio}.")
                    continue


                capacidad_maxima = max(item[1] for item in cola)
                suma_total_qubits = sum(item[1] for item in cola)  # Sumar todos los qubits en la cola
                # Seleccionar la mejor máquina según el criterio
                mejor_maquina = self.obtener_mejor_maquina(suma_total_qubits, capacidad_maxima, politica, criterio)
                if not mejor_maquina:
                    print(f"⚠ No se puede continuar sin una máquina adecuada para el criterio {criterio}.")
                    continue
                

                self.actualizar_maquina_usada("tiempo", criterio, mejor_maquina["deviceName"])
                max_qubits = mejor_maquina["qubitCount"]
                print(f"\n🔹 La máxima capacidad de las máquinas es: {max_qubits}")
                print('Sent')
                urls = []
                iterator = cola.copy() #Make a copy to not delete on search #queue.copy()
                sumQb = 0
                print(f"📢 Iniciación tiempo")
                #it=0
                


                # Nombre del archivo para el criterio actual
                #file_name = f"criterio_{criterio}_tiempo.txt"
                file_name = os.path.join(CARPETA_SALIDAS, f"criterio_{criterio}_tiempo.txt")

                with open(file_name, "a") as file:
                    #file.write(f"\n--- Iteracion {self.it} ---\n")
                    #file.write(f"Maquina utilizada: {mejor_maquina['deviceName']} (Qubits: {max_qubits})\n")
                    file.write(f"\nMaquina utilizada: {mejor_maquina['deviceName']} --Qubits: {max_qubits}--\n")
                    file.write("Cola Seleccionada: [")
                    elementos_procesados = 0
                    for url in iterator:
                        if url[1] + sumQb <= max_qubits:
                            urls.append(url)
                            sumQb += url[1]
                            queue.remove(url)
                            cola.remove(url)
                            #print(f"✅ Procesado: {url[4]} (Qubits usados: {url[1]})")
                            elementos_procesados += 1
                            # Guardar en archivo
                            #file.write(f"Circuito: {url[4]}, Qubits usados: {url[1]}\n")
                            file.write(f"  ('{url[4]}', {url[1]}, {self.it}), ")

                    file.write("]\n")
                    file.write(f"Suma total de qubits alcanzada: {sumQb}\n")
                    file.write(f"Elementos utilizados en la cola: {elementos_procesados}\n")
                #print(f"La suma total es: {sumQb}")
                print(f"📢 Quedan {len(cola)} elementos en la cola del criterio {criterio}.")

                self.reducir_queue_size_global("tiempo", criterio, self.iteracion)
                
                code, qb = [], []
                shotsUsr = [10000] * len(urls)

                self.create_circuit(urls, code, qb, provider)
                data = {"code": code}

                # executeCircuit(json.dumps(data), qb, shotsUsr, provider, urls)
                self.services['time'].timers[provider].reset()
        

    def send_individual_batches(self, queue: list, max_qubits: int, provider: str, executeCircuit: Callable, machine: str) -> None:
        """
        Política tipo IBM: enviar un circuito por batch, respetando orden de llegada.
        Cada circuito se envía como si fuera un job independiente.
        """

        if not queue:
            print("\n✅ No hay más elementos en la cola. Programa finalizado.\n")
            return

        self.iteracion_tiempo += 1
        batch_idx = 1
        file_name = os.path.join(CARPETA_SALIDAS, "criterio_ibm_like.txt")

        elementos_procesados = 0
        nuevos_enviados = []

        for url in queue[:]:  # Copia de la cola para iterar mientras se modifica
            if url[1] > max_qubits:
                print(f"⚠ Circuito '{url[4]}' necesita {url[1]} qubits, excede el máximo ({max_qubits}). Se omite.")
                continue

            # Registro
            with open(file_name, "a") as file:
                file.write(f"\n Iteración {self.iteracion_tiempo} - Batch #{batch_idx} - Máquina: {machine} -- Qubits: {max_qubits}\n")
                file.write(f"Batch generado: [('{url[4]}', {url[1]}, {self.iteracion_tiempo})]\n")
                file.write(f"Suma total de qubits utilizados: {url[1]}\n")
                file.write(f"Circuitos enviados en este batch: 1\n")

            # Preparar y enviar
            code, qb = [], []
            shotsUsr = [10000]
            self.create_circuit([url], code, qb, provider)
            data = {"code": code}
            # executeCircuit(json.dumps(data), qb, shotsUsr, provider, [url])

            nuevos_enviados.append(url)
            elementos_procesados += 1
            batch_idx += 1

        # Limpiar la cola
        for url in nuevos_enviados:
            if url in queue:
                queue.remove(url)

        print(f"\n✅ Iteración {self.iteracion_tiempo} completada con {batch_idx - 1} batch(es) individuales.\n")


    

    def getMaxQubits(self):
        return self.max_qubits
    



    def setMaxQubits(self):
        """
        Establece el número máximo de qubits para el scheduler basado en los dispositivos disponibles
        en el fichero 'maquinas_fran_1'.
        """
        try:
            #with open("maquina_principal.txt", "r") as file:
            with open(os.path.join(CARPETA_SALIDAS, f"maquina_principal.txt"), "r") as file:
                dispositivos = [json.loads(line.replace("'", '"')) for line in file]  # Cargar dispositivos desde el archivo

            if not dispositivos:
                print("No se encontraron dispositivos en el archivo.")
                return None

            # Filtrar dispositivos en línea
            dispositivos_online = [d for d in dispositivos if d.get("deviceStatus") == "ONLINE"]

            if not dispositivos_online:
                print("\n⚠ No hay máquinas en línea disponibles.")
                return None

            self.dispositivos_disponibles = dispositivos_online

            for dispositivo in dispositivos_online:
                print(f"  🔹 {dispositivo['deviceName']} ({dispositivo['providerName']}) - Qubits: {dispositivo['qubitCount']} - Cola: {dispositivo['queueSize']}")

            # Obtener el máximo número de qubits
            max_qubit_maquinas = max(d["qubitCount"] for d in dispositivos_online)

            print(f"Max qubits EL METODO ESTE QUE HE CREADO: {max_qubit_maquinas}")

            self.max_qubit = max_qubit_maquinas

        except Exception as e:
            print(f"Error al leer el archivo de máquinas: {e}")
            return None




    def obtener_dispositivos_ibm(self):
        """Obtiene la lista de dispositivos de IBM Quantum."""
        try:
            # Crear una instancia de la clase IBM
            dispositivos = self.executeCircuitIBM.IBM()  # ✅ Ahora IBM() devuelve dispositivos
            
            # Debugging
            #print(" Dispositivos obtenidos de IBM:", dispositivos)

            return dispositivos  # ✅ Devolver la lista correctamente

        except Exception as e:
            print(f"Error al obtener dispositivos de IBM: {e}")
            return []

    

    def obtener_dispositivos_aws(self):
        """Obtiene la lista de dispositivos de AWS."""
        try:
            # Crear una instancia de la clase AWS
            dispositivos = AWS()  # ✅ Ahora AWS() devuelve la lista correctamente

            # Debugging
            #print("📡 Dispositivos obtenidos de AWS:", dispositivos)

            return dispositivos  # ✅ Devolver la lista de dispositivos correctamente

        except Exception as e:
            print(f"Error al obtener dispositivos de AWS: {e}")
            return []

    def organizar_colas_por_criterio(self, queue):
        colas_por_criterio = {
            1: [item for item in queue if item[6] == 1],
            2: [item for item in queue if item[6] == 2],
            3: [item for item in queue if item[6] == 3],
        }

        # for criterio, cola in colas_por_criterio.items():
        #     max_numero = max([item[1] for item in cola], default=0)  # Obtener el número máximo
        #     print(f"\n📌 Cola para el criterio {criterio}:")
        #     for item in cola:
        #          print(f"  🔹 ID: {item[3]} | Número: {item[1]} | Criterio: {item[6]}")
        #     print(f"🔹 Número de elementos en la cola del criterio {criterio}: {len(cola)}")
        #     print(f"🔹 El número máximo en esta cola es: {max_numero}")
        
        return colas_por_criterio

    def obtener_colas_sin_criterio(self, queue):
        colas_sin_criterio = {
            1: [item for item in queue if item[6] == 0],
            
        }

        return colas_sin_criterio
    #   NO SIRVE PARA LAS PRUEBAS
    # def obtener_mejor_maquina(self, capacidad_maxima, criterio):
    #     # dispositivos_ibm = self.obtener_dispositivos_ibm()
    #     # dispositivos_aws = self.obtener_dispositivos_aws()
    #     # dispositivos = dispositivos_ibm + dispositivos_aws
        
    #     # if not dispositivos:
    #     #     print("No se encontraron dispositivos disponibles.")
    #     #     return None

    #     # dispositivos_online = [d for d in dispositivos if d.get("deviceStatus") == "ONLINE"]
    #     # if not dispositivos_online:
    #     #     print("\n⚠ No hay máquinas en línea disponibles.")
    #     #     return None
        
    #     # max_qubit_maquinas = max(d["qubitCount"] for d in dispositivos_online)
    #     # print(f"\n🔹 La máxima capacidad de las máquinas es: {max_qubit_maquinas}")

    #     dispositivos_online = self.dispositivos_disponibles
    #     max_qubit_maquinas = max(d["qubitCount"] for d in dispositivos_online)
    #     print(f"\n🔹 La máxima capacidad de las máquinas es: {max_qubit_maquinas}")
        
    #     # Filtrar máquinas con qubitCount mayor al máximo número en la cola
    #     maquinas_validas = [d for d in dispositivos_online if d["qubitCount"] > capacidad_maxima]
        
        
    #     if not maquinas_validas:
    #         print("⚠ No hay máquinas con suficiente capacidad.")
    #         return None
        
    #     if capacidad_maxima == max_qubit_maquinas:
    #         maquinas_validas = [d for d in dispositivos_online if d["qubitCount"] == max_qubit_maquinas]

    #     if criterio == 1:
    #         mejor_maquina = min(maquinas_validas, key=lambda d: (d["queueSize"], -d["qubitCount"]))
    #     elif criterio == 2:
    #         mejor_maquina = max(maquinas_validas, key=lambda d: (d["qubitCount"], -d["queueSize"]))
    #     elif criterio == 3:
    #         peso_capacidad = 50
    #         peso_cola = 50
    #         min_qubits = min(d["qubitCount"] for d in maquinas_validas)
    #         max_qubits = max(d["qubitCount"] for d in maquinas_validas)
    #         min_queue = min(d["queueSize"] for d in maquinas_validas)
    #         max_queue = max(d["queueSize"] for d in maquinas_validas)
            
    #         def normalizar(valor, minimo, maximo):
    #             return (valor - minimo) / (maximo - minimo) if maximo > minimo else 1
            
    #         def calcular_puntuacion(dispositivo):
    #             score_qubits = normalizar(dispositivo["qubitCount"], min_qubits, max_qubits)
    #             score_queue = 1 - normalizar(dispositivo["queueSize"], min_queue, max_queue)
    #             return (peso_capacidad / 100 * score_qubits) + (peso_cola / 100 * score_queue)
            
    #         ranking = sorted(maquinas_validas, key=calcular_puntuacion, reverse=True)
    #         mejor_maquina = ranking[0]
    #     else:
    #         print("⚠ Criterio no válido.")
    #         return None
        
        
        
    #     print(f"\n🏆 Máquina seleccionada para el criterio {criterio}: {mejor_maquina['deviceName']} ({mejor_maquina['providerName']})")
    #     return mejor_maquina


    def obtener_mejor_maquina(self, suma_total_qubits, capacidad_maxima, politica, criterio):
        #file_name = f"maquinas_{politica}_{criterio}.txt"  # Archivo en formato TXT
        file_name = os.path.join(CARPETA_SALIDAS, f"maquinas_{politica}_{criterio}.txt")
    
        maquinas_disponibles = []
        
        try:
            with open(file_name, "r") as file:
                for line in file:
                    try:
                        maquina = ast.literal_eval(line.strip())  # Convierte el string en diccionario
                        if isinstance(maquina, dict) and maquina.get("deviceStatus") == "ONLINE":
                            maquinas_disponibles.append(maquina)
                    except (SyntaxError, ValueError):
                        print(f"⚠ Error al procesar línea: {line.strip()}")  # Manejo de errores en líneas incorrectas
        except FileNotFoundError:
            print(f"⚠ Archivo {file_name} no encontrado.")
            return None

        if not maquinas_disponibles:
            print(f"⚠ No hay máquinas disponibles en {file_name}.")
            return None

        print(f"\n🔹 Máquinas disponibles en {file_name}:")
        for maquina in maquinas_disponibles:
            print(f"  🔹 {maquina['deviceName']} ({maquina['providerName']}) - Qubits: {maquina['qubitCount']} - Cola: {maquina['queueSize']}")

        # Filtrar máquinas con qubitCount mayor al máximo número en la cola
        maquinas_validas = [d for d in maquinas_disponibles if d["qubitCount"] > capacidad_maxima]

        #if suma_total_qubits <= max(d["qubitCount"] for d in maquinas_validas):
            #maquinas_validas = sorted(maquinas_validas, key=lambda d: abs(d["qubitCount"] - suma_total_qubits))[:1]
            #maquinas_validas = [d for d in maquinas_validas if d["qubitCount"] >= suma_total_qubits]
        #else:
            #maquinas_validas = sorted(maquinas_validas, key=lambda d: abs(d["qubitCount"] - suma_total_qubits))[:1]

        if not maquinas_validas:
            print("⚠ No hay máquinas con suficiente capacidad.")
            return None

        if capacidad_maxima == max(d["qubitCount"] for d in maquinas_validas):
            maquinas_validas = [d for d in maquinas_disponibles if d["qubitCount"] == capacidad_maxima]

        # Selección de la mejor máquina según el criterio
        if criterio == 1:
            mejor_maquina = min(maquinas_validas, key=lambda d: (d["queueSize"], -d["qubitCount"]))
        elif criterio == 2:
            mejor_maquina = max(maquinas_validas, key=lambda d: (d["qubitCount"], -d["queueSize"]))
        elif criterio == 3:
            peso_capacidad = 50
            peso_cola = 50
            min_qubits = min(d["qubitCount"] for d in maquinas_validas)
            max_qubits = max(d["qubitCount"] for d in maquinas_validas)
            min_queue = min(d["queueSize"] for d in maquinas_validas)
            max_queue = max(d["queueSize"] for d in maquinas_validas)

            def normalizar(valor, minimo, maximo):
                return (valor - minimo) / (maximo - minimo) if maximo > minimo else 1

            def calcular_puntuacion(dispositivo):
                score_qubits = normalizar(dispositivo["qubitCount"], min_qubits, max_qubits)
                score_queue = 1 - normalizar(dispositivo["queueSize"], min_queue, max_queue)
                return (peso_capacidad / 100 * score_qubits) + (peso_cola / 100 * score_queue)

            ranking = sorted(maquinas_validas, key=calcular_puntuacion, reverse=True)
            mejor_maquina = ranking[0]
        else:
            print("⚠ Criterio no válido.")
            return None
        # Ahora comprobamos si la mejor máquina elegida es óptima en base a suma_total_qubits
        if suma_total_qubits >= mejor_maquina["qubitCount"]:
            print(f"✅ La máquina seleccionada ({mejor_maquina['deviceName']}) puede ejecutar toda la cola. del criterio: {criterio} en {politica} e iteracion: {self.iteracion}")
        else:
            print(f"⚠ La máquina seleccionada ({mejor_maquina['deviceName']}) no puede ejecutar toda la cola. Buscando otra opción...")
            
            # Buscar la máquina que minimice la diferencia con suma_total_qubits
            maquinas_validas = sorted(maquinas_validas, key=lambda d: abs(d["qubitCount"] - suma_total_qubits))[:1]
            if maquinas_validas:
                mejor_maquina = maquinas_validas[0]

        print(f"\n🏆 Máquina final seleccionada: {mejor_maquina['deviceName']} ({mejor_maquina['providerName']}) - Qubits: {mejor_maquina['qubitCount']}")
        return mejor_maquina

      
    
    
    
    

    def programaDinamico(self, queue: list, max_qubits: int, criterio: int):
        """
        Encuentra la mejor combinación de elementos sin superar max_qubits.
        También selecciona la mejor máquina antes de optimizar.
        """
        # Seleccionar la mejor máquina según max_qubits y el criterio
        # mejor_maquina = self.obtener_mejor_maquina(max_qubits, criterio)
        # if not mejor_maquina:
        #     print("⚠ No se puede continuar sin una máquina adecuada.")
        #     return None, None

        # # Ajustar max_qubits al `qubitCount` de la mejor máquina
        # max_qubits = mejor_maquina["qubitCount"]
        # print(f"\n🔹 Optimizando para capacidad máxima de la máquina: {max_qubits}")

        # Programación dinámica para encontrar la mejor combinación
        print("\n🔹 Iniciando programación dinámica...")
        n = len(queue)
        dp = [0] * (max_qubits + 1)  # Almacena la suma máxima de valores para cada capacidad
        seleccionados = [[] for _ in range(max_qubits + 1)]  # Almacena las tareas seleccionadas para cada capacidad

        for i in range(n):
            id_, valor = queue[i][0], queue[i][1]  # Tomar solo el identificador y el valor de la tarea
            for w in range(max_qubits, valor - 1, -1):
                if dp[w - valor] + valor > dp[w]:
                    dp[w] = dp[w - valor] + valor
                    seleccionados[w] = seleccionados[w - valor] + [queue[i]]

        # Devolver la mejor combinación y la suma total
        return seleccionados[max_qubits], dp[max_qubits]


    def mainPD(self, queue=None, capacidad_maxima=None, provider=None, executeCircuit=None, machine=None):
        """
        Ejecuta el proceso completo. Si no se proporcionan queue y capacidad_maxima, usa los valores predeterminados.
        """
        if not queue:
            print("\n✅ No hay más elementos en la cola. Programa finalizado dinamico.\n")
            return
        
        print("\n🚀 Iniciando el programa...dinamico")

        # Si no hay más elementos en la cola, termina el programa
        
        politica = "MaxPD"
        # Calcular capacidad máxima
        #capacidad_maxima = max(x[1] for x in queue)
        #print(f"\n🔹 Capacidad máxima de la cola: {capacidad_maxima}")

        # Mostrar todas las máquinas disponibles
        print("\n📌 Máquinas disponibles:")
        # dispositivos_ibm = self.obtener_dispositivos_ibm()
        # dispositivos_aws = self.obtener_dispositivos_aws()
        # dispositivos = dispositivos_ibm + dispositivos_aws
        # for dispositivo in dispositivos:
        #     print(f"  🔹 {dispositivo['deviceName']} ({dispositivo['providerName']}) - Qubits: {dispositivo['qubitCount']} - Cola: {dispositivo['queueSize']}")
        
        self.setMaxQubits()
        self.iteracion += 1  # Número de iteración
        # Organizar las colas en un diccionario por criterio
        print("\n Para el criterio 1 se va a priorizar la máquina con menor número de qubits en cola y, a igual número de qubits, mayor capacidad.")
        print(" Para el criterio 2 se va a priorizar la máquina con mayor capacidad y, a igual capacidad, menor número en la cola.")
        print(" Para el criterio 3 se va a priorizar la máquina con un balance entre capacidad y tamaño de la cola (50%-50%).")
        
        colas_por_criterio = self.organizar_colas_por_criterio(queue)

        # Procesar cada criterio
        for criterio, cola in colas_por_criterio.items():
            if not cola:
                print(f"\n⚠ No hay elementos en la cola del criterio {criterio}.")
                continue

            suma_total_qubits = sum(item[1] for item in cola)  # Sumar todos los qubits en la cola
            capacidad_maxima = max(item[1] for item in cola)
            # Seleccionar la mejor máquina según el criterio
            mejor_maquina = self.obtener_mejor_maquina(suma_total_qubits, capacidad_maxima, politica, criterio)
            if mejor_maquina:
                self.actualizar_maquina_usada("MaxPD", criterio, mejor_maquina["deviceName"])
            if not mejor_maquina:
                print(f"⚠ No se puede continuar sin una máquina adecuada para el criterio {criterio}.")
                continue

            # Ajustar max_qubits al `qubitCount` de la mejor máquina
            max_qubits = mejor_maquina["qubitCount"]
            print(f"\n🔹 Optimizando para capacidad máxima de la máquina: {max_qubits}")

            # Ejecutar el algoritmo de programación dinámica con la mejor máquina
            combinacion, suma = self.programaDinamico(cola, max_qubits, criterio)

             # Archivo para el criterio actual
            #file_name = f"criterio_{criterio}_MaxPD.txt"
            file_name = os.path.join(CARPETA_SALIDAS, f"criterio_{criterio}_MaxPD.txt")
            
            with open(file_name, "a") as file:
                #file.write(f"\n---Iteracion {self.iteracion} ---\n")
                file.write(f"\nMaquina utilizada: {mejor_maquina['deviceName']} --Qubits: {max_qubits}--\n")
                file.write("Cola Seleccionada: [")

                if combinacion:
                    print(f"\n✅ Combinación encontrada para el criterio {criterio}:")
                    for item in combinacion:
                        #print(f"  🔹 ID: {item[4]} | Número de qubits: {item[1]} | Criterio: {item[6]}")
                        #file.write(f"Circuito: {item[4]}, Qubits usados: {item[1]}\n")
                        file.write(f"  ('{item[4]}', {item[1]}, {self.iteracion}), ")

                    file.write("]\n")
                    file.write(f"Suma total de qubits alcanzada: {suma}\n")
                    file.write(f"Elementos utilizados en la cola: {len(combinacion)}\n")

                    for item in combinacion:
                        queue.remove(item)
                        cola.remove(item)

                    # print(f"\n📌 Elementos restantes en la cola del criterio {criterio}:")
                    # for item in cola:
                    #     print(f"  🔹 ID: {item[3]} | Número de qubits: {item[1]} | Criterio: {item[6]}")
                    # print(f"🔹 Número de elementos restantes en la cola del criterio {criterio}: {len(cola)}")
                else:
                    print(f"⚠ No se encontraron combinaciones válidas para el criterio {criterio}.")
                    file.write("\n⚠ No se encontraron combinaciones válidas en esta iteración.\n")


            self.reducir_queue_size_global("MaxPD", criterio, self.iteracion)


        #self.reducir_queue_size_global("fran", criterio, self.iteracion)
        # Mostrar los elementos restantes en todas las colas
        # print("\n📌 Elementos restantes en todas las colas:")
        # for criterio, cola in colas_por_criterio.items():
        #     print(f"\n📌 Cola para el criterio {criterio}:")
        #     for item in cola:
        #         print(f"  🔹 ID: {item[3]} | Número: {item[1]} | Criterio: {item[6]}")
        #     print(f"🔹 Número de elementos restantes en la cola del criterio {criterio}: {len(cola)}")



    def predict_combination_with_model(self, cola, capacidad_maxima, modelo, input_size=2000):
        """
        Predice la combinación de elementos seleccionados directamente usando el modelo entrenado.

        Args:
            cola (list): Lista de tuplas (nombre_archivo, num_qubits, peso, ...).
            capacidad_maxima (int): Límite de qubits.
            modelo (torch.nn.Module): Modelo entrenado.
            input_size (int): Tamaño fijo del input.

        Returns:
            combinacion_final (list): Sublista seleccionada (con la tupla completa original).
            suma_qubits (int): Total de qubits usados.
        """
        print(f"🔹 Capacidad máxima: {capacidad_maxima}")
        if not cola or capacidad_maxima <= 0:
            return [], 0

        # Extraer solo los valores de qubits (asumido como segundo elemento de cada tupla)
        qubits_list = [item[1] for item in cola]

        if len(qubits_list) > input_size:
            cola = cola[:input_size]
            qubits_list = qubits_list[:input_size]

        padded_qubits = np.pad(qubits_list, (0, input_size - len(qubits_list)), 'constant')
        input_tensor = torch.tensor(padded_qubits, dtype=torch.float32).unsqueeze(0)

        with torch.no_grad():
            output = modelo(input_tensor).squeeze(0).numpy()

        # Selección ordenada por probabilidad descendente
        selected_indices = np.argsort(-output)
        combinacion_final = []
        suma_qubits = 0

        for idx in selected_indices:
            if idx < len(qubits_list):
                qubits = qubits_list[idx]
                if suma_qubits + qubits <= capacidad_maxima:
                    combinacion_final.append(cola[idx])
                    suma_qubits += qubits
                    if suma_qubits == capacidad_maxima:
                        break

        return combinacion_final, suma_qubits






        

    def mainML(self, queue=None, capacidad_maxima=None, provider=None, executeCircuit=None, machine=None):
        """
        Ejecuta el proceso completo. Si no se proporcionan queue y capacidad_maxima, usa los valores predeterminados.
        """

        model = load_model()
        print("✅ Modelo cargado correctamente.")
        if not queue:
            print("\n✅ No hay más elementos en la cola. Programa finalizado dinamico.\n")
            return
        
        print("\n🚀 Iniciando el programa...dinamico")

        # Si no hay más elementos en la cola, termina el programa
        
        politica = "MaxML"
        # Calcular capacidad máxima
        #capacidad_maxima = max(x[1] for x in queue)
        #print(f"\n🔹 Capacidad máxima de la cola: {capacidad_maxima}")

        # Mostrar todas las máquinas disponibles
        print("\n📌 Máquinas disponibles:")
        # dispositivos_ibm = self.obtener_dispositivos_ibm()
        # dispositivos_aws = self.obtener_dispositivos_aws()
        # dispositivos = dispositivos_ibm + dispositivos_aws
        # for dispositivo in dispositivos:
        #     print(f"  🔹 {dispositivo['deviceName']} ({dispositivo['providerName']}) - Qubits: {dispositivo['qubitCount']} - Cola: {dispositivo['queueSize']}")
        
        self.setMaxQubits()
        self.iteracion_ML += 1  # Número de iteración
        # Organizar las colas en un diccionario por criterio
        print("\n Para el criterio 1 se va a priorizar la máquina con menor número de qubits en cola y, a igual número de qubits, mayor capacidad.")
        print(" Para el criterio 2 se va a priorizar la máquina con mayor capacidad y, a igual capacidad, menor número en la cola.")
        print(" Para el criterio 3 se va a priorizar la máquina con un balance entre capacidad y tamaño de la cola (50%-50%).")
        
        colas_por_criterio = self.organizar_colas_por_criterio(queue)

        # Procesar cada criterio
        for criterio, cola in colas_por_criterio.items():
            if not cola:
                print(f"\n⚠ No hay elementos en la cola del criterio {criterio}.")
                continue

            suma_total_qubits = sum(item[1] for item in cola)  # Sumar todos los qubits en la cola
            capacidad_maxima = max(item[1] for item in cola)
            # Seleccionar la mejor máquina según el criterio
            mejor_maquina = self.obtener_mejor_maquina(suma_total_qubits, capacidad_maxima, politica, criterio)
            if mejor_maquina:
                self.actualizar_maquina_usada("MaxML", criterio, mejor_maquina["deviceName"])
            if not mejor_maquina:
                print(f"⚠ No se puede continuar sin una máquina adecuada para el criterio {criterio}.")
                continue

            # Ajustar max_qubits al `qubitCount` de la mejor máquina
            max_qubits = mejor_maquina["qubitCount"]
            print(f"\n🔹 Optimizando para capacidad máxima de la máquina: {max_qubits}")

            # Ejecutar el algoritmo de programación dinámica con la mejor máquina
            combinacion, suma = self.predict_combination_with_model(cola, max_qubits, model)


             # Archivo para el criterio actual
            #file_name = f"criterio_{criterio}_MaxML.txt"
            file_name = os.path.join(CARPETA_SALIDAS, f"criterio_{criterio}_MaxML.txt")

            with open(file_name, "a") as file:
                #file.write(f"\n---Iteracion {self.iteracion} ---\n")
                file.write(f"\nMaquina utilizada: {mejor_maquina['deviceName']} --Qubits: {max_qubits}--\n")
                file.write("Cola Seleccionada: [")

                if combinacion:
                    print(f"\n✅ Combinación encontrada para el criterio {criterio}:")
                    for item in combinacion:
                        #print(f"  🔹 ID: {item[4]} | Número de qubits: {item[1]} | Criterio: {item[6]}")
                        #file.write(f"Circuito: {item[4]}, Qubits usados: {item[1]}\n")
                        file.write(f"  ('{item[4]}', {item[1]}, {self.iteracion_ML}), ")

                    file.write("]\n")
                    file.write(f"Suma total de qubits alcanzada: {suma}\n")
                    file.write(f"Elementos utilizados en la cola: {len(combinacion)}\n")

                    for item in combinacion:
                        queue.remove(item)
                        cola.remove(item)

                    # print(f"\n📌 Elementos restantes en la cola del criterio {criterio}:")
                    # for item in cola:
                    #     print(f"  🔹 ID: {item[3]} | Número de qubits: {item[1]} | Criterio: {item[6]}")
                    # print(f"🔹 Número de elementos restantes en la cola del criterio {criterio}: {len(cola)}")
                else:
                    print(f"⚠ No se encontraron combinaciones válidas para el criterio {criterio}.")
                    file.write("\n⚠ No se encontraron combinaciones válidas en esta iteración.\n")


            self.reducir_queue_size_global("MaxML", criterio, self.iteracion_ML)


    

    def get_ibm_machine(self) -> str:
        """
        Returns the IBM machine of the scheduler

        Returns:
            str: The IBM machine of the scheduler
        """
        return self.machine_ibm
    
    def get_ibm(self):
        return self.executeCircuitIBM


    

#PARA LAS PRUEBAS


    def leer_maquinas(self,politica, criterio):
        #nombre_archivo = f"maquinas_{politica}_{criterio}.txt"
        nombre_archivo = os.path.join(CARPETA_SALIDAS, f"maquinas_{politica}_{criterio}.txt")
        try:
            with open(nombre_archivo, "r") as file:
                # Cada línea es un diccionario en formato str
                return [eval(line.strip()) for line in file if line.strip()]
        except FileNotFoundError:
            print(f"⚠ Archivo {nombre_archivo} no encontrado.")
            return []
        
        
    def actualizar_maquina_usada(self,politica, criterio, nombre_maquina):
        maquinas = self.leer_maquinas(politica, criterio)
        for maquina in maquinas:
            if maquina["deviceName"] == nombre_maquina:
                maquina["queueSize"] += 1
                break
        
        # Guardar los cambios
        #with open(f"maquinas_{politica}_{criterio}.txt", "w") as file:
        with open(os.path.join(CARPETA_SALIDAS, f"maquinas_{politica}_{criterio}.txt"), "w") as file:
            for maquina in maquinas:
                file.write(str(maquina) + "\n")  # Guardar cada diccionario en una línea

    def reducir_queue_size_global(self, politica, criterio, iteracion_actual):
        if iteracion_actual % 2 != 0:
            return  # Solo se ejecuta cada 2 iteraciones
        
      
        if iteracion_actual % 2 != 0:
            return  # Solo se ejecuta cada 2 iteraciones
        
        maquinas = self.leer_maquinas(politica, criterio)
        updated = False
        
        for maquina in maquinas:
            if maquina["queueSize"] > 0:
                maquina["queueSize"] -= 1
                updated = True
        
        if updated:
            #with open(f"maquinas_{politica}_{criterio}.txt", "w") as file:
            with open(os.path.join(CARPETA_SALIDAS, f"maquinas_{politica}_{criterio}.txt"), "w") as file:
                for maquina in maquinas:
                    file.write(str(maquina) + "\n")