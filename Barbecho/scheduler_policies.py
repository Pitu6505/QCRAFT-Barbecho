import json
import requests
from flask import request
import re
from executeCircuitIBM import executeCircuitIBM
from executeCircuitAWS import runAWS, runAWS_save, code_to_circuit_aws, AWS 
from ResettableTimer import ResettableTimer
from threading import Thread
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

CARPETA_SALIDAS = os.path.join("QCRAFT-Scheduler", "QCRAFT-Scheduler", "salidas")
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
        self.time_limit_seconds = 600#300 #estaba en 600
        self.executeCircuitIBM = executeCircuitIBM()
        
        self.setMaxQubits()
        self.max_qubits = 266 #254 o 266
        self.max_qubits_send = 133 #127 o 133
        self.machine_ibm = 'ibm_torino' # ibm_brisbane o ibm_torino
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
                        'batch' : Policy(self.send_individual_batches, self.max_qubits, self.time_limit_seconds, self.executeCircuit, self.machine_aws, self.machine_ibm)}
        
        
        
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
        if n_qubits >= 254 and (service_name != 'time_maquinas' and service_name != 'MaxML' and service_name != 'MaxPD' and service_name != 'time'): #es 127
           self.services[service_name].timers[provider].execute_and_reset()
        return 'Data received', 200
        
     #EL BUENO QUE HAY
    def executeCircuit(self,data:dict,qb:list,shots:list,provider:str,urls:list, machine:str) -> None: #Data is the composed circuit to execute, qb is the number of qubits per circuit, shots is the number of shots per circut, provider is the provider of the circuit, urls is the array with data of each circuit (url, num_qubits, shots, user, circuit_name)
        """
        Executes the circuit in the selected provider

        Args:
            data (dict): The data of the circuit to execute            
            qb (list): The number of qubits per circuit            
            shots (list): The number of shots per circuit
            provider (str): The provider of the circuit            
            urls (list): The data of each circuit            
            machine (str): The machine to execute the circuit

        Raises:
            Exception: If an error occurs during the execution of the circuit
        """

        circuit = ''
        for data in json.loads(data)['code']:
            circuit = circuit + data + '\n'
        
        loc = {}
        if provider == 'ibm':
            loc['circuit'] = self.executeCircuitIBM.code_to_circuit_ibm(circuit)
        else:
            loc['circuit'] = code_to_circuit_aws(circuit)


        #circuit = 'def circ():\n'
        #f = json.loads(data)
        #for line in f['code']: #Construir el circuito según lo obtenido del traductor
        #    circuit = circuit + '\t' + line + '\n'
#
        #circuit = circuit + 'circuit = circ()'
#
        #print(circuit)
