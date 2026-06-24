import numpy as np

def proportionalAllocation(total_shots:int,newCounts:dict,usershots:list) -> dict:
    """
    Applies proportional allocation to the results of a circuit execution.

    Args:
        total_shots (int): The total number of shots of the circuit execution.        
        newCounts (dict): The results of the circuit execution.        
        usershots (list): The number of shots to divide among the users.
    
    Returns:
        dict: The results of the circuit execution divided among the users.
    """
    proportions = {key: value / total_shots for key, value in newCounts.items()}
    # Calculate the number of shots to allocate to each key
    allocated_shots = {key: round(proportions[key] * usershots) for key in proportions.keys()} # round(...) or int(...). int is faster but round is more accurate
    # Create a new dictionary to store the counts of the allocated shots
    selected_counts = {key: allocated_shots[key] for key in allocated_shots.keys() if allocated_shots[key] > 0}
    return selected_counts

def stratifiedSampling(total_shots:int,newCounts:dict,usershots:list) -> dict:
    """
    Applies stratified sampling to the results of a circuit execution.

    Args:
        total_shots (int): The total number of shots of the circuit execution.        
        newCounts (dict): The results of the circuit execution.        
        usershots (list): The number of shots to divide among the users.
    
    Returns:
        dict: The results of the circuit execution divided among the users.
    """
    keys = list(newCounts.keys())
    probabilities = [value / total_shots for value in newCounts.values()]
    # Sample from the keys based on their probabilities
    sampled_keys = np.random.choice(keys, size=usershots, replace=True, p=probabilities) #This uses numpy instead of doing it manually to make it more readable
    # Create a new dictionary to store the counts of the sampled keys
    selected_counts = {key: np.count_nonzero(sampled_keys == key) for key in keys}
    return selected_counts

def divideResults(counts:dict, shots:list, provider:str, qb:list, users:list, circuit_name:list) -> list:
    """
    Divides the results of a circuit execution among the users that executed it.
    """
    result = []
    for i in range(len(shots)):
        newCounts = {}

        # 🟢 MEJORA: Calcular los puntos de corte UNA SOLA VEZ por circuito,
        # sacándolos del bucle interno masivo para ganar velocidad en el QML.
        rightRemovedQubits = sum(qb[0:i])
        leftRemovedQubits = sum(qb[i+1:])

        for key, value in counts.items():
            # Limpiamos posibles espacios en blanco que Qiskit a veces inserta
            clean_key = key.replace(" ", "")
            
            if provider == 'aws':
                data = clean_key[rightRemovedQubits:]
                data = data[:(len(data)-leftRemovedQubits)]
                data = data[::-1]
            else:
                # Recorte Little-Endian para IBM
                data = clean_key[leftRemovedQubits:]
                data = data[:(len(data)-rightRemovedQubits)]
            
            if data in newCounts:
                newCounts[data] += value
            else:
                newCounts[data] = value

        total_shots = sum(newCounts.values())
        if total_shots == shots[i]:
            selected_counts = newCounts
        else:
            selected_counts = stratifiedSampling(total_shots,newCounts,shots[i])

        print(users[i],': ',selected_counts)
        result.append({(users[i],circuit_name[i]):selected_counts})

    return result