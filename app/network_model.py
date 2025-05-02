# --- START OF FILE network_model.py ---

from collections import defaultdict, deque
from typing import Dict, List, Tuple, Optional, Set, Any, Union
import uuid
import math
import os
import json
from datetime import datetime
import shutil
import traceback

class BusinessNetwork:
    """
    Represents the business network with nodes, edges, and calculated metrics.
    Handles internal logic for node manipulation, metric calculation, and persistence.
    Removed 'risk' metric. 'value' defaults to 1000. 'profit' is sum of children's values.
    'criticality' reflects need for children based on threshold.
    """
    DEFAULT_NODE_VALUE = 1000.0

    def __init__(self, min_children_threshold: int = 2, balance_factor: float = 0.75):
        self.graph: Dict[str, List[Tuple[str, float]]] = defaultdict(list)
        self.nodes: Dict[str, Dict[str, Any]] = {}
        self.min_children_threshold: int = max(1, min_children_threshold)
        self.balance_factor: float = max(0, min(1, balance_factor))
        self.max_depth: int = 0
        script_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(script_dir)
        self.data_dir = os.path.join(project_root, "data")
        os.makedirs(self.data_dir, exist_ok=True)

    def add_node(self, parent_id: Optional[str] = None, node_id: Optional[str] = None, **kwargs) -> str:
        """
        Adds a new node. 'value' defaults to DEFAULT_NODE_VALUE if not provided.
        """
        is_root_node = not self.nodes
        is_explicit_root = parent_id is None and not is_root_node

        if is_explicit_root:
             raise ValueError("Cannot add multiple root nodes. Specify a 'parent_id'.")
        if parent_id is not None and parent_id not in self.nodes:
             raise ValueError(f"Parent node '{parent_id}' does not exist")
        elif not parent_id and not is_root_node:
             raise ValueError("Parent ID is required for non-root nodes in a non-empty network")

        # Determine node ID (handling potential collisions)
        if not node_id:
            if is_root_node:
                final_id = "root"
            else:
                base_id = f"{parent_id}.{len(self.graph.get(parent_id, [])) + 1}"
                final_id = base_id
                counter = 1
                while final_id in self.nodes:
                    final_id = f"{base_id}_{counter}"
                    counter += 1
        else:
            final_id = str(node_id)
            if final_id in self.nodes:
                 base_id = final_id
                 counter = 1
                 while final_id in self.nodes:
                     final_id = f"{base_id}_{counter}"
                     counter += 1
                 print(f"Warning: Provided node ID '{node_id}' already exists. Using '{final_id}' instead.")

        # --- Add the node with default value ---
        try:
            # Use provided value or default. Ensure it's float. Handle None/empty string.
            raw_value = kwargs.get('value')
            node_value = self.DEFAULT_NODE_VALUE if raw_value is None or raw_value == '' else float(raw_value)
        except (ValueError, TypeError):
             raise ValueError("Invalid format for 'value' property. Must be a number.")

        self.nodes[final_id] = {
            "id": final_id,
            "parents": [],
            "value": node_value, # Set the base value property
            # Initialize other metrics to defaults
            "depth": 0, "children_count": 0, "total_children": 0,
            "is_chokepoint": False, "suggested_child_count": self.min_children_threshold,
            "needed_children": 0, "balance_score": 1.0, "profit": 0.0,
            "criticality": 0.0,
            # Add other non-metric kwargs passed, excluding 'value' which is handled
            **{k: v for k, v in kwargs.items() if k != 'value'}
        }
        if final_id not in self.graph:
            self.graph[final_id] = []

        # --- Connect to parent ---
        if parent_id is not None:
            capacity = 1.0
            if parent_id not in self.graph: self.graph[parent_id] = []
            self.graph[parent_id].append((final_id, capacity))
            self.nodes[final_id]["parents"].append(parent_id)

        self._update_metrics()
        return final_id

    def remove_node(self, node_id: str) -> bool:
        """Removes a leaf node."""
        if node_id not in self.nodes:
            raise ValueError(f"Node '{node_id}' not found")
        if node_id in self.graph and self.graph[node_id]:
            raise ValueError("Cannot remove node with children. Remove children first.")

        parent_ids = self.nodes[node_id].get("parents", [])
        for parent_id in parent_ids:
            if parent_id in self.graph:
                self.graph[parent_id] = [(child, cap) for child, cap in self.graph[parent_id] if child != node_id]

        del self.nodes[node_id]
        if node_id in self.graph:
             del self.graph[node_id]

        self._update_metrics()
        return True

    def get_node(self, node_id: str) -> Optional[Dict[str, Any]]:
        return self.nodes.get(node_id)

    def get_direct_children(self, node_id: str) -> List[str]:
        return [child_id for child_id, _ in self.graph.get(node_id, [])]

    def get_all_descendants(self, node_id: str) -> Set[str]:
        if node_id not in self.nodes: return set()
        descendants = set()
        queue = deque(self.get_direct_children(node_id))
        while queue:
            current_node_id = queue.popleft()
            if current_node_id in self.nodes and current_node_id not in descendants:
                descendants.add(current_node_id)
                for child_id in self.get_direct_children(current_node_id):
                    if child_id not in descendants:
                        queue.append(child_id)
        return descendants

    def get_network_data(self) -> Dict[str, Any]:
        """Get network data including nodes, graph, and settings."""
        settings = {
            "min_children_threshold": self.min_children_threshold,
            "balance_factor": self.balance_factor,
            "max_depth": self.max_depth
        }
        serializable_graph = {node_id: edges for node_id, edges in self.graph.items()}
        return {"nodes": self.nodes, "graph": serializable_graph, "settings": settings}

    # --- Metric Calculation Methods ---

    def _calculate_depth(self, node_id: str, visited: Set[str]) -> int:
        # (Same as before - calculates depth topologically or recursively)
        if node_id not in self.nodes or node_id in visited: return 0
        visited.add(node_id)
        parents = self.nodes[node_id].get("parents", [])
        if not parents:
             visited.remove(node_id); return 0
        max_parent_depth = -1
        for parent_id in parents:
             if parent_id in self.nodes:
                  max_parent_depth = max(max_parent_depth, self._calculate_depth(parent_id, visited))
             else:
                  print(f"Warning: Node '{node_id}' lists non-existent parent '{parent_id}'.")
        depth = max_parent_depth + 1 if max_parent_depth >= 0 else 0
        visited.remove(node_id)
        return depth

    def _calculate_total_children(self, node_id: str) -> int:
        """Calculate the total number of descendants (direct and indirect)."""
        return len(self.get_all_descendants(node_id))

    def _calculate_profit(self, node_id: str) -> float:
        """NEW: Calculate profit as the sum of the 'value' of direct children."""
        profit = 0.0
        if node_id not in self.nodes: return 0.0

        child_ids = self.get_direct_children(node_id)
        for child_id in child_ids:
            child_node = self.nodes.get(child_id)
            if child_node:
                profit += child_node.get("value", 0.0) # Sum up children's base value

        return round(max(0.0, profit), 2)

    # REMOVED: _calculate_risk

    # REMOVED: _calculate_ponzi_value (using 'value' property directly)

    def _calculate_criticality(self, node_id: str) -> float:
        """
        NEW: Calculate criticality based on the depth (the importance) of the node if a node needs children, if many on the same level need children, the one with the
        least amount of existing children is the most critical. (1/depth ) + (1/treshold-children_count)

        """
        node = self.nodes.get(node_id)
        if not node: return 0.0
        depth = node.get("depth", 0)
        children_count = node.get("children_count", 0)
        if depth <= 0: return 0.0
        if self.min_children_threshold <= 0: return 0.0
        if self.min_children_threshold <= children_count: return 0.0
        
        criticality = 1/depth 
        return criticality






    def _calculate_suggested_child_count(self, node_id: str) -> int:
        """Calculate the suggested number of children needed."""
        node = self.nodes.get(node_id)
        if not node: return self.min_children_threshold
        depth = node.get("depth", 0)
        # Same logic as before - adjust if needed
        if depth == 0: return max(3, self.min_children_threshold + 1)
        elif depth <= 2: return max(2, self.min_children_threshold)
        else: return self.min_children_threshold


    def _calculate_balance_score(self, node_id: str) -> float:
        """Calculate balance score based on the children count of other nodes on the same depth """
        node = self.nodes.get(node_id)
        if not node: return 1.0
        depth = node.get("depth", 0)
        nodes_on_same_depth = [n for n in self.nodes.values() if n.get("depth", 0) == depth]
        children_count = node.get("children_count", 0)
        
        # Calculate balance score
        balance_score = 1.0
        for n in nodes_on_same_depth:
            if n.get("children_count", 0) > children_count:
                balance_score -= 0.1
        return round(max(0.0, balance_score), 3)



    def get_unbalanced_nodes(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Get nodes needing children, prioritized by imbalance (criticality) and depth."""
        candidates = []
        for node_id, node_data in self.nodes.items():
             # Use criticality score now as a primary indicator of imbalance
             criticality = node_data.get("criticality", 0.0)
             needed_children = node_data.get("needed_children", 0)

             if needed_children > 0 and criticality > 0: # Only suggest nodes that are actually critical
                 depth = node_data.get("depth", 0)
                 # Priority: Higher for higher criticality, higher for lower depth
                 depth_weight = max(0.1, 1.0 - (depth * 0.1)) # Weight depth more
                 # Priority score based on criticality and depth
                 priority = criticality * depth_weight

                 candidates.append({
                     "id": node_id,
                     "criticality": criticality, # Include new criticality score
                     "current_children": node_data.get("children_count", 0),
                     "suggested_children": node_data.get("suggested_child_count", self.min_children_threshold),
                     "needed_children": needed_children,
                     "depth": depth,
                     "priority": round(priority, 4),
                     "profit": node_data.get("profit", 0), # Include profit for context
                     "value": node_data.get("value", self.DEFAULT_NODE_VALUE) # Include base value
                 })

        candidates.sort(key=lambda x: x["priority"], reverse=True)
        return candidates[:limit]

    def _update_metrics(self) -> None:
        """Update all calculated metrics for all nodes."""
        # --- Depth Calculation (using Topological Sort) ---
        self.max_depth = 0
        nodes_to_process = deque()
        in_degree = {nid: 0 for nid in self.nodes}
        processed_nodes = set()
        node_depths = {}

        for node_id in self.nodes:
            valid_parents = [p for p in self.nodes[node_id].get("parents", []) if p in self.nodes]
            self.nodes[node_id]["parents"] = valid_parents
            in_degree[node_id] = len(valid_parents)
            if in_degree[node_id] == 0:
                nodes_to_process.append(node_id)
                node_depths[node_id] = 0

        while nodes_to_process:
            node_id = nodes_to_process.popleft()
            if node_id in processed_nodes: continue
            processed_nodes.add(node_id)
            current_depth = node_depths.get(node_id, 0)
            self.nodes[node_id]["depth"] = current_depth
            self.max_depth = max(self.max_depth, current_depth)

            for child_id in self.get_direct_children(node_id):
                if child_id in in_degree:
                    in_degree[child_id] -= 1
                    node_depths[child_id] = max(node_depths.get(child_id, 0), current_depth + 1)
                    if in_degree[child_id] == 0:
                        nodes_to_process.append(child_id)

        if len(processed_nodes) != len(self.nodes):
            unprocessed = set(self.nodes.keys()) - processed_nodes
            print(f"Warning: Cycle detected or orphaned nodes? Processed {len(processed_nodes)}/{len(self.nodes)}. Unprocessed: {unprocessed}")
            for node_id in unprocessed:
                 # Try recursive calc for orphans/cycles, limit depth
                 calculated_depth = self._calculate_depth(node_id, set())
                 self.nodes[node_id]["depth"] = min(calculated_depth, len(self.nodes) + 1) # Limit depth
                 self.max_depth = max(self.max_depth, self.nodes[node_id]["depth"])


        # --- Calculate other metrics in order ---
        # 1. Counts (Direct Children, Total Descendants)
        all_descendants_map = {nid: self.get_all_descendants(nid) for nid in self.nodes}
        for node_id in self.nodes:
             self.nodes[node_id]["children_count"] = len(self.get_direct_children(node_id))
             self.nodes[node_id]["total_children"] = len(all_descendants_map.get(node_id, set()))

        # 2. Profit (Depends on children having 'value' - 'value' is set on add/load)
        # Needs to be calculated after children counts are stable, but before criticality/balance potentially
        for node_id in self.nodes:
             self.nodes[node_id]["profit"] = self._calculate_profit(node_id)

        # 3. Suggested Children & Needed Children (Depend on depth and threshold)
        for node_id in self.nodes:
             suggested = self._calculate_suggested_child_count(node_id)
             self.nodes[node_id]["suggested_child_count"] = suggested
             needed = max(0, suggested - self.nodes[node_id]["children_count"])
             self.nodes[node_id]["needed_children"] = needed
             self.nodes[node_id]["is_chokepoint"] = needed > 0 # Update chokepoint flag

        # 4. Criticality (Depends on needed_children)
        for node_id in self.nodes:
            self.nodes[node_id]["criticality"] = self._calculate_criticality(node_id)

        # 5. Balance Score (Depends on counts, suggestions, descendant counts)
        for node_id in self.nodes:
             self.nodes[node_id]["balance_score"] = self._calculate_balance_score(node_id)
        # print("Metrics update complete.")


    # --- Persistence Methods ---

    def save(self, filename: str = "network.json") -> None:
        """Save the network state to JSON."""
        file_path = os.path.join(self.data_dir, filename)
        backup_path = None
        if os.path.exists(file_path):
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            backup_filename = f"{os.path.splitext(filename)[0]}_backup_{timestamp}.json"
            backup_path = os.path.join(self.data_dir, backup_filename)
            try: shutil.copy2(file_path, backup_path)
            except Exception as e: print(f"Error creating backup: {e}"); backup_path = None

        temp_file_path = file_path + ".tmp"
        try:
            network_data = self.get_network_data()
            with open(temp_file_path, 'w') as f:
                json.dump(network_data, f, indent=2)
            os.replace(temp_file_path, file_path)
        except Exception as e:
            print(f"Error saving network: {e}")
            if os.path.exists(temp_file_path):
                try: os.remove(temp_file_path)
                except OSError as rm_err: print(f"Error removing temp save file: {rm_err}")
            # Optional: Restore from backup on save failure
            # if backup_path and os.path.exists(backup_path): try: shutil.copy2(backup_path, file_path); print("Restored from backup.") except Exception as r_e: print(f"FATAL: Save failed & Restore failed: {r_e}")
            raise

    @classmethod
    def load(cls, filename: str = "network.json") -> 'BusinessNetwork':
        """Load network state from JSON, applying defaults for missing fields."""
        script_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(script_dir)
        data_dir = os.path.join(project_root, "data")
        file_path = os.path.join(data_dir, filename)

        if not os.path.exists(file_path):
            print(f"Network file not found at {file_path}. Creating new network.")
            return cls()

        try:
            with open(file_path, 'r') as f: data = json.load(f)
            settings = data.get("settings", {})
            network = cls(
                min_children_threshold=settings.get("min_children_threshold", 2),
                balance_factor=settings.get("balance_factor", 0.75)
            )

            loaded_nodes = data.get("nodes", {})
            for node_id, node_data in loaded_nodes.items():
                # Provide defaults for all expected fields during load
                node_data.setdefault("id", node_id)
                node_data.setdefault("parents", [])
                node_data.setdefault("value", cls.DEFAULT_NODE_VALUE) # Default value
                node_data.setdefault("depth", 0); node_data.setdefault("children_count", 0)
                node_data.setdefault("total_children", 0); node_data.setdefault("profit", 0.0)
                node_data.setdefault("is_chokepoint", False); node_data.setdefault("suggested_child_count", network.min_children_threshold)
                node_data.setdefault("needed_children", 0); node_data.setdefault("criticality", 0.0)
                node_data.setdefault("balance_score", 1.0)
                # Remove risk if present from older files
                node_data.pop("risk", None)
                node_data.pop("ponzi_value", None) # Remove old metric name

                network.nodes[node_id] = node_data

            loaded_graph = data.get("graph", {})
            network.graph = defaultdict(list)
            for node_id, edges in loaded_graph.items():
                 if node_id in network.nodes:
                     network.graph[node_id] = [
                         tuple(edge) if isinstance(edge, list) and len(edge) == 2 else edge
                         for edge in edges if isinstance(edge, (list, tuple)) and len(edge) > 0 and edge[0] in network.nodes
                     ]

            for node_id in network.nodes: network.graph.setdefault(node_id, [])

            network._update_metrics() # Recalculate all metrics based on loaded data/settings
            print(f"Network loaded and metrics recalculated from {file_path}")
            return network
        except json.JSONDecodeError as json_err:
             print(f"Error decoding JSON: {json_err}. Returning new network.")
             return cls()
        except Exception as e:
            print(f"Error loading network: {e}. Returning new network.")
            print(traceback.format_exc())
            return cls()

    @classmethod
    def from_json(cls, json_data: Union[str, bytes]) -> 'BusinessNetwork':
        """Create network from JSON string/bytes (used for import), applying defaults."""
        try:
            data = json.loads(json_data)
            if not isinstance(data.get("nodes"), dict) or not isinstance(data.get("graph"), dict):
                 raise ValueError("Invalid JSON structure: Missing 'nodes' or 'graph'.")

            settings = data.get("settings", {})
            network = cls(
                min_children_threshold=settings.get("min_children_threshold", 2),
                balance_factor=settings.get("balance_factor", 0.75)
            )

            loaded_nodes = data.get("nodes", {})
            for node_id, node_data in loaded_nodes.items():
                if not isinstance(node_data, dict): continue
                # Set defaults for required/calculated fields
                node_data.setdefault("id", node_id)
                node_data.setdefault("parents", [])
                node_data.setdefault("value", cls.DEFAULT_NODE_VALUE) # Default value
                node_data.setdefault("depth", 0); node_data.setdefault("children_count", 0); node_data.setdefault("total_children", 0); node_data.setdefault("profit", 0.0)
                node_data.setdefault("is_chokepoint", False); node_data.setdefault("suggested_child_count", network.min_children_threshold); node_data.setdefault("needed_children", 0)
                node_data.setdefault("criticality", 0.0); node_data.setdefault("balance_score", 1.0)
                 # Remove risk if present from older files
                node_data.pop("risk", None)
                node_data.pop("ponzi_value", None)

                # Validate value format if present
                try:
                     if "value" in node_data: node_data["value"] = float(node_data["value"])
                except (ValueError, TypeError):
                     print(f"Warning: Invalid value format for node '{node_id}'. Using default.")
                     node_data["value"] = cls.DEFAULT_NODE_VALUE

                network.nodes[node_id] = node_data


            loaded_graph = data.get("graph", {})
            network.graph = defaultdict(list)
            for node_id, edges in loaded_graph.items():
                if node_id in network.nodes and isinstance(edges, list):
                    valid_edges = []
                    for edge in edges:
                         if isinstance(edge, (list, tuple)) and len(edge) >= 1 and edge[0] in network.nodes:
                             capacity = 1.0
                             if len(edge) > 1: 
                                 try: capacity = float(edge[1]) 
                                 except (ValueError, TypeError): pass
                             valid_edges.append( (str(edge[0]), capacity) )
                    network.graph[node_id] = valid_edges

            for node_id in network.nodes: network.graph.setdefault(node_id, [])

            network._update_metrics() # Recalculate all metrics
            return network
        except json.JSONDecodeError as json_err:
             raise ValueError(f"Invalid JSON data provided: {json_err}") from json_err
        except ValueError as ve: raise ve
        except Exception as e:
            print(f"Error creating network from JSON data: {e}\n{traceback.format_exc()}")
            raise ValueError(f"Failed to create network from JSON: {e}") from e

# --- END OF FILE network_model.py ---