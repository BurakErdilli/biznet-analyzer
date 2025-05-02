# --- START OF FILE logic.py ---

import os
from typing import Dict, Any, Optional
import traceback

try:
    from .network_model import BusinessNetwork
except ImportError:
    from network_model import BusinessNetwork

NETWORK_FILENAME = "network.json"
network: Optional[BusinessNetwork] = None

def initialize_network():
    global network
    try:
        network = BusinessNetwork.load(filename=NETWORK_FILENAME)
        print(f"Network loaded successfully using filename: {NETWORK_FILENAME}")
    except Exception as e:
        print(f"Error loading network: {e}. Initializing new network.")
        network = BusinessNetwork()
        try:
             network.save(filename=NETWORK_FILENAME)
             print(f"New network initialized and saved using filename: {NETWORK_FILENAME}")
        except Exception as save_e: print(f"FATAL: Could not save initial empty network: {save_e}")

initialize_network()

def _get_network_instance() -> BusinessNetwork:
    if network is None:
        print("Network not initialized. Attempting initialization again.")
        initialize_network()
        if network is None: raise RuntimeError("Failed to initialize the Business Network.")
    return network

# --- API Logic Functions ---

def get_network():
    """Return the current network data (nodes, graph, settings)."""
    current_network = _get_network_instance()
    return current_network.get_network_data()

def add_node(data: Dict[str, Any]):
    """Add a node. Handles optional 'id' and 'value'. 'value' defaults to 1000."""
    current_network = _get_network_instance()
    try:
        parent_id = data.get("parent_id")
        node_id = data.get("id") or None # Treat empty string as None
        properties = {}
        # Extract value, backend model handles default if not provided or invalid format error
        if "value" in data:
             properties["value"] = data["value"] # Pass it along, model validates/defaults

        new_id = current_network.add_node(parent_id=parent_id, node_id=node_id, **properties)
        current_network.save(filename=NETWORK_FILENAME)
        return {"status": "success", "id": new_id}
    except ValueError as ve:
         return {"error": str(ve)}
    except Exception as e:
        print(f"Unexpected error in add_node: {e}\n{traceback.format_exc()}")
        return {"error": f"An unexpected error occurred: {str(e)}"}

def remove_node(node_id: str):
    """Remove a leaf node."""
    current_network = _get_network_instance()
    try:
        success = current_network.remove_node(node_id)
        if success:
            current_network.save(filename=NETWORK_FILENAME)
            return {"status": "success"}
        else: # Should be unreachable due to exceptions in model
            return {"error": f"Node {node_id} not found or could not be removed"}
    except ValueError as ve: # Catches not found, has children etc.
        return {"error": str(ve)}
    except Exception as e:
        print(f"Unexpected error in remove_node: {e}\n{traceback.format_exc()}")
        return {"error": f"An unexpected error occurred: {str(e)}"}

def get_node_insight(node_id: str):
    """Get detailed insights: value, profit (sum children value), criticality (needs children)."""
    current_network = _get_network_instance()
    try:
        node = current_network.get_node(node_id)
        if not node: return {"error": f"Node {node_id} not found"}

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
            "balance_score": node.get("balance_score", 1.0),
            "parents": node.get("parents", []),
            "children": current_network.get_direct_children(node_id),
            # Add any other custom properties stored (excluding known/calculated ones)
            **{k: v for k, v in node.items() if k not in [
                "id", "value", "depth", "children_count", "total_children", "profit",
                "criticality", "is_chokepoint", "needed_children", "suggested_children",
                "balance_score", "parents", "children", "risk", "ponzi_value" # Also exclude old names
            ]}
        }
        return insight_data
    except Exception as e:
        print(f"Unexpected error in get_node_insight: {e}\n{traceback.format_exc()}")
        return {"error": f"An unexpected error occurred while fetching insights: {str(e)}"}

def get_suggestions(limit: int = 5):
    """Get nodes needing children, prioritized by criticality and depth."""
    current_network = _get_network_instance()
    try:
        limit = max(1, limit)
        suggestions = current_network.get_unbalanced_nodes(limit=limit)
        return {"suggestions": suggestions}
    except Exception as e:
        print(f"Unexpected error in get_suggestions: {e}\n{traceback.format_exc()}")
        return {"suggestions": []} # Graceful failure for UI

def update_settings(data: Dict[str, Any]):
    """Update network settings (min_children_threshold, balance_factor)."""
    current_network = _get_network_instance()
    updated = False
    errors = {}
    try:
        if "min_children_threshold" in data:
            try:
                threshold = int(data["min_children_threshold"])
                if threshold < 1: errors["min_children_threshold"] = "Must be at least 1"
                elif current_network.min_children_threshold != threshold:
                    current_network.min_children_threshold = threshold; updated = True
            except (ValueError, TypeError): errors["min_children_threshold"] = "Invalid integer"

        if "balance_factor" in data:
            try:
                balance = float(data["balance_factor"])
                if not (0 <= balance <= 1): errors["balance_factor"] = "Must be 0-1"
                elif current_network.balance_factor != balance:
                    current_network.balance_factor = balance; updated = True
            except (ValueError, TypeError): errors["balance_factor"] = "Invalid number"

        if errors:
             error_message = "; ".join([f"{k}: {v}" for k, v in errors.items()])
             return {"error": f"Invalid settings: {error_message}"}

        if updated:
            print("Settings updated. Recalculating metrics and saving...")
            current_network._update_metrics()
            current_network.save(filename=NETWORK_FILENAME)
            print("Network metrics updated and saved.")
        else: print("No settings changed.")

        return {"status": "success"}
    except Exception as e:
        print(f"Unexpected error in update_settings: {e}\n{traceback.format_exc()}")
        return {"error": f"An unexpected error occurred: {str(e)}"}

def reload_network_from_file(filepath: str):
    """Forces reload of the global network instance from the specified file."""
    global network
    try:
        network = BusinessNetwork.load(filename=os.path.basename(filepath))
        print(f"Network reloaded successfully from {filepath}")
        return True
    except Exception as e:
        print(f"Error reloading network from {filepath}: {e}")
        return False

# --- END OF FILE logic.py ---