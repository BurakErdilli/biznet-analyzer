
from collections import defaultdict, deque
from typing import Dict, List, Tuple, Optional, Set, Any, Union
import uuid
import math
import os
import json
from datetime import datetime
import shutil
import traceback
import copy # For deep copying subtree data

class BusinessNetwork:
    """
    Represents the business network with nodes, edges, and calculated metrics.
    Handles internal logic for node manipulation, metric calculation, and persistence.
    'value' defaults to DEFAULT_NODE_VALUE. 'profit' is sum of children's values.
    'criticality' reflects need for children based on threshold.
    Removed balance factor/score.
    Added subtree import functionality.
    """
    DEFAULT_NODE_VALUE = 1000.0

    def __init__(self, min_children_threshold: int = 2):
        self.graph: Dict[str, List[Tuple[str, float]]] = defaultdict(list)
        self.nodes: Dict[str, Dict[str, Any]] = {}
        self.min_children_threshold: int = max(1, min_children_threshold) # Balance factor removed
        self.max_depth: int = 0
        script_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(script_dir)
        self.data_dir = os.path.join(project_root, "data")
        os.makedirs(self.data_dir, exist_ok=True)

    def _generate_unique_id(self, base_id: str) -> str:
        """Generates a unique ID based on base_id, adding suffix if needed."""
        final_id = base_id
        counter = 1
        while final_id in self.nodes:
            final_id = f"{base_id}_{counter}"
            counter += 1
        return final_id

    def add_node(self, parent_id: Optional[str] = None, node_id: Optional[str] = None, **kwargs) -> str:
        """
        Adds a new node. 'value' defaults to DEFAULT_NODE_VALUE if not provided.
        Handles ID generation and potential collisions.
        """
        is_root_node = not self.nodes
        is_explicit_root = parent_id is None and not is_root_node

        if is_explicit_root:
             raise ValueError("Cannot add multiple root nodes. Specify a 'parent_id'.")
        if parent_id is not None and parent_id not in self.nodes:
             raise ValueError(f"Parent node '{parent_id}' does not exist")
        elif not parent_id and not is_root_node:
             raise ValueError("Parent ID is required for non-root nodes in a non-empty network")

        # Determine node ID
        if not node_id:
            if is_root_node:
                final_id = "root"
            else:
                 # Generate ID based on parent and number of siblings already present
                 base_id = f"{parent_id}.{len(self.graph.get(parent_id, [])) + 1}"
                 final_id = self._generate_unique_id(base_id)
        else:
            final_id = self._generate_unique_id(str(node_id))
            if final_id != str(node_id):
                 print(f"Warning: Provided node ID '{node_id}' already exists or invalid. Using '{final_id}' instead.")

        # Add the node with default value
        try:
            raw_value = kwargs.get('value')
            node_value = self.DEFAULT_NODE_VALUE if raw_value is None or raw_value == '' else float(raw_value)
        except (ValueError, TypeError):
             raise ValueError("Invalid format for 'value' property. Must be a number.")

        self.nodes[final_id] = {
            "id": final_id,
            "parents": [],
            "value": node_value,
            "depth": 0, "children_count": 0, "total_children": 0,
            "is_chokepoint": False, "suggested_child_count": self.min_children_threshold,
            "needed_children": 0, "profit": 0.0, "criticality": 0.0,
            # Balance score removed
            **{k: v for k, v in kwargs.items() if k not in ['value', 'balance_score']} # Ensure balance_score is not added
        }
        if final_id not in self.graph:
            self.graph[final_id] = []

        # Connect to parent
        if parent_id is not None:
            capacity = 1.0 # Default capacity
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
             del self.graph[node_id] # Remove entry from graph dict if exists

        self._update_metrics()
        return True

    # --- NEW: Add Subtree Functionality ---
    def add_subtree_from_data(self, parent_id: str, subtree_data: Dict[str, Any]) -> List[str]:
        """
        Adds a network structure defined in subtree_data as children of parent_id.
        Handles ID collisions by prefixing. Assumes subtree_data has 'nodes' and 'graph'.
        """
        if parent_id not in self.nodes:
            raise ValueError(f"Parent node '{parent_id}' not found.")
        if not isinstance(subtree_data, dict) or "nodes" not in subtree_data or "graph" not in subtree_data:
            raise ValueError("Invalid subtree data format. Missing 'nodes' or 'graph'.")

        subtree_nodes_data = subtree_data.get("nodes", {})
        subtree_graph_data = subtree_data.get("graph", {})

        if not subtree_nodes_data:
            return [] # Nothing to add

        # Find root(s) of the subtree (nodes with no parents *within the subtree*)
        subtree_node_ids = set(subtree_nodes_data.keys())
        nodes_with_parents_in_subtree = set()
        for src, edges in subtree_graph_data.items():
            for target, _ in edges:
                 if target in subtree_node_ids:
                     nodes_with_parents_in_subtree.add(target)

        subtree_roots = [nid for nid in subtree_node_ids if nid not in nodes_with_parents_in_subtree]
        if not subtree_roots:
             raise ValueError("Subtree seems to have a cycle or no clear root(s).")

        # Use a prefix to avoid collisions with existing network IDs
        # Simple prefix based on parent ID and current time/randomness
        prefix = f"{parent_id}_sub{datetime.now().strftime('%H%M%S%f')[-8:]}_"

        id_mapping = {} # Map original subtree ID -> new prefixed ID in the main network
        added_node_ids = []

        # Use BFS/DFS starting from subtree roots to add nodes and edges
        queue = deque(subtree_roots)
        processed_in_subtree = set()

        while queue:
            original_id = queue.popleft()
            if original_id in processed_in_subtree or original_id not in subtree_nodes_data:
                continue
            processed_in_subtree.add(original_id)

            node_data = copy.deepcopy(subtree_nodes_data[original_id]) # Copy data
            new_id = self._generate_unique_id(prefix + original_id) # Ensure uniqueness even with prefix
            id_mapping[original_id] = new_id

            # Extract value, default if missing/invalid
            try:
                 raw_value = node_data.get('value')
                 node_value = self.DEFAULT_NODE_VALUE if raw_value is None or raw_value == '' else float(raw_value)
            except (ValueError, TypeError):
                 node_value = self.DEFAULT_NODE_VALUE
                 print(f"Warning: Invalid value for imported node '{original_id}'. Using default.")

            # Add the node to the main network
            self.nodes[new_id] = {
                "id": new_id,
                "parents": [], # Parents will be updated below
                "value": node_value,
                "depth": 0, "children_count": 0, "total_children": 0,
                "is_chokepoint": False, "suggested_child_count": self.min_children_threshold,
                "needed_children": 0, "profit": 0.0, "criticality": 0.0,
                 # Add other properties from import, excluding calculated/internal ones
                 **{k: v for k, v in node_data.items() if k not in [
                     'id', 'parents', 'value', 'depth', 'children_count', 'total_children',
                     'profit', 'criticality', 'is_chokepoint', 'needed_children',
                     'suggested_child_count', 'balance_score', 'risk', 'ponzi_value'
                 ]}
            }
            if new_id not in self.graph: self.graph[new_id] = []
            added_node_ids.append(new_id)

            # Connect to the main parent if it's a root of the subtree
            if original_id in subtree_roots:
                self.graph[parent_id].append((new_id, 1.0)) # Connect to main parent
                self.nodes[new_id]["parents"].append(parent_id)

            # Process children within the subtree
            if original_id in subtree_graph_data:
                for child_original_id, capacity in subtree_graph_data[original_id]:
                    if child_original_id in subtree_nodes_data: # Ensure child is part of the imported subtree
                         if child_original_id not in processed_in_subtree: # Add child to queue if not processed
                             queue.append(child_original_id)
                         # If child is already processed (possible in DAGs), connect edge later
                         # Edges within the subtree are handled after all nodes are mapped

        # Connect edges within the newly added subtree
        for original_src, new_src in id_mapping.items():
            if original_src in subtree_graph_data:
                 for original_target, capacity in subtree_graph_data[original_src]:
                     if original_target in id_mapping: # Check if target was added
                         new_target = id_mapping[original_target]
                         # Add edge in main graph
                         if new_src not in self.graph: self.graph[new_src] = []
                         self.graph[new_src].append((new_target, float(capacity if capacity is not None else 1.0)))
                         # Add parent link in main nodes structure
                         if new_target in self.nodes and new_src not in self.nodes[new_target]["parents"]:
                              self.nodes[new_target]["parents"].append(new_src)

        if len(processed_in_subtree) != len(subtree_node_ids):
             print(f"Warning: Some nodes in the subtree data might not have been added (possible disconnection). Added {len(processed_in_subtree)} out of {len(subtree_node_ids)}.")

        self._update_metrics() # Update metrics for the whole network
        return added_node_ids

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
            # "balance_factor": self.balance_factor, # Removed
            "max_depth": self.max_depth
        }
        # Ensure graph is serializable (list of tuples)
        serializable_graph = {node_id: list(edges) for node_id, edges in self.graph.items()}
        return {"nodes": self.nodes, "graph": serializable_graph, "settings": settings}

    # --- Metric Calculation Methods ---

    def _calculate_depth(self, node_id: str, visited: Set[str]) -> int:
        """Calculates depth topologically or recursively. Helper for _update_metrics."""
        if node_id not in self.nodes: return 0 # Should not happen if called from _update_metrics
        # Base case: root nodes (or nodes whose parents aren't in self.nodes yet during calculation)
        parents = self.nodes[node_id].get("parents", [])
        valid_parents = [p for p in parents if p in self.nodes] # Check parents exist

        if not valid_parents:
             return 0

        # Avoid infinite recursion in case of cycles during calculation
        if node_id in visited:
            print(f"Warning: Cycle detected involving node '{node_id}' during depth calculation. Assigning large depth.")
            return len(self.nodes) + 1 # Assign a large depth to indicate cycle

        visited.add(node_id)
        max_parent_depth = -1
        for parent_id in valid_parents:
            # Recursively find depth of parents
            # Use node's stored depth if already calculated in this update cycle, otherwise recurse
            parent_depth = self.nodes[parent_id].get('_current_depth_calculation') # Temp storage during update
            if parent_depth is None:
                parent_depth = self._calculate_depth(parent_id, visited)

            max_parent_depth = max(max_parent_depth, parent_depth)

        visited.remove(node_id) # Backtrack: remove current node from visited path

        # Depth is 1 + max depth of parents
        depth = max_parent_depth + 1 if max_parent_depth >= 0 else 0
        self.nodes[node_id]['_current_depth_calculation'] = depth # Store temporarily
        return depth


    def _calculate_total_children(self, node_id: str) -> int:
        """Calculate the total number of descendants (direct and indirect)."""
        return len(self.get_all_descendants(node_id))

    def _calculate_profit(self, node_id: str) -> float:
        """Calculate profit as the sum of the 'value' of direct children."""
        profit = 0.0
        if node_id not in self.nodes: return 0.0

        child_ids = self.get_direct_children(node_id)
        for child_id in child_ids:
            child_node = self.nodes.get(child_id)
            if child_node:
                profit += child_node.get("value", 0.0) # Sum up children's base value

        return round(max(0.0, profit), 2)


    def _calculate_criticality(self, node_id: str) -> float:
        """
        Calculate criticality based on how many children are needed compared to the threshold.
        A score between 0 (not critical) and 1 (highly critical).
        Based on needed children and depth (deeper nodes are slightly less critical for the same need).
        """
        node = self.nodes.get(node_id)
        if not node: return 0.0

        children_count = node.get("children_count", 0)
        needed_children = max(0, self.min_children_threshold - children_count)

        if needed_children <= 0:
            return 0.0 # Not critical if threshold is met or exceeded

        # Normalize needed children based on threshold (0 to 1 range)
        # If threshold is 2 and node has 0 children, need_ratio = 2/2 = 1.0
        # If threshold is 2 and node has 1 child, need_ratio = 1/2 = 0.5
        need_ratio = min(1.0, needed_children / max(1, self.min_children_threshold))

        # Factor in depth: deeper nodes are slightly less critical for the same need_ratio
        depth = node.get("depth", 0)
        # Depth factor decreases criticality slightly as depth increases
        # Example: depth 0 -> factor 1.0, depth 5 -> factor ~0.83, depth 10 -> ~0.7
        depth_factor = 1 / (1 + 0.04 * depth) # Adjust the 0.04 to tune depth influence

        criticality = need_ratio * depth_factor

        # Ensure criticality is between 0 and 1
        return round(max(0.0, min(1.0, criticality)), 3)


    def _calculate_suggested_child_count(self, node_id: str) -> int:
        """Calculate the suggested number of children needed based on threshold (simplified)."""
        # Now simply returns the threshold, as specific depth logic was less critical
        return self.min_children_threshold

    # REMOVED: _calculate_balance_score

    def get_unbalanced_nodes(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Get nodes needing children, prioritized by criticality and then depth."""
        candidates = []
        for node_id, node_data in self.nodes.items():
             criticality = node_data.get("criticality", 0.0)
             needed_children = node_data.get("needed_children", 0)

             if needed_children > 0 and criticality > 0: # Only suggest nodes that are actually critical
                 depth = node_data.get("depth", 0)
                 # Priority: Higher criticality first. If tied, lower depth (higher in tree) is slightly preferred.
                 priority = (criticality * 100) - depth # Simple priority score

                 candidates.append({
                     "id": node_id,
                     "criticality": criticality,
                     "current_children": node_data.get("children_count", 0),
                     "suggested_children": node_data.get("suggested_child_count", self.min_children_threshold),
                     "needed_children": needed_children,
                     "depth": depth,
                     "priority": round(priority, 4),
                     "profit": node_data.get("profit", 0),
                     "value": node_data.get("value", self.DEFAULT_NODE_VALUE)
                 })

        # Sort primarily by priority (descending)
        candidates.sort(key=lambda x: x["priority"], reverse=True)
        return candidates[:limit]

    def _update_metrics(self) -> None:
        """Update all calculated metrics for all nodes."""
        if not self.nodes:
             self.max_depth = 0
             return # No nodes to update

        # --- Depth Calculation (using Topological Sort approach) ---
        self.max_depth = 0
        nodes_to_process = deque()
        in_degree = {nid: 0 for nid in self.nodes}
        processed_nodes = set()
        node_depths = {} # Store calculated depths {node_id: depth}

        # Initialize in-degrees and find initial nodes (roots)
        for node_id in self.nodes:
            valid_parents = [p for p in self.nodes[node_id].get("parents", []) if p in self.nodes]
            self.nodes[node_id]["parents"] = valid_parents # Clean up parent list
            in_degree[node_id] = len(valid_parents)
            if in_degree[node_id] == 0:
                nodes_to_process.append(node_id)
                node_depths[node_id] = 0 # Root nodes have depth 0

        # Process nodes layer by layer
        while nodes_to_process:
            node_id = nodes_to_process.popleft()
            if node_id in processed_nodes: continue # Should not happen with DAG but safety check
            processed_nodes.add(node_id)

            current_depth = node_depths.get(node_id, 0)
            self.nodes[node_id]["depth"] = current_depth
            self.max_depth = max(self.max_depth, current_depth)

            # Update children's in-degree and depth
            for child_id in self.get_direct_children(node_id):
                if child_id in in_degree: # Ensure child exists in the network
                    in_degree[child_id] -= 1
                    # Depth of child is max(its current calculated depth, parent_depth + 1)
                    node_depths[child_id] = max(node_depths.get(child_id, 0), current_depth + 1)
                    if in_degree[child_id] == 0:
                        nodes_to_process.append(child_id)
                # else: # This case should ideally not happen if graph/nodes are consistent
                     # print(f"Warning: Child '{child_id}' listed for node '{node_id}' not found in in_degree map.")


        # Handle nodes potentially missed by topological sort (e.g., cycles or disconnected components after initial roots)
        if len(processed_nodes) != len(self.nodes):
            unprocessed = set(self.nodes.keys()) - processed_nodes
            print(f"Warning: Potential cycle or disconnected nodes detected. Processed {len(processed_nodes)}/{len(self.nodes)}. Unprocessed: {unprocessed}")
            # Assign a large depth to unprocessed nodes or attempt recursive calc with cycle detection
            for node_id in unprocessed:
                if node_id not in self.nodes: continue
                if "depth" not in self.nodes[node_id] or self.nodes[node_id].get('_current_depth_calculation') is None:
                     # Attempt recursive calculation with cycle detection for these nodes
                     self.nodes[node_id].pop('_current_depth_calculation', None) # Clear any temp state
                     visited_rec = set()
                     calculated_depth = self._calculate_depth(node_id, visited_rec)
                     self.nodes[node_id]["depth"] = calculated_depth
                     self.max_depth = max(self.max_depth, calculated_depth)
                     # Clear temp calculation state for all nodes after recursive calls
                     for nid in self.nodes: nid_data = self.nodes.get(nid); nid_data.pop('_current_depth_calculation', None)


        # --- Calculate other metrics in order ---
        # 1. Counts (Direct Children, Total Descendants)
        all_descendants_map = {nid: self.get_all_descendants(nid) for nid in self.nodes}
        for node_id in self.nodes:
             self.nodes[node_id]["children_count"] = len(self.get_direct_children(node_id))
             self.nodes[node_id]["total_children"] = len(all_descendants_map.get(node_id, set()))

        # 2. Profit (Depends on children's 'value')
        for node_id in self.nodes:
             self.nodes[node_id]["profit"] = self._calculate_profit(node_id)

        # 3. Suggested Children & Needed Children (Depend on threshold and children_count)
        for node_id in self.nodes:
             suggested = self._calculate_suggested_child_count(node_id) # Now just threshold
             self.nodes[node_id]["suggested_child_count"] = suggested
             needed = max(0, suggested - self.nodes[node_id]["children_count"])
             self.nodes[node_id]["needed_children"] = needed
             self.nodes[node_id]["is_chokepoint"] = needed > 0 # Chokepoint if children needed

        # 4. Criticality (Depends on needed_children and depth)
        for node_id in self.nodes:
            self.nodes[node_id]["criticality"] = self._calculate_criticality(node_id)

        # 5. Balance Score - REMOVED
        # for node_id in self.nodes:
        #      self.nodes[node_id]["balance_score"] = self._calculate_balance_score(node_id)
        print("Metrics update complete.")


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
            # Atomically replace the old file with the new one
            os.replace(temp_file_path, file_path)
            print(f"Network saved successfully to {file_path}")
        except Exception as e:
            print(f"Error saving network to {file_path}: {e}")
            if os.path.exists(temp_file_path):
                try: os.remove(temp_file_path)
                except OSError as rm_err: print(f"Error removing temp save file {temp_file_path}: {rm_err}")
            # Optional: Restore from backup on save failure
            # if backup_path and os.path.exists(backup_path): try: shutil.copy2(backup_path, file_path); print("Restored from backup.") except Exception as r_e: print(f"FATAL: Save failed & Restore failed: {r_e}")
            raise # Re-raise the exception after cleanup attempt

    @classmethod
    def load(cls, filename: str = "network.json") -> 'BusinessNetwork':
        """Load network state from JSON, applying defaults for missing fields."""
        script_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(script_dir)
        data_dir = os.path.join(project_root, "data")
        file_path = os.path.join(data_dir, filename)

        if not os.path.exists(file_path):
            print(f"Network file not found at {file_path}. Creating new network.")
            return cls() # Return a new instance with default settings

        try:
            with open(file_path, 'r') as f: data = json.load(f)
            settings = data.get("settings", {})
            # Initialize with loaded settings, providing defaults if missing
            network = cls(
                min_children_threshold=settings.get("min_children_threshold", 2)
                # balance_factor removed
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
                # node_data.setdefault("balance_score", 1.0) # Removed

                # Remove obsolete fields if present from older files
                node_data.pop("risk", None)
                node_data.pop("ponzi_value", None)
                node_data.pop("balance_score", None)

                network.nodes[node_id] = node_data

            loaded_graph = data.get("graph", {})
            network.graph = defaultdict(list)
            for node_id, edges in loaded_graph.items():
                 if node_id in network.nodes: # Ensure node exists before adding edges
                     # Validate and format edges correctly (ensure they are tuples)
                     valid_edges = []
                     if isinstance(edges, list):
                         for edge in edges:
                              if isinstance(edge, (list, tuple)) and len(edge) >= 1:
                                  target_id = edge[0]
                                  if target_id in network.nodes: # Ensure target node also exists
                                       capacity = 1.0
                                       if len(edge) > 1:
                                            try: capacity = float(edge[1])
                                            except (ValueError, TypeError): pass # Keep default capacity if conversion fails
                                       valid_edges.append((str(target_id), capacity))
                                  # else: print(f"Warning: Edge target '{target_id}' not found for source '{node_id}' during load.")
                     network.graph[node_id] = valid_edges

            # Ensure all nodes have at least an empty list in the graph dict
            for node_id in network.nodes: network.graph.setdefault(node_id, [])

            network._update_metrics() # Recalculate all metrics based on loaded data/settings
            print(f"Network loaded and metrics recalculated from {file_path}")
            return network
        except json.JSONDecodeError as json_err:
             print(f"Error decoding JSON from {file_path}: {json_err}. Returning new network.")
             return cls() # Return new instance on file corruption
        except Exception as e:
            print(f"Error loading network from {file_path}: {e}. Returning new network.")
            print(traceback.format_exc())
            return cls() # Return new instance on other errors

    @classmethod
    def from_json(cls, json_data: Union[str, bytes]) -> 'BusinessNetwork':
        """Create network from JSON string/bytes (used for import), applying defaults."""
        try:
            data = json.loads(json_data)
            if not isinstance(data.get("nodes"), dict) or not isinstance(data.get("graph"), dict):
                 raise ValueError("Invalid JSON structure: Missing 'nodes' or 'graph'.")

            settings = data.get("settings", {})
            network = cls(
                min_children_threshold=settings.get("min_children_threshold", 2)
                # balance_factor removed
            )

            loaded_nodes = data.get("nodes", {})
            for node_id, node_data in loaded_nodes.items():
                if not isinstance(node_data, dict): continue # Skip invalid node entries
                # Set defaults for required/calculated fields
                node_data.setdefault("id", node_id)
                node_data.setdefault("parents", [])
                node_data.setdefault("value", cls.DEFAULT_NODE_VALUE) # Default value
                node_data.setdefault("depth", 0); node_data.setdefault("children_count", 0); node_data.setdefault("total_children", 0); node_data.setdefault("profit", 0.0)
                node_data.setdefault("is_chokepoint", False); node_data.setdefault("suggested_child_count", network.min_children_threshold); node_data.setdefault("needed_children", 0)
                node_data.setdefault("criticality", 0.0)
                # node_data.setdefault("balance_score", 1.0) # Removed

                 # Remove obsolete fields
                node_data.pop("risk", None)
                node_data.pop("ponzi_value", None)
                node_data.pop("balance_score", None)

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
                if node_id in network.nodes and isinstance(edges, list): # Ensure source exists
                    valid_edges = []
                    for edge in edges:
                         if isinstance(edge, (list, tuple)) and len(edge) >= 1:
                             target_id = str(edge[0])
                             if target_id in network.nodes: # Ensure target exists
                                 capacity = 1.0
                                 if len(edge) > 1:
                                     try: capacity = float(edge[1])
                                     except (ValueError, TypeError): pass
                                 valid_edges.append( (target_id, capacity) )
                    network.graph[node_id] = valid_edges

            # Ensure all nodes have graph entries
            for node_id in network.nodes: network.graph.setdefault(node_id, [])

            network._update_metrics() # Recalculate all metrics
            return network
        except json.JSONDecodeError as json_err:
             raise ValueError(f"Invalid JSON data provided: {json_err}") from json_err
        except ValueError as ve: raise ve # Re-raise validation errors
        except Exception as e:
            print(f"Error creating network from JSON data: {e}\n{traceback.format_exc()}")
            raise ValueError(f"Failed to create network from JSON: {e}") from e