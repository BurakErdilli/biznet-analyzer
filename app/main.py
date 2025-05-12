from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Form, Depends, Body
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.background import BackgroundTasks # Import BackgroundTasks
from typing import Dict, List, Optional, Any, Union
import uvicorn
import os
import json
import traceback
from datetime import datetime
import shutil # For secure file saving

# Assuming 'app' directory is in the python path or use relative import if running as module
try:
    # Adjusted imports assuming standard structure
    from app.network_model import BusinessNetwork
    import app.logic as logic
except ImportError:
     # Fallback for running main.py directly from project root for development
    from network_model import BusinessNetwork
    import logic # type: ignore

app = FastAPI(
    title="Business Network Analyzer API",
    description="API for managing and visualizing a business network using Cytoscape.js.",
    version="1.2.0" # Updated version - Features added/removed
)

# --- Determine Directories ---
# Correctly determine project root assuming standard structure or direct run
if __name__ == "__main__" and __package__ is None:
     # Running main.py directly from project root
     project_root = os.path.dirname(os.path.abspath(__file__))
else:
     # Running as part of a package (e.g., via uvicorn main:app)
     # Assumes main.py is inside 'app' which is inside the project root
     project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

static_dir = os.path.join(project_root, "static")
templates_dir = os.path.join(project_root, "templates")
data_dir = os.path.join(project_root, "data") # Used for import/export path construction

# Ensure directories exist
os.makedirs(static_dir, exist_ok=True)
os.makedirs(templates_dir, exist_ok=True)
os.makedirs(data_dir, exist_ok=True) # Ensure data dir exists

# Mount static files
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Set up templates
templates = Jinja2Templates(directory=templates_dir)

# --- Global Error Handler ---
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    error_msg = f"Unhandled exception during request to {request.url}:\n{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
    print(error_msg)
    return JSONResponse(
        status_code=500,
        content={"detail": f"An internal server error occurred."} # Keep internal details private
    )

# --- Frontend Route ---
@app.get("/", include_in_schema=False)
def home(request: Request):
    # Pass global stats to the template
    stats = logic.get_global_stats()
    return templates.TemplateResponse("index.html", {"request": request, "global_stats": stats})

# --- API Routes ---
@app.get("/api/network", tags=["Network"])
def api_get_network():
    """Retrieve the current state of the entire business network including global stats."""
    try:
        # Logic module handles potential initialization errors
        result = logic.get_network() # Contains nodes, graph, settings
        stats = logic.get_global_stats()
        result["global_stats"] = stats # Add stats to the response
        return result
    except Exception as e:
        print(f"Error getting network data: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve network data.")

@app.post("/api/nodes", status_code=201, tags=["Nodes"])
def api_add_node(data: Dict[str, Any]):
    """Add a new node. Requires 'parent_id' if network isn't empty. Optional 'id' and 'value'."""
    result = logic.add_node(data)
    if "error" in result:
        # Use 400 for validation/user errors, 500 if it was unexpected internal
        status_code = 400 if "invalid" in result["error"].lower() or "required" in result["error"].lower() or "exist" in result["error"].lower() else 500
        raise HTTPException(status_code=status_code, detail=result["error"])
    return result # Returns {"status": "success", "id": new_node_id}

# Keeping this alias as frontend might use it, logic is identical to POST /api/nodes
@app.post("/api/nodes/near", status_code=201, tags=["Nodes"])
def api_add_node_near(data: Dict[str, Any]):
    """(Alias for Add Node) Add a new node."""
    result = logic.add_node(data)
    if "error" in result:
        status_code = 400 if "invalid" in result["error"].lower() or "required" in result["error"].lower() or "exist" in result["error"].lower() else 500
        raise HTTPException(status_code=status_code, detail=result["error"])
    return result

@app.delete("/api/nodes/{node_id}", status_code=200, tags=["Nodes"])
def api_delete_node(node_id: str):
    """Delete a leaf node. Fails if the node has children or doesn't exist."""
    result = logic.remove_node(node_id)
    if "error" in result:
        error_detail = result["error"].lower()
        if "not found" in error_detail:
            raise HTTPException(status_code=404, detail=result["error"])
        elif "cannot remove node with children" in error_detail:
             raise HTTPException(status_code=409, detail=result["error"]) # Conflict
        else:
             raise HTTPException(status_code=400, detail=result["error"]) # Other validation errors
    return result # Returns {"status": "success"}

