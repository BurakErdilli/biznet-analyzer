# --- START OF FILE main.py ---

from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Form, Depends
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from typing import Dict, List, Optional, Any, Union
import uvicorn
import os
import json
import traceback
from datetime import datetime
import shutil # For secure file saving

# Assuming 'app' directory is in the python path or use relative import if running as module
try:
    from app.network_model import BusinessNetwork
    import app.logic as logic
except ImportError:
     # Fallback for running main.py directly from project root for development
    from network_model import BusinessNetwork
    import logic

app = FastAPI(
    title="Business Network Analyzer API",
    description="API for managing and visualizing a business network.",
    version="1.0.0"
)

# Determine base directory and setup paths
# Correctly determine project root assuming main.py is inside 'app' or at root level
if os.path.basename(os.path.dirname(__file__)) == 'app':
     project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
else:
     project_root = os.path.dirname(os.path.abspath(__file__))

static_dir = os.path.join(project_root, "static")
templates_dir = os.path.join(project_root, "templates")
data_dir = os.path.join(project_root, "data")

# Ensure directories exist
os.makedirs(static_dir, exist_ok=True)
os.makedirs(templates_dir, exist_ok=True)
os.makedirs(data_dir, exist_ok=True)

# Mount static files
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Set up templates
templates = Jinja2Templates(directory=templates_dir)

# --- Global Error Handler ---
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    # Log the exception for debugging
    error_msg = f"Unhandled exception during request to {request.url}:\n{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
    print(error_msg) # Log to console/server logs

    # Return a user-friendly JSON error message
    return JSONResponse(
        status_code=500,
        content={"detail": f"An internal server error occurred: {str(exc)}"}
    )

# --- Frontend Route ---
@app.get("/", include_in_schema=False) # Hide from API docs
def home(request: Request):
    """Serves the main HTML page."""
    return templates.TemplateResponse("index.html", {"request": request})

# --- API Routes ---
@app.get("/api/network", tags=["Network"])
def api_get_network():
    """Retrieve the current state of the entire business network."""
    try:
        result = logic.get_network()
        return result
    except Exception as e:
        # This endpoint is critical, so let the global handler manage unexpected errors
        print(f"Error getting network data: {e}") # Log specific context
        raise HTTPException(status_code=500, detail=f"Failed to retrieve network data: {str(e)}")

@app.post("/api/nodes", status_code=201, tags=["Nodes"]) # Use 201 Created for successful POST
def api_add_node(data: Dict[str, Any]):
    """Add a new node to the network. Requires 'parent_id' if network is not empty. Optional 'id' can be provided."""
    result = logic.add_node(data)
    if "error" in result:
        raise HTTPException(
            status_code=400, # Bad Request for validation errors
            detail=result["error"]
        )
    return result # Returns {"status": "success", "id": new_node_id}

# This endpoint seems redundant if the logic is identical to POST /api/nodes.
# Kept for compatibility with existing JS, but consider merging or clarifying purpose.
@app.post("/api/nodes/near", status_code=201, tags=["Nodes"])
def api_add_node_near(data: Dict[str, Any]):
    """(Alias for Add Node) Add a new node, typically used by context menu 'add nearby'."""
    result = logic.add_node(data)
    if "error" in result:
        raise HTTPException(
            status_code=400,
            detail=result["error"]
        )
    return result

@app.delete("/api/nodes/{node_id}", status_code=200, tags=["Nodes"]) # Use 200 OK or 204 No Content
def api_delete_node(node_id: str):
    """Delete a node from the network. Fails if the node has children."""
    result = logic.remove_node(node_id)
    if "error" in result:
        if "not found" in result["error"].lower():
            raise HTTPException(
                status_code=404, # Not Found
                detail=result["error"]
            )
        elif "Cannot remove node with children" in result["error"]:
             raise HTTPException(
                status_code=409, # Conflict - cannot delete due to state
                detail=result["error"]
            )
        else:
             raise HTTPException(
                 status_code=400, # Bad Request for other validation errors
                 detail=result["error"]
             )
    # Return success status, maybe 204 No Content is better if no body needed
    return result # Returns {"status": "success"}

# This endpoint might be redundant if the main /api/network provides all necessary node details.
# Kept for potential direct access or future expansion.
@app.get("/api/nodes/{node_id}/insight", tags=["Nodes"])
def api_node_insight(node_id: str):
    """Get detailed calculated insights and properties for a specific node."""
    result = logic.get_node_insight(node_id)
    if "error" in result:
        if "not found" in result["error"].lower():
            raise HTTPException(
                status_code=404,
                detail=result["error"]
            )
        else:
            raise HTTPException(
                status_code=400,
                detail=result["error"]
            )
    return result

