
import os
from typing import Dict, Any, Optional, List
import traceback

try:
    from .network_model import BusinessNetwork
except ImportError:
    from network_model import BusinessNetwork

NETWORK_FILENAME = "network.json"
network: Optional[BusinessNetwork] = None

def initialize_network():
    """Loads the network from file or creates a new one if not found or invalid."""
    global network
    try:
        network = BusinessNetwork.load(filename=NETWORK_FILENAME)
        print(f"Network loaded successfully using filename: {NETWORK_FILENAME}")
    except Exception as e:
        print(f"Error loading network from {NETWORK_FILENAME}: {e}. Initializing new network.")
        network = BusinessNetwork() # Initialize with default settings
        try:
             # Attempt to save the newly initialized network immediately
             network.save(filename=NETWORK_FILENAME)
             print(f"New network initialized and saved using filename: {NETWORK_FILENAME}")
        except Exception as save_e:
             # Log a critical error if saving the initial network fails
             print(f"FATAL: Could not save initial empty network {NETWORK_FILENAME}: {save_e}")
             print(traceback.format_exc())
             # Depending on requirements, might want to prevent app start here
             # For now, we allow starting with an in-memory network only

def _get_network_instance() -> BusinessNetwork:
    """Ensures the network instance is available, initializing if necessary."""
    if network is None:
        print("Network not initialized. Attempting initialization again.")
        initialize_network()
        # If initialization still fails (e.g., file system issues), raise an error
        if network is None:
             raise RuntimeError("FATAL: Failed to initialize the Business Network.")
    return network

# Initialize on module load
initialize_network()

# --- API Logic Functions ---

def get_network():
    """Return the current network data (nodes, graph, settings)."""
    current_network = _get_network_instance()
    return current_network.get_network_data()

def get_global_stats() -> Dict[str, Any]:
    """Calculate and return global statistics about the network."""
    current_network = _get_network_instance()
    nodes = current_network.nodes
    total_nodes = len(nodes)
    total_edges = sum(len(edges) for edges in current_network.graph.values())
    max_depth = current_network.max_depth
    total_value = sum(node.get('value', 0) for node in nodes.values())
    total_profit = sum(node.get('profit', 0) for node in nodes.values())

    return {
        "total_nodes": total_nodes,
        "total_edges": total_edges,
        "max_depth": max_depth,
        "total_value": round(total_value, 2),
        "total_profit": round(total_profit, 2)
    }


def add_node(data: Dict[str, Any]):
    """Add a node. Handles optional 'id' and 'value'. 'value' defaults."""
    current_network = _get_network_instance()
    try:
        parent_id = data.get("parent_id")
        node_id = data.get("id") or None # Treat empty string as None for auto-generation
        properties = {}
        # Extract value, backend model handles default if not provided or invalid format error
        if "value" in data and data["value"] is not None and data["value"] != '':
             properties["value"] = data["value"] # Pass it along, model validates/defaults

        new_id = current_network.add_node(parent_id=parent_id, node_id=node_id, **properties)
        current_network.save(filename=NETWORK_FILENAME)
        return {"status": "success", "id": new_id}
    except ValueError as ve:
         # User-related errors (invalid parent, duplicate ID type issues)
         return {"error": str(ve)}
    except Exception as e:
        # Unexpected errors during node addition or saving
        print(f"Unexpected error in add_node: {e}\n{traceback.format_exc()}")
        return {"error": f"An unexpected server error occurred while adding the node."}


def remove_node(node_id: str):
    """Remove a leaf node."""
    current_network = _get_network_instance()
    try:
        success = current_network.remove_node(node_id)
        if success:
            current_network.save(filename=NETWORK_FILENAME)
            return {"status": "success"}
        else: # Should be unreachable due to exceptions in model
            return {"error": f"Node '{node_id}' could not be removed (unexpected)."}
    except ValueError as ve: # Catches not found, has children etc.
        return {"error": str(ve)}
    except Exception as e:
        print(f"Unexpected error in remove_node for '{node_id}': {e}\n{traceback.format_exc()}")
        return {"error": f"An unexpected server error occurred while removing the node."}

