"""
visualizar_grafo.py

Script para visualizar el grafo de qubits de una máquina cuántica específica.
Muestra los qubits con colores según su nivel de ruido.

Uso:
    python visualizar_grafo.py ibm_fez
    python visualizar_grafo.py ibm_heron
    
    Con particionado:
    python visualizar_grafo.py ibm_fez --partition 1 --partitions 4
"""

import sys
import argparse
import matplotlib.pyplot as plt
import networkx as nx
from graph_utils import build_graph
from config import USE_PARTITION, PARTITIONS, PARTITION_INDEX

DEFAULT_BACKEND_NAME = "ibm_fez"


def get_backend_data(backend_name: str = None, platform: str = "IBM"):
    """Obtiene coupling_map y properties del backend especificado."""
    if platform.upper() == "IBM":
        from ibm_api import get_backend_graph_with_backend
        
        resolved_backend_name = backend_name or DEFAULT_BACKEND_NAME
        print(f"Obteniendo datos del backend IBM: {resolved_backend_name}...")
        
        result = get_backend_graph_with_backend(resolved_backend_name)
        if not result or result[0] is None:
            raise RuntimeError(f"No se pudieron obtener los datos del backend IBM: {resolved_backend_name}")
        
        coupling_map, properties, _, backend_obj = result
        return coupling_map, properties, resolved_backend_name
    
    elif platform.upper() == "AWS":
        from aws_api import get_backend_graph_aws_with_device
        
        print(f"Obteniendo datos del backend AWS...")
        result = get_backend_graph_aws_with_device()
        if not result or result[0] is None:
            raise RuntimeError("No se pudieron obtener los datos del backend AWS")
        
        coupling_map, properties, _, _ = result
        return coupling_map, properties, "aws_ankaa3"
    
    else:
        raise ValueError(f"Plataforma no reconocida: {platform}")