@app.get("/api/nodes/{node_id}/insight", tags=["Nodes"])
def api_node_insight(node_id: str):
    """Get detailed insights for a specific node."""
    result = logic.get_node_insight(node_id)
    if "error" in result:
        if "not found" in result["error"].lower():
            raise HTTPException(status_code=404, detail=result["error"])
        else:
            # Could be 500 if it's an unexpected insight calculation error
            raise HTTPException(status_code=400, detail=result["error"])
    return result

# --- NEW: Subtree Import Endpoint ---
@app.post("/api/nodes/{parent_id}/subtree", status_code=201, tags=["Nodes", "Import/Export"])
async def api_add_subtree(parent_id: str, file: UploadFile = File(..., description="JSON file for the subtree")):
    """Add a subtree from a JSON file as children of the specified parent node."""
    if file.content_type != "application/json":
        raise HTTPException(status_code=400, detail="Invalid file type. Please upload a JSON file.")

    try:
        contents = await file.read()
        # Basic JSON validation
        try:
            subtree_data = json.loads(contents)
            if not isinstance(subtree_data, dict) or "nodes" not in subtree_data or "graph" not in subtree_data:
                 raise ValueError("Invalid subtree JSON structure. Must contain 'nodes' and 'graph'.")
        except json.JSONDecodeError as e:
            raise HTTPException(status_code=400, detail=f"Invalid JSON format: {e}")
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        result = logic.add_subtree(parent_id, subtree_data)
        if "error" in result:
            error_detail = result["error"].lower()
            if "parent node" in error_detail and "not found" in error_detail:
                 raise HTTPException(status_code=404, detail=result["error"])
            elif "collision" in error_detail or "invalid" in error_detail:
                 raise HTTPException(status_code=400, detail=result["error"])
            else: # Unexpected internal errors during add
                 raise HTTPException(status_code=500, detail=result["error"])

        return result # Returns {"status": "success", "added_nodes": [...]}

    except HTTPException:
        raise # Re-raise handled HTTP exceptions
    except Exception as e:
        print(f"Error adding subtree: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred during subtree import.")
    finally:
         if file: await file.close()

# --- NEW: Bulk Delete Endpoint ---
@app.post("/api/nodes/bulk-delete", status_code=200, tags=["Nodes"])
def api_bulk_delete_nodes(node_ids: List[str] = Body(..., description="List of node IDs to delete.")):
    """Delete multiple leaf nodes. Fails if any node has children or doesn't exist."""
    result = logic.bulk_remove_nodes(node_ids)
    if "error" in result:
        # Provide more detail if possible (e.g., which nodes failed)
        raise HTTPException(status_code=400, detail=result["error"])
    return result # Returns {"status": "success", "deleted_count": count, "failed_nodes": [...]}


@app.get("/api/suggestions", tags=["Analysis"])
def api_get_suggestions(limit: int = 5):
    """Get suggested nodes to add children to, ranked by criticality and depth."""
    if limit < 1:
        raise HTTPException(status_code=400, detail="Limit must be at least 1")
    try:
        # Logic function handles internal errors gracefully
        return logic.get_suggestions(limit)
    except Exception as e:
        print(f"Unexpected error getting suggestions: {e}\n{traceback.format_exc()}")
        # Return 500 for unexpected errors in this endpoint
        raise HTTPException(status_code=500, detail="Failed to retrieve suggestions.")


@app.post("/api/settings", tags=["Settings"])
def api_update_settings(data: Dict[str, Any]):
    """Update network analysis settings (Min Children Threshold)."""
    result = logic.update_settings(data)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result # Returns {"status": "success"}