@app.get("/api/suggestions", tags=["Analysis"])
def api_get_suggestions(limit: int = 5):
    """Get suggested nodes to add children to, based on network balance metrics."""
    if limit < 1:
        raise HTTPException(status_code=400, detail="Limit must be at least 1")
    try:
        # Logic function now handles internal errors gracefully
        return logic.get_suggestions(limit)
    except Exception as e:
        # Log unexpected errors in this specific endpoint
        print(f"Error getting suggestions: {e}\n{traceback.format_exc()}")
        # Return empty suggestions as per requirement, but maybe signal error differently?
        # Consider returning 500 if the error isn't handled by logic.get_suggestions
        return {"suggestions": []}


@app.post("/api/settings", tags=["Settings"])
def api_update_settings(data: Dict[str, Any]):
    """Update network analysis settings like 'min_children_threshold' or 'balance_factor'."""
    result = logic.update_settings(data)
    if "error" in result:
        raise HTTPException(
            status_code=400,
            detail=result["error"]
        )
    return result # Returns {"status": "success"}

@app.post("/api/import", tags=["Import/Export"])
async def import_network(file: UploadFile = File(..., description="A JSON file representing the network structure.")):
    """Import a network structure from an uploaded JSON file, replacing the current network."""
    if file.content_type != "application/json":
        raise HTTPException(status_code=400, detail="Invalid file type. Please upload a JSON file.")

    # Define the path for the new network file
    import_filepath = os.path.join(data_dir, logic.NETWORK_FILENAME)
    temp_filepath = import_filepath + ".tmp" # Temporary file for safe writing

    try:
        # Read file content async
        contents = await file.read()

        # Validate JSON structure before replacing anything
        try:
            network_data = json.loads(contents)
            # Basic validation (presence of 'nodes' and 'graph' keys)
            if not isinstance(network_data.get("nodes"), dict) or not isinstance(network_data.get("graph"), dict):
                 raise ValueError("Invalid JSON structure: Missing 'nodes' or 'graph'.")
            # Try creating a temporary network instance to fully validate structure and data
            BusinessNetwork.from_json(contents)
        except (json.JSONDecodeError, ValueError, Exception) as json_err:
            raise HTTPException(status_code=400, detail=f"Invalid JSON file content: {str(json_err)}")

        # Save content to temporary file securely
        with open(temp_filepath, "wb") as f:
            f.write(contents)

        # Replace the original file with the temporary file
        shutil.move(temp_filepath, import_filepath)

        # Reload the global network instance from the new file
        if logic.reload_network_from_file(import_filepath):
             return {"success": True, "message": "Network imported successfully."}
        else:
             # This case indicates an error during reload AFTER successful file save/move
             raise HTTPException(status_code=500, detail="Network file saved but failed to reload.")

    except HTTPException:
        raise # Re-raise HTTP exceptions directly
    except Exception as e:
        print(f"Error importing network: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred during import: {str(e)}")
    finally:
        # Clean up temp file if it exists (e.g., if move failed)
        if os.path.exists(temp_filepath):
            os.remove(temp_filepath)
        await file.close()


@app.get("/api/export", tags=["Import/Export"])
def export_network():
    """Export the current network structure as a JSON file."""
    try:
        # Define export filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        export_filename = f"network_export_{timestamp}.json"
        temp_export_path = os.path.join(data_dir, export_filename) # Temporary path

        # Get current network data
        network_data = logic.get_network()

        # Save network data to the export file
        with open(temp_export_path, 'w') as f:
            json.dump(network_data, f, indent=2)

        # Return the file for download
        return FileResponse(
            path=temp_export_path,
            filename=export_filename, # Suggest filename to browser
            media_type="application/json",
            # Cleanup: FastAPI doesn't automatically delete the temp file after sending.
            # A background task could be used, or rely on OS temp cleaning.
            # For simplicity here, we leave the file temporarily.
            # background=BackgroundTask(os.remove, temp_export_path) # Requires importing BackgroundTask
        )
    except Exception as e:
        print(f"Error exporting network: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error exporting network: {str(e)}")

# --- Run Server ---
if __name__ == "__main__":
    # Determine host and port from environment variables or use defaults
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))
    reload_flag = bool(os.environ.get("RELOAD", True)) # Enable reload by default for dev

    print(f"Starting server on {host}:{port} with reload={'enabled' if reload_flag else 'disabled'}")
    uvicorn.run("main:app", host=host, port=port, reload=reload_flag)

# --- END OF FILE main.py ---