def visualizar_grafo(
    backend_name: str = None,
    platform: str = "IBM",
    partition_mode: bool = False,
    partition_index: int = 1,
    partitions: int = 4,
    save_path: str = None
):
    """
    Visualiza el grafo de qubits de una máquina cuántica.
    
    Args:
        backend_name: Nombre del backend a visualizar
        platform: Plataforma (IBM o AWS)
        partition_mode: Si se desea usar particionado
        partition_index: Índice de la partición (1-based)
        partitions: Número de particiones
        save_path: Ruta para guardar la imagen (opcional)
    """
    
    # Obtener datos del backend
    coupling_map, properties, resolved_backend_name = get_backend_data(backend_name, platform)
    
    print(f"Construyendo grafo para {resolved_backend_name}...")
    
    # Construir grafo
    graph = build_graph(
        coupling_map,
        properties,
        partition_mode=partition_mode,
        partition_index=partition_index,
        partitions=partitions,
        partition_ranges=None,
    )
    
    # Información del grafo
    print(f"\n{'='*60}")
    print(f"Información del Grafo - {resolved_backend_name}")
    print(f"{'='*60}")
    print(f"Número de nodos (qubits): {graph.number_of_nodes()}")
    print(f"Número de aristas (conexiones): {graph.number_of_edges()}")
    
    if partition_mode:
        print(f"Modo particionado: SÍ (partición {partition_index} de {partitions})")
    else:
        print(f"Modo particionado: NO (mostrando todos los qubits)")
    
    # Estadísticas de ruido
    noise_values = [graph.nodes[node]['noise'] for node in graph.nodes()]
    if noise_values:
        min_noise = min(noise_values)
        max_noise = max(noise_values)
        avg_noise = sum(noise_values) / len(noise_values)
        print(f"\nEstadísticas de ruido:")
        print(f"  Mínimo: {min_noise:.6f}")
        print(f"  Máximo: {max_noise:.6f}")
        print(f"  Promedio: {avg_noise:.6f}")
    
    print(f"{'='*60}\n")
    
    # Crear figura
    fig, ax = plt.subplots(figsize=(14, 10))
    
    # Usar layout de spring para mejor visualización
    print("Calculando posiciones de nodos...")
    pos = nx.spring_layout(graph, k=0.5, iterations=50, seed=42)
    
    # Normalizar ruido para colormap
    noise_values = [graph.nodes[node]['noise'] for node in graph.nodes()]
    
    if noise_values:
        min_noise = min(noise_values)
        max_noise = max(noise_values)
        # Evitar división por cero
        if max_noise == min_noise:
            normalized_noise = [0.5] * len(noise_values)
        else:
            normalized_noise = [(n - min_noise) / (max_noise - min_noise) for n in noise_values]
    else:
        normalized_noise = []
    
    # Dibujar aristas
    nx.draw_networkx_edges(
        graph, pos,
        ax=ax,
        edge_color='gray',
        alpha=0.3,
        width=1.5
    )
    
    # Dibujar nodos con colormap basado en ruido
    nodes = graph.nodes()
    node_colors = normalized_noise if normalized_noise else [0.5] * len(nodes)
    
    nodes_collection = nx.draw_networkx_nodes(
        graph, pos,
        ax=ax,
        node_color=node_colors,
        node_size=400,
        cmap='RdYlGn_r',  # Rojo (ruido alto) a Verde (ruido bajo)
        vmin=0,
        vmax=1,
        alpha=0.9,
        edgecolors='black',
        linewidths=1.5
    )
    
    # Dibujar etiquetas de nodos
    nx.draw_networkx_labels(
        graph, pos,
        ax=ax,
        font_size=7,
        font_weight='bold'
    )
    
    # Colorbar para el ruido
    cbar = plt.colorbar(nodes_collection, ax=ax, label='Nivel de Ruido (normalizado)')
    
    # Títulos y etiquetas
    title = f"Grafo de Qubits - {resolved_backend_name}"
    if partition_mode:
        title += f"\n(Partición {partition_index} de {partitions})"
    
    ax.set_title(title, fontsize=16, fontweight='bold', pad=20)
    ax.axis('off')
    
    plt.tight_layout()
    
    # Guardar o mostrar
    if save_path:
        plt.savefig(save_path, dpi=300, bbox_inches='tight')
        print(f"Gráfico guardado en: {save_path}")
    else:
        plt.show()
    
    return graph


def main():
    parser = argparse.ArgumentParser(
        description="Visualizar el grafo de qubits de una máquina cuántica",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python visualizar_grafo.py ibm_fez
  python visualizar_grafo.py ibm_heron --partition 1 --partitions 4
  python visualizar_grafo.py ibm_fez --save grafo.png
        """
    )
    
    parser.add_argument(
        'backend',
        nargs='?',
        default=DEFAULT_BACKEND_NAME,
        help=f'Nombre del backend IBM (default: {DEFAULT_BACKEND_NAME})'
    )
    
    parser.add_argument(
        '--platform',
        choices=['IBM', 'AWS'],
        default='IBM',
        help='Plataforma cuántica (default: IBM)'
    )
    
    parser.add_argument(
        '--partition',
        type=int,
        default=1,
        help='Índice de la partición a visualizar (1-based, default: 1)'
    )
    
    parser.add_argument(
        '--partitions',
        type=int,
        default=4,
        help='Número total de particiones (default: 4)'
    )
    
    parser.add_argument(
        '--with-partition',
        action='store_true',
        help='Activar modo particionado'
    )
    
    parser.add_argument(
        '--save',
        type=str,
        help='Guardar gráfico en archivo (ej: grafo.png)'
    )
    
    args = parser.parse_args()
    
    try:
        graph = visualizar_grafo(
            backend_name=args.backend,
            platform=args.platform,
            partition_mode=args.with_partition,
            partition_index=args.partition,
            partitions=args.partitions,
            save_path=args.save
        )
        
        return 0
        
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