@app.post("/api/import", tags=["Import/Export"])
async def import_network(file: UploadFile = File(..., description="A JSON file representing the network structure.")):
    """Import network from JSON, replacing the current one."""
    if file.content_type != "application/json":
        raise HTTPException(status_code=400, detail="Invalid file type. Please upload a JSON file.")

    # Define the target path using the standard filename in the data directory
    # logic.NETWORK_FILENAME provides the standard name "network.json"
    import_filepath = os.path.join(data_dir, logic.NETWORK_FILENAME)
    temp_filepath = import_filepath + ".tmp" # Temporary file for safe writing

    try:
        contents = await file.read()

        # Validate content by attempting to load it into a temporary BusinessNetwork instance
        try:
            # BusinessNetwork.from_json performs robust validation now
            temp_network = BusinessNetwork.from_json(contents)
            # Optionally add more checks on temp_network if needed
        except (json.JSONDecodeError, ValueError, Exception) as validation_err:
            raise HTTPException(status_code=400, detail=f"Invalid network file content: {str(validation_err)}")

        # Save validated content to temporary file securely
        with open(temp_filepath, "wb") as f:
            f.write(contents)

        # Replace the original file with the temporary file
        shutil.move(temp_filepath, import_filepath)

        # Reload the global network instance from the new file
        if logic.reload_network_from_file(import_filepath):
             return {"success": True, "message": "Network imported successfully."}
        else:
             # This indicates an error during reload AFTER successful file save/move
             raise HTTPException(status_code=500, detail="Network file saved but failed to reload into application.")

    except HTTPException:
        raise # Re-raise HTTP exceptions directly
    except Exception as e:
        print(f"Error importing network: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred during import.")
    finally:
        # Clean up temp file if it exists
        if os.path.exists(temp_filepath):
            try:
                os.remove(temp_filepath)
            except OSError as rm_err:
                print(f"Error removing temporary import file {temp_filepath}: {rm_err}")
        if file: # Ensure file is closed even if errors occurred before await file.close()
            await file.close()


# --- Helper function for cleaning up export file ---
def remove_file(path: str) -> None:
    try:
        os.remove(path)
        print(f"Cleaned up temporary export file: {path}")
    except OSError as e:
        print(f"Error removing temporary export file {path}: {e}")

# --- Export Endpoint ---
@app.get("/api/export", tags=["Import/Export"])
def export_network(background_tasks: BackgroundTasks): # Inject BackgroundTasks
    """Export the current network structure as a JSON file."""
    try:
        # Define export filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        export_filename = f"network_export_{timestamp}.json"
        # Create temp file in the data directory (accessible location)
        temp_export_path = os.path.join(data_dir, export_filename)

        # Get current network data from logic module
        network_data = logic.get_network()
        # Remove global stats before exporting if they were added
        network_data.pop("global_stats", None)

        # Save network data to the export file
        with open(temp_export_path, 'w') as f:
            json.dump(network_data, f, indent=2)

        # Add background task to remove the file after response is sent
        background_tasks.add_task(remove_file, temp_export_path)

        # Return the file for download
        return FileResponse(
            path=temp_export_path,
            filename=export_filename, # Suggest filename to browser
            media_type="application/json"
        )
    except Exception as e:
        print(f"Error exporting network: {e}\n{traceback.format_exc()}")
        # Clean up temp file if error occurs before returning response
        if 'temp_export_path' in locals() and os.path.exists(temp_export_path):
             remove_file(temp_export_path) # Attempt cleanup immediately
        raise HTTPException(status_code=500, detail="Error exporting network.")

# --- Run Server ---
if __name__ == "__main__":
    host = os.environ.get("HOST", "127.0.0.1") # Default to 127.0.0.1 for local dev
    port = int(os.environ.get("PORT", "8000"))
    # Disable reload by default unless explicitly set, as it can interfere with some setups
    reload_flag_str = os.environ.get("RELOAD", "false").lower()
    reload_flag = reload_flag_str in ["true", "1", "yes"]

    # Check if logic.network exists before starting (initial load)
    if logic.network is None:
         print("FATAL: Network object failed to initialize on startup. Check logs.")
         # sys.exit(1) # Or handle more gracefully

    print(f"Starting server on http://{host}:{port} with reload={'enabled' if reload_flag else 'disabled'}")
    uvicorn.run("main:app", host=host, port=port, reload=reload_flag)