#
        #loc = {}
        #exec(circuit,globals(),loc) #Recuperar el objeto circuito que se obtiene, cuidado porque si el código del circuito no está controlado, esto es muy peligroso
        # Aquí se podría comprobar la mejor máquina para ejecutar el circuito
        print('_____________________________________________________________________')
        #print(loc['circuit'])
        print('_____________________________________________________________________')
        try:
            if provider == 'ibm':
                #backend = least_busy_backend_ibm(sum(qb))
                # TODO escoger el backend más adecuado para el circuito
                #counts = runIBM(self.machine_ibm,loc['circuit'],max(shots)) #Ejecutar el circuito y obtener el resultado
                counts = self.executeCircuitIBM.runIBM_save(machine,loc['circuit'],max(shots),[url[3] for url in urls],qb,[url[4] for url in urls]) #Ejecutar el circuito y obtener el resultado
            else:
                counts = runAWS_save(machine,loc['circuit'],max(shots),[url[3] for url in urls],qb,[url[4] for url in urls],'') #Ejecutar el circuito y obtener el resultado
        except Exception as e:
            print(f"Error executing circuit: {e}")

        #print(counts.items())

        data = {"counts": counts, "shots": shots, "provider": provider, "qb": qb, "users": [url[3] for url in urls], "circuit_names": [url[4] for url in urls]}

        requests.post(self.unscheduler, json=data)


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

        for batch_idx, batch in enumerate(urls):
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


            if provider == 'ibm' and batch_idx < len(urls) - 1:
                code.append("circuit.barrier()")
                for i in range(composition_qubits):
                    code.append(f"circuit.reset(qreg_q[{i}])")
            composition_qubits = 0

        # Barrera global al final (para separar batches en IBM)
        
            

        code.append("return circuit")


    # #POLITICA DE TIEMPO HORIZONTAL
    # def send(self, queue: list, max_qubits: int, provider: str, executeCircuit: Callable, machine: str) -> None:
    #     """
    #     Modificado para garantizar que en cada iteración se ejecute un único circuito compuesto
    #     (que puede contener hasta 2 batches si hay suficientes circuitos).
    #     """
    #     if not queue:
    #         print("\n✅ No hay más elementos en la cola. Programa finalizado.\n")
    #         return

    #     if not hasattr(self, "urls_ya_procesados"):
    #         self.urls_ya_procesados = set()

    #     self.iteracion_tiempo += 1
    #     colas_sin_criterio = self.obtener_colas_sin_criterio(queue)

    #     file_name = os.path.join(CARPETA_SALIDAS, f"criterio_tiempo.txt")
    #     elementos_procesados_total = 0

    #     for criterio, cola_original in colas_sin_criterio.items():
    #         if not cola_original:
    #             continue

    #         cola = list(cola_original)  # Copia para trabajar
    #         batches = []

    #         # Generar hasta 2 batches por iteración (si hay suficientes circuitos)
    #         for batch_num in range(1, 498):  
    #             urls_batch = []
    #             sumQb = 0

    #             for url in cola:
    #                 if url in self.urls_ya_procesados:
    #                     continue
    #                 if url[1] + sumQb <= max_qubits:
    #                     urls_batch.append(url)
    #                     sumQb += url[1]

    #             if not urls_batch:
    #                 break  # No hay más circuitos para este batch

    #             batches.append((urls_batch, sumQb, batch_num))
    #             self.urls_ya_procesados.update(urls_batch)

    #             # Eliminar de la cola principal y la cola del criterio
    #             for url in urls_batch:
    #                 if url in queue:
    #                     queue.remove(url)
    #                 if url in cola_original:
    #                     cola_original.remove(url)

    #         # ⚡ Procesar todos los batches juntos en esta iteración
    #         if batches:
    #             with open(file_name, "a") as file:
    #                 file.write(f"\n Iteración {self.iteracion_tiempo} - Máquina: {machine} -- Qubits: {max_qubits}\n")
    #                 for urls_batch, sumQb, batch_num in batches:
    #                     file.write(f"  Batch #{batch_num}: [")
    #                     for url in urls_batch:
    #                         file.write(f"('{url[4]}', {url[1]} qubits, shots={url[2]}), ")
    #                     file.write("]\n")
    #                     file.write(f"    Total qubits usados: {sumQb}\n")

    #             # Construir el circuito único de la iteración
    #             code, qb = [], []
    #             shotsUsr = [1000] * sum(len(batch[0]) for batch in batches)  # 1000 fijo por circuito
    #             self.create_circuit(batches, code, qb, provider)

    #             print(f"///////// EJECUTANDO ITERACIÓN {self.iteracion_tiempo} /////////")
    #             data = {"code": code}

    #             # ⚠️ Aquí ya no paso urls_batch, sino todos los batches de la iteración
    #             all_urls = [url for batch in batches for url in batch[0]]
    #             executeCircuit(json.dumps(data), qb, shotsUsr, provider, all_urls, machine) #AQUI PARA EJECUTAR
    #             elementos_procesados_total += len(all_urls)

    #     if elementos_procesados_total == 0:
    #         print(f"\n⚠ Iteración {self.iteracion_tiempo} no generó batches (cola vacía o sin circuitos válidos).")
    #     else:
    #         print(f"\n✅ Iteración {self.iteracion_tiempo} completada con {len(batches)} batch(es).")
    #         print(f"📊 Circuitos procesados en esta iteración: {elementos_procesados_total}")
    #         print(f"📌 Total acumulado: {len(self.urls_ya_procesados)} circuitos únicos ejecutados.\n")

    

    # POLÍTICA DE TIEMPO HORIZONTAL
    # POLITICA DE TIEMPO HORIZONTAL
    # POLITICA DE TIEMPO HORIZONTAL
    # POLITICA DE TIEMPO HORIZONTAL
    # POLITICA DE TIEMPO HORIZONTAL
    # POLITICA DE TIEMPO HORIZONTAL
    # POLITICA DE TIEMPO HORIZONTAL
    # def send(self, queue: list, max_qubits: int, provider: str, executeCircuit: Callable, machine: str) -> None:
    #     """
    #     Ejecuta batches normalmente, pero cada vez que la suma total de qubits acumulados
    #     supera 20, ejecuta inmediatamente y continúa con la siguiente tanda.
    #     """
    #     if not queue:
    #         print("\n✅ No hay más elementos en la cola. Programa finalizado.\n")
    #         return

    #     if not hasattr(self, "urls_ya_procesados"):
    #         self.urls_ya_procesados = set()

    #     self.iteracion_tiempo += 1
    #     colas_sin_criterio = self.obtener_colas_sin_criterio(queue)

    #     file_name = os.path.join(CARPETA_SALIDAS, "criterio_tiempo.txt")
    #     elementos_procesados_total = 0

    #     LIMITE_EJECUCION_QUBITS = 65500  # 🔹 Ejecutar cuando se pase de 20 qubits acumulados

    #     for criterio, cola_original in colas_sin_criterio.items():
    #         if not cola_original:
    #             continue

    #         cola = list(cola_original)
    #         batches = []
    #         sumQb_total = 0
    #         batch_counter = 1  # 🔹 Contador que se reiniciará tras cada ejecución

    #         for url in list(cola):  # iteramos sobre copia
    #             if url in self.urls_ya_procesados:
    #                 continue

    #             # Intentamos meter el circuito actual en el batch activo o uno nuevo
    #             if not batches or (batches[-1][1] + url[1]) > max_qubits:
    #                 # nuevo batch
    #                 batches.append(([url], url[1], batch_counter))
    #                 batch_counter += 1
    #             else:
    #                 # añadir al último batch
    #                 batches[-1][0].append(url)
    #                 batches[-1] = (batches[-1][0], batches[-1][1] + url[1], batches[-1][2])

    #             # marcar procesado
    #             self.urls_ya_procesados.add(url)
    #             if url in queue:
    #                 queue.remove(url)
    #             if url in cola_original:
    #                 cola_original.remove(url)

    #             # actualizar suma global
    #             sumQb_total += url[1]

    #             # ⚡ Si superamos el límite global (20 qubits), ejecutamos inmediatamente
    #             if sumQb_total >= LIMITE_EJECUCION_QUBITS:
    #                 with open(file_name, "a") as file:
    #                     file.write(f"\n Iteración {self.iteracion_tiempo} - Máquina: {machine} -- Límite ejecución: {LIMITE_EJECUCION_QUBITS} qubits\n")
    #                     for urls_batch, sumQb_b, batch_num_b in batches:
    #                         file.write(f"  Batch #{batch_num_b}: [")
    #                         for u in urls_batch:
    #                             file.write(f"('{u[4]}', {u[1]} qubits, shots={u[2]}), ")
    #                         file.write("]\n")
    #                         file.write(f"    Total qubits usados: {sumQb_b}\n")

    #                 # Construir y ejecutar
    #                 code, qb = [], []
    #                 shotsUsr = [1000] * sum(len(batch[0]) for batch in batches)
    #                 self.create_circuit(batches, code, qb, provider)

    #                 print(f"///////// EJECUTANDO ITERACIÓN {self.iteracion_tiempo} /////////")
    #                 data = {"code": code}
    #                 all_urls = [u for batch in batches for u in batch[0]]

    #                 #executeCircuit(json.dumps(data), qb, shotsUsr, provider, all_urls, machine)
    #                 elementos_procesados_total += len(all_urls)

    #                 # 🔁 Reiniciamos para siguiente ejecución
    #                 self.iteracion_tiempo += 1
    #                 batches = []
    #                 sumQb_total = 0
    #                 batch_counter = 1  # Reinicia numeración de batches

    #         # ⚠ Si quedaron circuitos sin llegar a los 20 qubits finales, ejecutar esos también
    #         if batches:
    #             with open(file_name, "a") as file:
    #                 file.write(f"\n Iteración {self.iteracion_tiempo} - Máquina: {machine} -- Ejecución final parcial\n")
    #                 for urls_batch, sumQb_b, batch_num_b in batches:
    #                     file.write(f"  Batch #{batch_num_b}: [")
    #                     for u in urls_batch:
    #                         file.write(f"('{u[4]}', {u[1]} qubits, shots={u[2]}), ")
    #                     file.write("]\n")
    #                     file.write(f"    Total qubits usados: {sumQb_b}\n")

    #             code, qb = [], []
    #             shotsUsr = [1000] * sum(len(batch[0]) for batch in batches)
    #             self.create_circuit(batches, code, qb, provider)

    #             print(f"///////// EJECUTANDO ITERACIÓN FINAL {self.iteracion_tiempo} /////////")
    #             data = {"code": code}
    #             all_urls = [u for batch in batches for u in batch[0]]

    #             executeCircuit(json.dumps(data), qb, shotsUsr, provider, all_urls, machine)
    #             elementos_procesados_total += len(all_urls)

    #     if elementos_procesados_total == 0:
    #         print(f"\n⚠ Iteración {self.iteracion_tiempo} no generó batches (cola vacía o sin circuitos válidos).")
    #     else:
    #         print(f"\n✅ Iteraciones completadas. Circuitos totales procesados: {elementos_procesados_total}")
    #         print(f"📌 Total acumulado: {len(self.urls_ya_procesados)} circuitos únicos ejecutados.\n")



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
                    self.create_circuit(batches, code, qb, provider)

                    print(f"///////// EJECUTANDO ITERACIÓN {self.iteracion_tiempo} /////////")
                    data = {"code": code}
                    all_urls = [u for batch in batches for u in batch[0]]

                    executeCircuit(json.dumps(data), qb, shotsUsr, provider, all_urls, machine)
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
                self.create_circuit(batches, code, qb, provider)

                print(f"///////// EJECUTANDO ITERACIÓN FINAL {self.iteracion_tiempo} /////////")
                data = {"code": code}
                all_urls = [u for batch in batches for u in batch[0]]

                executeCircuit(json.dumps(data), qb, shotsUsr, provider, all_urls, machine)
                elementos_procesados_total += len(all_urls)

        if elementos_procesados_total == 0:
            print(f"\n⚠ Iteración {self.iteracion_tiempo} no generó batches (cola vacía o sin circuitos válidos).")
        else:
            print(f"\n✅ Iteraciones completadas. Circuitos totales procesados: {elementos_procesados_total}")
            print(f"📌 Total acumulado: {len(self.urls_ya_procesados)} circuitos únicos ejecutados.\n")





        
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