# --- NEW: Bulk Remove Nodes ---
def bulk_remove_nodes(node_ids: List[str]):
    """Remove multiple leaf nodes."""
    current_network = _get_network_instance()
    deleted_count = 0
    failed_nodes = {} # Store errors per node ID

    if not node_ids:
        return {"error": "No node IDs provided for deletion."}

    # Check upfront if all nodes are leaves and exist
    valid_to_delete = True
    for node_id in node_ids:
        node = current_network.get_node(node_id)
        if not node:
            failed_nodes[node_id] = "Node not found"
            valid_to_delete = False
            continue
        if current_network.graph.get(node_id): # Check if it has children
            failed_nodes[node_id] = "Node has children"
            valid_to_delete = False
            continue

    if not valid_to_delete:
        error_msg = "Cannot perform bulk delete: " + "; ".join([f"{nid}: {reason}" for nid, reason in failed_nodes.items()])
        return {"error": error_msg, "deleted_count": 0, "failed_nodes": failed_nodes}

    # Proceed with deletion if all checks passed
    try:
        for node_id in node_ids:
            try:
                # We already validated, but model's remove_node does final checks
                current_network.remove_node(node_id)
                deleted_count += 1
            except ValueError as ve_inner:
                 # Should ideally not happen due to pre-check, but catch just in case
                 failed_nodes[node_id] = str(ve_inner)
                 print(f"Error deleting node '{node_id}' during bulk operation (post-check): {ve_inner}")
            except Exception as e_inner:
                 failed_nodes[node_id] = "Unexpected server error during deletion"
                 print(f"Unexpected error deleting node '{node_id}' during bulk operation: {e_inner}\n{traceback.format_exc()}")

        # Save only if at least one node was successfully deleted (or attempted)
        if deleted_count > 0 or failed_nodes: # Save even if some failed to persist successful deletions
             current_network.save(filename=NETWORK_FILENAME)

        if not failed_nodes:
            return {"status": "success", "deleted_count": deleted_count, "failed_nodes": {}}
        else:
            error_summary = f"Completed with errors. Deleted: {deleted_count}. Failed: {len(failed_nodes)}."
            # Return 207 Multi-Status might be more appropriate here, but for simplicity use 400 with details
            return {"error": error_summary, "deleted_count": deleted_count, "failed_nodes": failed_nodes}

    except Exception as e:
        print(f"Unexpected error during bulk_remove_nodes: {e}\n{traceback.format_exc()}")
        # Attempt to save any potentially successful changes before the error
        try: current_network.save(filename=NETWORK_FILENAME)
        except Exception as save_e: print(f"Failed to save network after bulk delete error: {save_e}")
        return {"error": "An unexpected server error occurred during the bulk delete operation.", "deleted_count": deleted_count, "failed_nodes": failed_nodes}


def add_subtree(parent_id: str, subtree_data: Dict[str, Any]):
    """Adds a subtree structure under the given parent node."""
    current_network = _get_network_instance()
    try:
        added_ids = current_network.add_subtree_from_data(parent_id, subtree_data)
        current_network.save(filename=NETWORK_FILENAME)
        return {"status": "success", "added_nodes": added_ids}
    except ValueError as ve:
        # Specific errors from the model (parent not found, invalid structure)
        return {"error": str(ve)}
    except Exception as e:
        # Unexpected errors during subtree addition or saving
        print(f"Unexpected error in add_subtree for parent '{parent_id}': {e}\n{traceback.format_exc()}")
        return {"error": f"An unexpected server error occurred while adding the subtree."}


