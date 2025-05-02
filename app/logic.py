# --- START OF FILE logic.py ---

# app/logic.py

import os
from typing import Dict, Any, Optional
import traceback # Keep for potential future detailed logging

from .network_model import BusinessNetwork
# Removed unused storage imports as BusinessNetwork handles its own persistence

# Get data directory path relative to this file's location
# Assuming structure: project_root/app/logic.py and project_root/data/
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
data_dir = os.path.join(project_root, "data")
os.makedirs(data_dir, exist_ok=True)

# Define the standard filename
NETWORK_FILENAME = "network.json"

# Initialize the business network by loading from the standard file
try:
    network = BusinessNetwork.load(filename=NETWORK_FILENAME)
    print(f"Network loaded successfully from {os.path.join(data_dir, NETWORK_FILENAME)}")
except Exception as e:
    print(f"Error loading network: {e}. Initializing new network.")
    network = BusinessNetwork()
    network.save(filename=NETWORK_FILENAME) # Save the initial empty state

def get_network():
    """Return the current network data."""
    return network.get_network_data()

def add_node(data: Dict[str, Any]):
    """Add a new node to the network."""
    global network
    try:
        # Extract required parameters
        parent_id = data.get("parent_id")
        node_id = data.get("id") # Optional, can be None or empty string

        # Handle empty string for optional node_id
        if node_id == "":
            node_id = None

        # Validate parent_id: required if the network is not empty
        if not parent_id and len(network.nodes) > 0:
            return {"error": "Parent ID is required for non-root nodes"}

        # Add additional properties if provided (optional)
        properties = {}
        if "value" in data:
            try:
                properties["value"] = float(data["value"])
            except (ValueError, TypeError):
                 return {"error": "Invalid format for 'value' property"}
        if "risk" in data:
            try:
                properties["risk"] = float(data["risk"])
            except (ValueError, TypeError):
                 return {"error": "Invalid format for 'risk' property"}

        # Add the node using the network instance
        new_id = network.add_node(parent_id=parent_id, node_id=node_id, **properties)

        # Save network changes to the standard file
        network.save(filename=NETWORK_FILENAME)

        return {"status": "success", "id": new_id}
    except ValueError as ve: # Catch specific validation errors from model
         return {"error": str(ve)}
    except Exception as e:
        # Log unexpected errors for debugging
        print(f"Unexpected error in add_node: {e}\n{traceback.format_exc()}")
        return {"error": f"An unexpected error occurred: {str(e)}"}

def remove_node(node_id: str):
    """Remove a node from the network."""
    global network
    try:
        success = network.remove_node(node_id)
        if success:
            network.save(filename=NETWORK_FILENAME)
            return {"status": "success"}
        else:
            # This case might not be reachable if remove_node raises error on not found
            return {"error": f"Node {node_id} not found or could not be removed"}
    except ValueError as ve: # Specific error for nodes with children
        return {"error": str(ve)}
    except Exception as e:
        print(f"Unexpected error in remove_node: {e}\n{traceback.format_exc()}")
        return {"error": f"An unexpected error occurred: {str(e)}"}

def get_node_insight(node_id: str):
    """Get detailed insights about a specific node."""
    global network
    try:
        node = network.get_node(node_id)
        if not node:
            return {"error": f"Node {node_id} not found"}

        # Ensure metrics are present, default if not (though _update_metrics should handle this)
        depth = node.get("depth", 0)
        children_count = node.get("children_count", 0)
        is_chokepoint = node.get("is_chokepoint", False)
        suggested_count = node.get("suggested_child_count", network.min_children_threshold)
        needed_children = max(0, suggested_count - children_count)

        # Get direct children IDs
        direct_children = network.get_direct_children(node_id)

        # Assemble the insight dictionary
        insight_data = {
            "id": node_id,
            "depth": depth,
            "children_count": children_count,
            "total_children": node.get("total_children", 0), # Add total descendants
            "is_chokepoint": is_chokepoint,
            "needed_children": needed_children,
            "suggested_children": suggested_count,
            "balance_score": node.get("balance_score", 1.0),
            "risk": node.get("risk", 0.0),
            "profit": node.get("profit", 0.0),
            "ponzi_value": node.get("ponzi_value", 0.0),
            "criticality": node.get("criticality", 0.0),
            "parents": node.get("parents", []), # Include parents if available
            "children": direct_children, # Direct children IDs
            # Add any other custom properties stored in the node
            **{k: v for k, v in node.items() if k not in [
                "id", "depth", "children_count", "total_children", "is_chokepoint",
                "needed_children", "suggested_child_count", "balance_score",
                "risk", "profit", "ponzi_value", "criticality", "parents", "children"
            ]}
        }

        return insight_data
    except Exception as e:
        print(f"Unexpected error in get_node_insight: {e}\n{traceback.format_exc()}")
        return {"error": f"An unexpected error occurred while fetching insights: {str(e)}"}

def get_suggestions(limit: int = 5):
    """Get nodes that would benefit from adding children."""
    global network
    try:
        # Ensure limit is positive
        limit = max(1, limit)
        suggestions = network.get_unbalanced_nodes(limit=limit)
        return {"suggestions": suggestions}
    except Exception as e:
        print(f"Unexpected error in get_suggestions: {e}\n{traceback.format_exc()}")
        # Return empty list on error to avoid breaking the UI component
        return {"suggestions": []}

def update_settings(data: Dict[str, Any]):
    """Update network settings."""
    global network
    updated = False
    try:
        # Update min_children_threshold if provided and valid
        if "min_children_threshold" in data:
            try:
                threshold = int(data["min_children_threshold"])
                if threshold < 1:
                    return {"error": "Minimum children threshold must be at least 1"}
                if network.min_children_threshold != threshold:
                    network.min_children_threshold = threshold
                    updated = True
                    print(f"Updated min_children_threshold to {threshold}")
            except (ValueError, TypeError):
                return {"error": "Invalid value for Minimum children threshold"}

        # Update balance_factor if provided and valid
        if "balance_factor" in data:
            try:
                balance = float(data["balance_factor"])
                if not (0 <= balance <= 1):
                     return {"error": "Balance factor must be between 0 and 1"}
                if network.balance_factor != balance:
                    network.balance_factor = balance
                    updated = True
                    print(f"Updated balance_factor to {balance}")
            except (ValueError, TypeError):
                return {"error": "Invalid value for Balance factor"}

        # If any setting was updated, recalculate metrics and save
        if updated:
            network._update_metrics()
            network.save(filename=NETWORK_FILENAME)
            print("Network metrics updated and saved.")

        return {"status": "success"}
    except Exception as e:
        print(f"Unexpected error in update_settings: {e}\n{traceback.format_exc()}")
        return {"error": f"An unexpected error occurred while updating settings: {str(e)}"}

def reload_network_from_file(filepath: str = os.path.join(data_dir, NETWORK_FILENAME)):
    """Forces a reload of the network from the specified file."""
    global network
    try:
        network = BusinessNetwork.load(filename=os.path.basename(filepath)) # Load expects filename, not full path relative to its own logic
        print(f"Network reloaded successfully from {filepath}")
        return True
    except Exception as e:
        print(f"Error reloading network from {filepath}: {e}")
        # Optionally, revert to an empty network or handle error differently
        # network = BusinessNetwork()
        return False

# --- END OF FILE logic.py ---