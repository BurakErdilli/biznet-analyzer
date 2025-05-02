# --- START OF FILE network_model.py ---

from collections import defaultdict, deque
from typing import Dict, List, Tuple, Optional, Set, Any, Union
import uuid
import math
import os
import json
from datetime import datetime

class BusinessNetwork:
    """
    Represents the business network with nodes, edges, and calculated metrics.
    Handles internal logic for node manipulation, metric calculation, and persistence.
    """
    def __init__(self, min_children_threshold: int = 2, balance_factor: float = 0.75):
        self.graph: Dict[str, List[Tuple[str, float]]] = defaultdict(list) # Adjacency list: parent -> list of (child, capacity)
        self.nodes: Dict[str, Dict[str, Any]] = {} # Node ID -> Node data dictionary
        self.min_children_threshold: int = max(1, min_children_threshold) # Ensure at least 1
        self.balance_factor: float = max(0, min(1, balance_factor)) # Clamp between 0 and 1
        self.max_depth: int = 0
        # Note: next_id generation is handled within add_node now

    def add_node(self, parent_id: Optional[str] = None, node_id: Optional[str] = None, **kwargs) -> str:
        """
        Adds a new node to the network.

        Args:
            parent_id: The ID of the parent node. Required if the network is not empty.
            node_id: Optional preferred ID for the new node. If None or empty, an ID is generated.
                     If the preferred ID exists, a unique suffix is added.
            **kwargs: Additional properties to store with the node (e.g., value, risk).

        Returns:
            The final ID of the added node.

        Raises:
            ValueError: If parent_id is required but not provided or does not exist.
                        If the provided node_id is invalid (e.g., contains problematic characters - not implemented yet).
        """
        is_root_node = not self.nodes # True if the network is currently empty
        is_explicit_root = parent_id is None and not is_root_node # Trying to add another root to non-empty graph

        if is_explicit_root:
             raise ValueError("Cannot add multiple root nodes. Specify a 'parent_id'.")

        if parent_id is not None:
            if parent_id not in self.nodes:
                raise ValueError(f"Parent node '{parent_id}' does not exist")
        elif not is_root_node:
             # This condition is checked in logic.py, but double-check here for model integrity
             raise ValueError("Parent ID is required for non-root nodes in a non-empty network")


        # Determine the node ID
        if not node_id: # If node_id is None or ""
            if is_root_node:
                final_id = "root"
            else:
                # Generate child-based ID
                base_id = f"{parent_id}.{len(self.graph.get(parent_id, [])) + 1}"
                final_id = base_id
                counter = 1
                while final_id in self.nodes: # Ensure uniqueness if base_id collides
                    final_id = f"{base_id}_{counter}"
                    counter += 1
        else:
            # Use provided ID, ensuring uniqueness
            final_id = str(node_id) # Ensure it's a string
            if final_id in self.nodes:
                 base_id = final_id
                 counter = 1
                 while final_id in self.nodes:
                     final_id = f"{base_id}_{counter}"
                     counter += 1
                 print(f"Warning: Provided node ID '{node_id}' already exists. Using '{final_id}' instead.")

        # --- Add the node ---
        self.nodes[final_id] = {
            "id": final_id,
            "parents": [], # Initialize parents list
            **kwargs # Add any custom properties passed
        }
        self.graph[final_id] = [] # Initialize adjacency list for the new node

        # --- Connect to parent (if applicable) ---
        if parent_id is not None:
            capacity = 1.0 # Default capacity, could be customized via kwargs if needed
            self.graph[parent_id].append((final_id, capacity))
            self.nodes[final_id]["parents"].append(parent_id)

        # --- Update metrics and return ---
        self._update_metrics() # Recalculate metrics after adding
        return final_id

    def remove_node(self, node_id: str) -> bool:
        """
        Removes a leaf node (node with no children) from the network.

        Args:
            node_id: The ID of the node to remove.

        Returns:
            True if the node was successfully removed.

        Raises:
            ValueError: If the node has children or if the node_id does not exist.
        """
        if node_id not in self.nodes:
            raise ValueError(f"Node '{node_id}' not found")

        # Check if node has children using the graph structure
        if self.graph.get(node_id): # Check if the list exists and is non-empty
            raise ValueError("Cannot remove node with children. Remove children first.")

        # --- Remove connections from parent(s) ---
        parent_ids = self.nodes[node_id].get("parents", [])
        for parent_id in parent_ids:
            if parent_id in self.graph:
                # Filter out the edge pointing to the node being removed
                self.graph[parent_id] = [(child, cap) for child, cap in self.graph[parent_id] if child != node_id]

        # --- Remove the node itself ---
        del self.nodes[node_id]
        if node_id in self.graph: # Remove its (empty) entry from the graph keys
             del self.graph[node_id]


        # --- Update metrics ---
        # It's important to update metrics *after* removal
        self._update_metrics()
        return True


    def get_node(self, node_id: str) -> Optional[Dict[str, Any]]:
        """Get the data dictionary for a specific node."""
        return self.nodes.get(node_id)

    def get_direct_children(self, node_id: str) -> List[str]:
        """Get a list of IDs of the direct children of a node."""
        # Use graph structure for direct children
        return [child_id for child_id, _ in self.graph.get(node_id, [])]

    def get_all_descendants(self, node_id: str) -> Set[str]:
        """Get a set of IDs of all descendants (direct and indirect) using BFS."""
        if node_id not in self.graph:
            return set()

        descendants = set()
        queue = deque(self.get_direct_children(node_id)) # Start with direct children

        while queue:
            current_node_id = queue.popleft()
            if current_node_id not in descendants:
                descendants.add(current_node_id)
                # Add children of the current node to the queue
                for child_id in self.get_direct_children(current_node_id):
                    if child_id not in descendants: # Avoid cycles in queue if graph has them (shouldn't in tree)
                        queue.append(child_id)
        return descendants

    def get_network_data(self) -> Dict[str, Any]:
        """Get all network data suitable for serialization (e.g., to JSON)."""
        # Ensure settings reflect the current state
        settings = {
            "min_children_threshold": self.min_children_threshold,
            "balance_factor": self.balance_factor,
            "max_depth": self.max_depth # Include max_depth calculated by _update_metrics
        }

        # Convert graph defaultdict to a regular dict for JSON serialization
        serializable_graph = {node_id: edges for node_id, edges in self.graph.items()}

        return {
            "nodes": self.nodes,
            "graph": serializable_graph,
            "settings": settings
        }

    # --- Metric Calculation Methods ---

    def _calculate_depth(self, node_id: str, visited: Set[str]) -> int:
        """Helper for depth calculation with cycle detection."""
        if node_id not in self.nodes or node_id in visited:
            return 0 # Base case or cycle detected

        visited.add(node_id)
        parents = self.nodes[node_id].get("parents", [])

        if not parents:
             visited.remove(node_id)
             return 0 # Root node

        max_parent_depth = 0
        for parent_id in parents:
             # Check if parent exists before recursing
             if parent_id in self.nodes:
                  max_parent_depth = max(max_parent_depth, self._calculate_depth(parent_id, visited))
             else:
                  # Handle case where parent listed doesn't exist (data integrity issue)
                  print(f"Warning: Node '{node_id}' lists non-existent parent '{parent_id}'. Skipping for depth calc.")


        depth = max_parent_depth + 1
        visited.remove(node_id) # Remove after returning from this path
        return depth


    def _calculate_total_children(self, node_id: str) -> int:
        """Calculate the total number of descendants (direct and indirect)."""
        # Reuses the efficient BFS implementation
        return len(self.get_all_descendants(node_id))

    def _calculate_profit(self, node_id: str) -> float:
        """Calculate profit based on 'Ponzi scheme' position."""
        node = self.nodes.get(node_id)
        if not node: return 0.0

        depth = node.get("depth", 0)
        total_children = node.get("total_children", 0)
        children_count = node.get("children_count", 0)

        # Base profit: More descendants = more profit
        base_profit = 100 * total_children

        # Bonus for direct recruitment
        direct_bonus = 50 * children_count

        # Early adopter bonus (higher for lower depth)
        early_adopter_bonus = 1000 * math.exp(-0.5 * depth) # Adjusted decay rate

        # 'Ponzi' factor - value decreases deeper in hierarchy
        ponzi_discount = max(0.05, 1.0 - (0.1 * depth)) # Ensure minimum factor

        profit = (base_profit + direct_bonus + early_adopter_bonus) * ponzi_discount
        return round(max(0, profit), 2) # Round for cleaner display

    def _calculate_risk(self, node_id: str) -> float:
        """Calculate risk based on 'Ponzi scheme' position."""
        node = self.nodes.get(node_id)
        if not node: return 0.0

        depth = node.get("depth", 0)
        total_children = node.get("total_children", 0)

        # Base risk increases with depth
        base_risk = 0.1 + (0.06 * depth) # Adjusted base and increment

        # Risk decreases with more descendants (more stable downline)
        # Using tanh for a smoother S-curve effect, stabilizing risk reduction
        children_factor = 1 - 0.8 * math.tanh(total_children / 10.0) # Max 80% reduction

        risk = base_risk * children_factor
        return round(min(0.99, max(0.01, risk)), 3) # Clamp and round


    def _calculate_ponzi_value(self, node_id: str) -> float:
        """Calculate the 'Ponzi network value' for a node."""
        node = self.nodes.get(node_id)
        if not node: return 0.0

        depth = node.get("depth", 0)
        total_children = node.get("total_children", 0)

        # Value decreases with depth
        depth_factor = max(0.1, 1.0 - (0.1 * depth))

        # Value increases with number of recruits (log scale for diminishing returns)
        recruitment_factor = math.log1p(total_children) * 0.1 # log1p(x) = log(1+x)

        ponzi_value = depth_factor + recruitment_factor
        return round(min(1.0, max(0.1, ponzi_value)), 3) # Clamp and round

    def _calculate_criticality(self, node_id: str) -> float:
        """Calculate the criticality of a node (higher if it bridges few children to many descendants)."""
        node = self.nodes.get(node_id)
        if not node: return 0.0

        total_children = node.get("total_children", 0)
        children_count = node.get("children_count", 0)

        if children_count == 0:
            return 0.0 # Leaf nodes are not critical chokepoints in this context

        # Ratio of total descendants funneled through direct children
        # Add 1 to total_children to account for the node itself if desired,
        # but for branching factor, just descendants seems better.
        branching_factor = total_children / children_count

        # Normalize using tanh for smooth scaling, capping around 1.0
        # Adjust the divisor (e.g., 10.0) to control sensitivity
        criticality = math.tanh(branching_factor / 10.0)

        return round(min(1.0, max(0.0, criticality)), 3)

    def _calculate_suggested_child_count(self, node_id: str) -> int:
        """Calculate the suggested number of children based on depth and threshold."""
        node = self.nodes.get(node_id)
        if not node: return self.min_children_threshold

        depth = node.get("depth", 0)

        # Tiered suggestion based on depth
        if depth == 0:
            return max(3, self.min_children_threshold + 1) # Root needs more
        elif depth <= 2:
            return max(2, self.min_children_threshold) # Early levels
        else:
            return self.min_children_threshold # Deeper levels baseline

    def _calculate_balance_score(self, node_id: str) -> float:
        """Calculate a balance score (0-1) for the node's immediate sub-tree."""
        node = self.nodes.get(node_id)
        if not node: return 1.0 # Default to balanced if node doesn't exist

        children_ids = self.get_direct_children(node_id)
        children_count = len(children_ids)
        suggested_count = node.get("suggested_child_count", self.min_children_threshold)

        # Factor 1: Meeting the suggested count threshold
        if children_count == 0:
             # Score depends on whether children are suggested
             threshold_score = 1.0 if suggested_count == 0 else 0.2 # Penalize heavily if children needed
        elif children_count < suggested_count:
             threshold_score = 0.3 + 0.7 * (children_count / suggested_count) # Score between 0.3 and 1.0
        else:
             threshold_score = 1.0 # Meets or exceeds threshold

        # Factor 2: Even distribution of descendants among children (if more than 1 child)
        distribution_score = 1.0
        if children_count > 1:
            child_descendant_counts = []
            for child_id in children_ids:
                 child_node = self.nodes.get(child_id)
                 # Include the child node itself in its subtree size (+1)
                 count = (child_node.get("total_children", 0) + 1) if child_node else 1
                 child_descendant_counts.append(count)

            if sum(child_descendant_counts) > 0: # Avoid division by zero if all children have 0 descendants
                 mean_descendants = sum(child_descendant_counts) / children_count
                 # Sum of squared differences from the mean
                 variance = sum((count - mean_descendants) ** 2 for count in child_descendant_counts) / children_count
                 std_dev = math.sqrt(variance)
                 # Coefficient of Variation (CV) - lower is better
                 cv = std_dev / mean_descendants if mean_descendants > 0 else 0
                 # Convert CV to score (0-1), using balance_factor to tune sensitivity
                 # Lower CV -> higher score
                 distribution_score = max(0, 1.0 - (cv * self.balance_factor))
            # else: all children are leaf nodes -> perfectly balanced distribution

        # Combine scores (e.g., weighted average or minimum)
        # Using minimum emphasizes that both conditions should be met
        final_score = min(threshold_score, distribution_score)
        # Or a weighted average:
        # final_score = 0.6 * threshold_score + 0.4 * distribution_score

        return round(final_score, 3)

    def get_unbalanced_nodes(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Get nodes needing more children, prioritized by imbalance and depth."""
        candidates = []
        for node_id, node_data in self.nodes.items():
             # Ensure all necessary metrics are calculated and present
             balance_score = node_data.get("balance_score", 1.0)
             children_count = node_data.get("children_count", 0)
             suggested_count = node_data.get("suggested_child_count", self.min_children_threshold)
             needed_children = max(0, suggested_count - children_count)

             # Only consider nodes that actually need children
             if needed_children > 0:
                 depth = node_data.get("depth", 0)
                 # Priority: Higher for lower balance, higher for lower depth
                 depth_weight = max(0.1, 1.0 - (depth * 0.05)) # Less penalty for depth
                 priority = (1.0 - balance_score) * depth_weight * needed_children # Factor in how many are needed

                 candidates.append({
                     "id": node_id,
                     "balance_score": balance_score,
                     "current_children": children_count,
                     "suggested_children": suggested_count,
                     "needed_children": needed_children,
                     "depth": depth,
                     "priority": round(priority, 4),
                     "profit": node_data.get("profit", 0) # Include profit for context
                 })

        # Sort by priority (descending)
        candidates.sort(key=lambda x: x["priority"], reverse=True)
        return candidates[:limit]


    def _update_metrics(self) -> None:
        """Update all calculated metrics for all nodes in the network."""
        print("Updating network metrics...")
        # Reset max depth
        self.max_depth = 0

        # Topological Sort (BFS from roots) to calculate depths correctly in DAGs
        nodes_to_process = deque()
        in_degree = {node_id: 0 for node_id in self.nodes}
        processed_nodes = set()
        node_depths = {}

        # Calculate initial in-degrees and find roots
        for node_id in self.nodes:
            parents = self.nodes[node_id].get("parents", [])
            in_degree[node_id] = len(parents)
            if in_degree[node_id] == 0:
                nodes_to_process.append(node_id)
                node_depths[node_id] = 0 # Roots have depth 0

        # Process nodes topologically
        while nodes_to_process:
            node_id = nodes_to_process.popleft()
            processed_nodes.add(node_id)
            current_depth = node_depths.get(node_id, 0)

            # Update node's depth in the main dictionary
            self.nodes[node_id]["depth"] = current_depth
            self.max_depth = max(self.max_depth, current_depth)

            # Process children
            for child_id in self.get_direct_children(node_id):
                if child_id in in_degree:
                    in_degree[child_id] -= 1
                    # Calculate child depth based on max parent depth seen so far
                    node_depths[child_id] = max(node_depths.get(child_id, 0), current_depth + 1)
                    if in_degree[child_id] == 0:
                        nodes_to_process.append(child_id)

        # Check for cycles if not all nodes were processed
        if len(processed_nodes) != len(self.nodes):
             print(f"Warning: Cycle detected or orphaned nodes found. Processed {len(processed_nodes)}/{len(self.nodes)} nodes.")
             # Handle nodes potentially missed by topological sort (assign default depth?)
             for node_id in self.nodes:
                  if node_id not in processed_nodes:
                       self.nodes[node_id]["depth"] = self.nodes[node_id].get("depth", 999) # Assign high depth or handle differently
                       print(f"Assigning default depth to unprocessed node: {node_id}")


        # --- Calculate other metrics based on depth ---
        # Order matters: counts -> values -> balance/chokepoints

        # Calculate direct children count
        for node_id in self.nodes:
             self.nodes[node_id]["children_count"] = len(self.get_direct_children(node_id))

        # Calculate total descendants (can be done in any order after graph is stable)
        # This can be slow for large graphs, consider optimizing if needed
        for node_id in self.nodes:
             self.nodes[node_id]["total_children"] = self._calculate_total_children(node_id)

        # Calculate value, risk, profit (depend on counts and depth)
        for node_id in self.nodes:
            self.nodes[node_id]["ponzi_value"] = self._calculate_ponzi_value(node_id)
            self.nodes[node_id]["risk"] = self._calculate_risk(node_id)
            self.nodes[node_id]["profit"] = self._calculate_profit(node_id)

        # Calculate suggested children (depends on depth and threshold setting)
        for node_id in self.nodes:
             self.nodes[node_id]["suggested_child_count"] = self._calculate_suggested_child_count(node_id)

        # Determine chokepoints and calculate criticality (depend on counts and suggestions)
        for node_id in self.nodes:
             is_chokepoint = self.nodes[node_id]["children_count"] < self.nodes[node_id]["suggested_child_count"]
             self.nodes[node_id]["is_chokepoint"] = is_chokepoint
             self.nodes[node_id]["criticality"] = self._calculate_criticality(node_id) if is_chokepoint else 0.0

        # Calculate balance scores (depend on counts, suggestions, and descendant counts)
        for node_id in self.nodes:
             self.nodes[node_id]["balance_score"] = self._calculate_balance_score(node_id)

        print("Metrics update complete.")


    # --- Persistence Methods ---

    def save(self, filename: str = "network.json") -> None:
        """Save the network state to a JSON file in the 'data' directory."""
        # Determine data directory relative to this script file
        script_dir = os.path.dirname(os.path.abspath(__file__))
        data_dir = os.path.join(os.path.dirname(script_dir), "data") # Assumes app/ is sibling to data/
        os.makedirs(data_dir, exist_ok=True)
        file_path = os.path.join(data_dir, filename)
        backup_path = None # Initialize backup path

        # Create backup
        if os.path.exists(file_path):
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f") # Added microseconds for higher resolution
            backup_filename = f"{os.path.splitext(filename)[0]}_backup_{timestamp}.json"
            backup_path = os.path.join(data_dir, backup_filename)
            try:
                shutil.copy2(file_path, backup_path) # copy2 preserves metadata
                # print(f"Created backup: {backup_filename}")
            except Exception as e:
                print(f"Error creating backup for {filename}: {e}")
                backup_path = None # Ensure backup_path is None if backup failed

        # Save current network using a temporary file for atomicity
        temp_file_path = file_path + ".tmp"
        try:
            network_data = self.get_network_data()
            with open(temp_file_path, 'w') as f:
                json.dump(network_data, f, indent=2)
            # Rename temporary file to the actual file path atomically (on most OS)
            os.replace(temp_file_path, file_path)
            # print(f"Network saved successfully to {file_path}")
        except Exception as e:
            print(f"Error saving network to {file_path}: {e}")
            # Clean up temporary file if saving failed
            if os.path.exists(temp_file_path):
                try:
                    os.remove(temp_file_path)
                except OSError as rm_err:
                     print(f"Error removing temporary save file {temp_file_path}: {rm_err}")
            # Optional: Restore from backup if save failed? Requires careful consideration.
            # if backup_path and os.path.exists(backup_path):
            #     try:
            #         shutil.copy2(backup_path, file_path)
            #         print(f"Restored network from backup {backup_path} due to save error.")
            #     except Exception as restore_e:
            #          print(f"FATAL: Failed to save network and failed to restore backup: {restore_e}")
            raise # Re-raise the original save error

    @classmethod
    def load(cls, filename: str = "network.json") -> 'BusinessNetwork':
        """Load the network state from a JSON file in the 'data' directory."""
        script_dir = os.path.dirname(os.path.abspath(__file__))
        data_dir = os.path.join(os.path.dirname(script_dir), "data")
        file_path = os.path.join(data_dir, filename)

        if not os.path.exists(file_path):
            print(f"Network file not found at {file_path}. Creating a new network instance.")
            # Return a new empty network if file doesn't exist
            return cls()

        try:
            with open(file_path, 'r') as f:
                data = json.load(f)

            # --- Instantiate and Populate ---
            settings = data.get("settings", {})
            min_children_threshold = settings.get("min_children_threshold", 2)
            balance_factor = settings.get("balance_factor", 0.75)

            # Create instance with loaded settings
            network = cls(min_children_threshold=min_children_threshold, balance_factor=balance_factor)

            # Load nodes
            network.nodes = data.get("nodes", {})

            # Load graph, converting lists back to tuples if necessary (JSON saves lists)
            # And ensuring defaultdict behavior is restored if needed, though direct assignment works too.
            loaded_graph = data.get("graph", {})
            network.graph = defaultdict(list, {
                 node_id: [tuple(edge) if isinstance(edge, list) else edge for edge in edges]
                 for node_id, edges in loaded_graph.items()
             })


            # It's crucial to recalculate metrics after loading, as saved metrics might be stale
            # or inconsistent with loaded settings/structure.
            network._update_metrics()
            print(f"Network loaded and metrics recalculated from {file_path}")
            return network
        except json.JSONDecodeError as json_err:
             print(f"Error decoding JSON from {file_path}: {json_err}. Returning new network.")
             return cls() # Return empty network on JSON error
        except Exception as e:
            print(f"Error loading network from {file_path}: {e}. Returning new network.")
            print(traceback.format_exc()) # Log detailed error
            # Consider attempting to load the latest backup here as a fallback
            return cls() # Return empty network on other errors

    @classmethod
    def from_json(cls, json_data: Union[str, bytes]) -> 'BusinessNetwork':
        """Create a network instance from a JSON string or bytes."""
        try:
            data = json.loads(json_data)

            settings = data.get("settings", {})
            min_children_threshold = settings.get("min_children_threshold", 2)
            balance_factor = settings.get("balance_factor", 0.75)

            network = cls(min_children_threshold=min_children_threshold, balance_factor=balance_factor)
            network.nodes = data.get("nodes", {})

            loaded_graph = data.get("graph", {})
            network.graph = defaultdict(list, {
                 node_id: [tuple(edge) if isinstance(edge, list) else edge for edge in edges]
                 for node_id, edges in loaded_graph.items()
             })

            network._update_metrics() # Recalculate metrics
            return network
        except json.JSONDecodeError as json_err:
             print(f"Error decoding JSON data: {json_err}")
             raise ValueError(f"Invalid JSON data provided: {json_err}") from json_err
        except Exception as e:
            print(f"Error creating network from JSON data: {e}")
            raise ValueError(f"Failed to create network from JSON: {e}") from e

# --- END OF FILE network_model.py ---