def get_node_insight(node_id: str):
    """Get detailed insights: value, profit, criticality, etc."""
    current_network = _get_network_instance()
    try:
        node = current_network.get_node(node_id)
        if not node: return {"error": f"Node '{node_id}' not found"}

        # Extract data, relying on defaults set in the node object by _update_metrics
        insight_data = {
            "id": node_id,
            "value": node.get("value", BusinessNetwork.DEFAULT_NODE_VALUE),
            "depth": node.get("depth", -1),
            "children_count": node.get("children_count", 0),
            "total_children": node.get("total_children", 0),
            "profit": node.get("profit", 0.0), # Calculated profit
            "criticality": node.get("criticality", 0.0), # 0 if OK, >0 if needs children
            "is_chokepoint": node.get("is_chokepoint", False), # Still useful flag
            "needed_children": node.get("needed_children", 0),
            "suggested_children": node.get("suggested_child_count", current_network.min_children_threshold),
            # "balance_score": node.get("balance_score", 1.0), # Removed
            "parents": node.get("parents", []),
            "children": current_network.get_direct_children(node_id),
            # Add any other custom properties stored (excluding known/calculated ones)
            **{k: v for k, v in node.items() if k not in [
                "id", "value", "depth", "children_count", "total_children", "profit",
                "criticality", "is_chokepoint", "needed_children", "suggested_children",
                "parents", "children",
                # Also exclude obsolete/internal keys
                "balance_score", "risk", "ponzi_value", "_current_depth_calculation"
            ]}
        }
        return insight_data
    except Exception as e:
        print(f"Unexpected error in get_node_insight for '{node_id}': {e}\n{traceback.format_exc()}")
        return {"error": f"An unexpected error occurred while fetching insights."}

def get_suggestions(limit: int = 5):
    """Get nodes needing children, prioritized by criticality and depth."""
    current_network = _get_network_instance()
    try:
        limit = max(1, limit) # Ensure limit is at least 1
        suggestions = current_network.get_unbalanced_nodes(limit=limit)
        return {"suggestions": suggestions}
    except Exception as e:
        # Graceful failure: log error, return empty list for UI
        print(f"Unexpected error in get_suggestions: {e}\n{traceback.format_exc()}")
        return {"suggestions": []}

def update_settings(data: Dict[str, Any]):
    """Update network settings (currently only min_children_threshold)."""
    current_network = _get_network_instance()
    updated = False
    errors = {}
    try:
        if "min_children_threshold" in data:
            try:
                threshold = int(data["min_children_threshold"])
                if threshold < 1: errors["min_children_threshold"] = "Must be at least 1"
                elif current_network.min_children_threshold != threshold:
                    current_network.min_children_threshold = threshold
                    updated = True
            except (ValueError, TypeError): errors["min_children_threshold"] = "Must be a valid integer"

        # Balance factor removed
        # if "balance_factor" in data:
        #     try:
        #         balance = float(data["balance_factor"])
        #         if not (0 <= balance <= 1): errors["balance_factor"] = "Must be 0-1"
        #         elif current_network.balance_factor != balance:
        #             current_network.balance_factor = balance; updated = True
        #     except (ValueError, TypeError): errors["balance_factor"] = "Invalid number"

        if errors:
             error_message = "; ".join([f"{k}: {v}" for k, v in errors.items()])
             return {"error": f"Invalid settings: {error_message}"}

        if updated:
            print("Settings updated. Recalculating metrics and saving...")
            current_network._update_metrics()
            current_network.save(filename=NETWORK_FILENAME)
            print("Network metrics updated and saved.")
        else:
             print("No settings changed.")

        return {"status": "success"}
    except Exception as e:
        print(f"Unexpected error in update_settings: {e}\n{traceback.format_exc()}")
        return {"error": f"An unexpected server error occurred while updating settings."}


def reload_network_from_file(filepath: str):
    """Forces reload of the global network instance from the specified file."""
    global network
    try:
        # Use the filename part to load relative to the data directory
        network = BusinessNetwork.load(filename=os.path.basename(filepath))
        print(f"Network reloaded successfully from {filepath}")
        return True
    except Exception as e:
        print(f"Error reloading network from {filepath}: {e}")
        # Attempt to re-initialize to prevent None state
        initialize_network()
        return False