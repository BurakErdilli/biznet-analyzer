// --- START OF FILE static/js/network.js ---

/**
 * Business Network Analyzer Frontend Script
 *
 * Handles Cytoscape visualization, user interactions, API calls,
 * and updates the UI based on network data.
 * v1.1 - Added reliability improvements for visualization initialization.
 */
document.addEventListener('DOMContentLoaded', () => {
    // --- Configuration Constants ---
    const API_BASE = '/api'; // Base URL for API endpoints
    const NETWORK_ENDPOINT = `${API_BASE}/network`; // Get full network data + stats
    const NODES_ENDPOINT = `${API_BASE}/nodes`; // Add/delete single nodes
    const BULK_DELETE_ENDPOINT = `${API_BASE}/nodes/bulk-delete`; // Delete multiple nodes
    const ADD_SUBTREE_ENDPOINT = (parentId) => `${API_BASE}/nodes/${parentId}/subtree`; // Add subtree under parent
    const SUGGESTIONS_ENDPOINT = `${API_BASE}/suggestions`; // Get nodes needing children
    const SETTINGS_ENDPOINT = `${API_BASE}/settings`; // Update analysis settings
    const IMPORT_ENDPOINT = `${API_BASE}/import`; // Import full network (replace)
    const EXPORT_ENDPOINT = `${API_BASE}/export`; // Export full network
    const DEFAULT_NODE_VALUE = 1000.0; // Default value for nodes if not specified

    // --- State Variables ---
    let cy; // Holds the Cytoscape instance
    let currentLayout = 'dagre'; // Current layout algorithm name
    let currentRankDir = 'TB'; // Current layout direction ('TB' or 'LR')
    let selectedNodeId = null; // ID of the currently selected node in the details panel
    let selectedNodesForBulk = new Set(); // IDs of nodes selected for bulk operations
    let networkDataCache = null; // Cache of the last fetched network data (nodes, graph, settings)
    let tippyInstances = []; // Array to hold Tippy.js tooltip instances
    let currentTheme = localStorage.getItem('theme') || 'light'; // 'light' or 'dark'
    let isSubtreeIsolated = false; // Flag if a subtree view is active
    let dataStats = { minValue: DEFAULT_NODE_VALUE, maxValue: DEFAULT_NODE_VALUE + 1, minProfit: 0, maxProfit: 1 }; // Min/max values for styling calculations
    let draggedNodeInfo = null; // Info about node being dragged { node, subtreeNodes, initialPosition }
    let contextMenuParentId = null; // Stores the parent ID when context menu for subtree import is opened

    // --- UI Element References ---
    const networkContainer = document.getElementById('network');
    const loadingIndicator = document.getElementById('loadingIndicator');
    // ... (keep all other UI element references from the previous version)
    const nodeDetailsPanel = document.getElementById('nodeDetails');
    const nodeStatsContainer = document.getElementById('nodeStats');
    const deleteNodeBtn = document.getElementById('deleteNodeBtn');
    const deleteNodeMsg = document.getElementById('deleteNodeMsg');
    const addNodeForm = document.getElementById('addNodeForm');
    const addNodeModal = document.getElementById('addNodeModal');
    const addNodeNearbyForm = document.getElementById('addNodeNearbyForm');
    const closeModalBtn = document.getElementById('closeModal');
    const suggestionsPanel = document.getElementById('suggestionsPanel');
    const suggestionsList = document.getElementById('suggestionsList');
    const refreshSuggestionsBtn = document.getElementById('refreshSuggestions');
    const settingsForm = document.getElementById('settingsForm');
    const minChildrenInput = document.getElementById('minChildrenThreshold');
    const importFileLabel = document.querySelector('label[for="importFile"]');
    const importFileInput = document.getElementById('importFile');
    const importSubtreeInput = document.getElementById('importSubtreeFile'); // Input for subtree import
    const exportBtn = document.getElementById('exportBtn');
    const centerNetworkBtn = document.getElementById('centerNetworkBtn');
    const zoomInBtn = document.getElementById('zoomInBtn');
    const zoomOutBtn = document.getElementById('zoomOutBtn');
    const layoutToggleBtn = document.getElementById('layoutToggle');
    const layoutToggleText = document.getElementById('layoutToggleText');
    const layoutToggleIcon = layoutToggleBtn.querySelector('i');
    const themeToggleBtn = document.getElementById('themeToggle');
    const themeIconMoon = document.getElementById('themeIconMoon');
    const themeIconSun = document.getElementById('themeIconSun');
    const searchInput = document.getElementById('searchNode');
    const searchClearBtn = document.getElementById('searchClearBtn');
    const isolateSubtreeBtn = document.getElementById('isolateSubtreeBtn');
    const showAllBtn = document.getElementById('showAllBtn');
    const reapplyLayoutBtn = document.getElementById('reapplyLayoutBtn');
    const bulkDeleteBtn = document.getElementById('bulkDeleteBtn'); // Button for bulk delete
    const toastElement = document.getElementById('toast');
    // Global Stats Bar Elements
    const statTotalNodes = document.getElementById('statTotalNodes');
    const statTotalEdges = document.getElementById('statTotalEdges');
    const statMaxDepth = document.getElementById('statMaxDepth');
    const statTotalValue = document.getElementById('statTotalValue');
    const statTotalProfit = document.getElementById('statTotalProfit');


    // --- Helper Functions ---
    // showLoading, hideLoading, showToast, debounce, apiCall (Keep these exactly as in the previous version)
    const showLoading = () => { /* ... */ if (loadingIndicator) loadingIndicator.style.display = 'flex'; };
    const hideLoading = () => { /* ... */ if (loadingIndicator) loadingIndicator.style.display = 'none'; };
    const showToast = (message, type = 'info', duration = 3000) => { /* ... implementation ... */ };
    function debounce(func, wait) { /* ... implementation ... */ }
    async function apiCall(endpoint, options = {}) { /* ... implementation ... */ }


    // --- Color & Style Mapping ---
    // interpolateColor, interpolateHeatmapColor, mapValueToSize, getThemeColor, calculateDataStats, getCytoscapeStyle
    // (Keep these exactly as in the previous version)
    function interpolateColor(value, minVal, maxVal, colors) { /* ... */ }
    function interpolateHeatmapColor(value, minVal, maxVal, colors) { /* ... */ }
    function mapValueToSize(value, minVal, maxVal, minSize, maxSize) { /* ... */ }
    const getThemeColor = (varName) => getComputedStyle(document.documentElement).getPropertyValue(varName).trim();
    function calculateDataStats(nodes) { /* ... implementation ... */ return dataStats; } // Make sure it returns the result
    const getCytoscapeStyle = (theme) => { /* ... implementation ... */ return [ /* style objects */ ]; };

    // --- Cytoscape Initialization & Data Loading ---

    /**
     * Configures the layout options for Cytoscape (using Dagre).
     */
    const layoutOptions = {
        dagre: {
            name: 'dagre',
            rankDir: currentRankDir, // Layout direction ('TB' or 'LR')
            spacingFactor: 1.2, // Multiplier for node spacing
            fit: true, // Fit the graph to the viewport after layout
            padding: 30, // Padding around the graph
            animate: true, // Animate layout changes (can disable if causing issues)
            animationDuration: 400, // Duration of layout animation (slightly faster)
            ready: () => { console.log("Dagre layout ready."); }, // Log when layout engine is ready
            stop: () => { console.log("Dagre layout stopped."); }  // Log when layout calculation stops
        }
    };

    /**
     * Initializes or Updates the Cytoscape instance.
     * This function now handles destruction, creation, styling, events, layout, and post-layout setup.
     * @param {object[]} elements - Array of nodes and edges in Cytoscape format. Can be empty.
     */
    function initializeOrUpdateCytoscape(elements) {
        console.log("Attempting to initialize or update Cytoscape...");

        // 1. Destroy previous instance and clean up associated resources (tooltips)
        if (cy) {
            console.log("Destroying previous Cytoscape instance and tooltips.");
            destroyTooltips(); // Clean up tooltips first
            try {
                 cy.destroy();
            } catch (destroyError) {
                 console.error("Error destroying previous Cytoscape instance:", destroyError);
                 // Continue best effort
            }
            cy = null;
        }

        // 2. Crucial Check: Ensure the container element exists in the DOM
        if (!networkContainer) {
            console.error("FATAL: Network container div (#network) not found! Cannot initialize visualization.");
            showToast("Visualization Error: Container missing.", "error", 10000);
            // Optionally display error in the expected container area if possible, or just log.
            hideLoading(); // Ensure loading is hidden
            return; // Stop initialization
        }

        // Clear any previous error messages in the container
        networkContainer.innerHTML = '';

        // 3. Log element count
        const nodeCount = elements.filter(e => e.group === 'nodes').length;
        const edgeCount = elements.filter(e => e.group === 'edges').length;
        console.log(`Initializing Cytoscape with ${nodeCount} nodes and ${edgeCount} edges.`);
        if (nodeCount === 0) {
             console.warn("Network appears to be empty or data transformation failed.");
             // Optionally display "Empty Network" message in the container
             networkContainer.innerHTML = '<div class="flex items-center justify-center h-full theme-text-muted italic">Network is empty</div>';
        }

        // 4. Initialize Cytoscape - Wrapped in try...catch
        try {
            cy = cytoscape({
                container: networkContainer,
                elements: elements,
                layout: { name: 'preset' }, // Use preset initially to load elements faster
                style: getCytoscapeStyle(currentTheme), // Apply style immediately
                zoom: 1, minZoom: 0.1, maxZoom: 3.0,
                wheelSensitivity: 0.3,
                boxSelectionEnabled: true,
                autounselectify: false,
                autoungrabify: false, // Keep nodes draggable
                 // Motion blur can improve perceived performance during animations/panning
                 // textureOnViewport: true, // Can help performance but might look blurry briefly
                 // hideEdgesOnViewport: false, // Set true if edge rendering is slow with many edges
                 // hideLabelsOnViewport: false // Set true if label rendering is slow
            });

            console.log("Cytoscape instance created.");

            // 5. Setup Core Event Listeners (Select, Drag, Tap) - These can be set up immediately
            console.log("Setting up core Cytoscape event listeners...");
            setupCytoscapeEventListeners();

            // 6. Handle Layout and Post-Layout Setup (Tooltips, Context Menus)
            // Use cy.ready() to ensure the instance is fully interactive
            cy.ready(() => {
                console.log("Cytoscape instance is ready.");
                if (cy.elements().length > 0) {
                     console.log("Running layout...");
                     // Run the layout and wait for it to finish
                     const layout = cy.layout(layoutOptions.dagre);
                     layout.promiseOn('layoutstop').then(() => {
                         console.log("Layout finished. Setting up tooltips and context menu.");
                         // Setup things that might depend on element positions *after* layout
                         setupTooltips();
                         setupContextMenu();
                         console.log("Cytoscape initialization and layout complete.");
                         hideLoading(); // Hide loading AFTER layout is done
                     }).catch(layoutError => {
                          console.error("Layout execution failed:", layoutError);
                          showToast("Error applying network layout.", "error");
                          hideLoading(); // Hide loading even if layout fails
                     });
                     layout.run(); // Start the layout process
                } else {
                    console.log("Network is empty, skipping layout. Setting up empty context menu/tooltips.");
                    // Still setup empty tooltips/menus so they are ready if nodes are added later
                    setupTooltips();
                    setupContextMenu();
                    hideLoading(); // Hide loading as there's no layout to wait for
                }
            });

        } catch (error) {
            // --- Catch Cytoscape Initialization Errors ---
            console.error("FATAL: Cytoscape initialization failed:", error);
            showToast(`Visualization Error: ${error.message}`, "error", 10000);
            // Display error message directly in the network container
            if (networkContainer) {
                networkContainer.innerHTML = `<div class="p-4 text-center theme-danger flex flex-col items-center justify-center h-full">
                    <i class="fas fa-exclamation-triangle text-3xl mb-2"></i>
                    <span>Failed to initialize visualization.</span>
                    <span class="text-xs mt-1">(${error.message})</span>
                    <span class="text-xs mt-1">Check console for details.</span>
                  </div>`;
            }
            hideLoading(); // Ensure loading is hidden
            cy = null; // Ensure cy state is null on failure
        }
    }


    /**
     * Transforms the network data received from the API into Cytoscape's expected format.
     * Calculates data statistics needed for styling.
     * @param {object} data - The raw network data from the API ({ nodes: {...}, graph: {...}, settings: {...} }).
     * @returns {object[]} An array of elements formatted for Cytoscape, or null if data is invalid.
     */
    function transformDataForCytoscape(data) {
        console.log("Transforming API data for Cytoscape format...");
        const elements = [];
        networkDataCache = data; // Cache the raw data

        // **Robust Validation:** Check if essential data parts exist and are objects
        if (!data || typeof data !== 'object') {
             console.error("Invalid API response: Data is null or not an object.");
             showToast("Error: Invalid data received from server.", "error");
             return null; // Indicate failure
        }
         if (!data.nodes || typeof data.nodes !== 'object') {
            console.error("Invalid API response: Missing or invalid 'nodes' data.");
            // Don't show toast here, maybe network is just empty. Log is sufficient.
             // Initialize with empty nodes if graph exists, otherwise return null
             data.nodes = {}; // Assume empty if missing but graph might exist
             // return null; // Or fail hard if nodes are expected
        }
        if (!data.graph || typeof data.graph !== 'object') {
             console.warn("API response: Missing or invalid 'graph' data. Assuming no edges.");
             data.graph = {}; // Assume empty graph if missing
        }


        // Calculate min/max values for styling normalization
        dataStats = calculateDataStats(data.nodes); // Handles empty nodes case

        // --- Transform Nodes ---
        const nodeIds = Object.keys(data.nodes);
        console.log(`Transforming ${nodeIds.length} nodes.`);
        for (const nodeId of nodeIds) {
            const node = data.nodes[nodeId];
            if (node && node.id) { // Basic validation
                elements.push({ group: 'nodes', data: { id: node.id, ...node } });
            } else { console.warn(`Skipping invalid node data for ID: ${nodeId}`); }
        }

        // --- Transform Edges ---
        let edgeCount = 0;
        const graphSources = Object.keys(data.graph);
        console.log(`Transforming edges from ${graphSources.length} sources in graph data.`);
        for (const parentId of graphSources) {
             // Ensure source node exists before processing its edges
             if (!data.nodes[parentId]) {
                  // console.warn(`Skipping edges from source node '${parentId}' as it's missing in 'nodes' data.`);
                  continue;
             }

            const children = data.graph[parentId];
            if (Array.isArray(children)) {
                children.forEach((edgeData) => {
                    let childId, capacity = 1.0;
                    if (Array.isArray(edgeData) && edgeData.length > 0) {
                        childId = edgeData[0];
                        if (edgeData.length > 1 && edgeData[1] !== null) {
                            const parsedCapacity = parseFloat(edgeData[1]);
                            if (!isNaN(parsedCapacity)) capacity = parsedCapacity;
                        }
                    } else { return; } // Skip invalid edge entry

                    // **Crucial Check:** Ensure target node also exists
                    if (data.nodes[childId]) {
                        elements.push({
                            group: 'edges',
                            data: { id: `${parentId}->${childId}`, source: parentId, target: childId, capacity: capacity }
                        });
                        edgeCount++;
                    } else {
                        // console.warn(`Skipping edge: ${parentId} -> ${childId} (Target node missing in 'data.nodes')`);
                    }
                });
            }
        }

        console.log(`Data transformation complete: ${nodeIds.length} nodes, ${edgeCount} edges processed.`);
        return elements; // Return the array for Cytoscape
    }

    /**
     * Fetches the latest network data, transforms it, and initializes/updates Cytoscape.
     * Also updates global stats and suggestions. Main entry point for loading.
     */
    async function loadAndRenderNetwork() {
        console.log("--- Loading and Rendering Network ---");
        showLoading();
        selectedNodeId = null; isSubtreeIsolated = false;
        updateNodeDetails(null); updateIsolateButtons(null); updateBulkActionButtons();

        try {
            // 1. Fetch Data
            const data = await apiCall(NETWORK_ENDPOINT);
            console.log("API data received successfully.");

            // 2. Transform Data
            const elements = transformDataForCytoscape(data);
            // Check if transformation was successful before initializing
            if (elements === null) {
                 throw new Error("Data transformation failed. Check console for details.");
            }
            console.log("Data transformed successfully.");

            // 3. Initialize or Update Cytoscape
            // This function now handles the core initialization, layout, and post-setup steps.
            initializeOrUpdateCytoscape(elements);

            // 4. Update UI Elements (Settings, Stats, Suggestions) - outside Cytoscape init
            if (data.settings) {
                minChildrenInput.value = data.settings.min_children_threshold ?? 2;
            }
            if (data.global_stats) {
                updateGlobalStats(data.global_stats);
            } else {
                 console.warn("Global stats missing in network response.");
                 updateGlobalStats({}); // Clear stats display
            }
            loadSuggestions(); // Load suggestions panel content

            // NOTE: hideLoading() is now called inside initializeOrUpdateCytoscape after layout/setup

        } catch (error) {
            console.error("FATAL: Failed to load and render network:", error);
            // Ensure loading is hidden
            hideLoading();
            // Display error in container or via toast (handled partly by apiCall/initializeOrUpdateCytoscape)
            if (!networkContainer.innerHTML.includes('Failed')) { // Avoid duplicate messages
                 showToast(`Error loading network: ${error.message}`, 'error', 6000);
                 networkContainer.innerHTML = `<div class="p-4 text-center theme-danger flex flex-col items-center justify-center h-full">
                    <i class="fas fa-exclamation-triangle text-3xl mb-2"></i>
                    <span>Error loading network data.</span>
                     <span class="text-xs mt-1">(${error.message})</span>
                     <span class="text-xs mt-1">Please try refreshing or check server logs.</span>
                 </div>`;
            }
            // Clear other UI elements on failure
            updateGlobalStats({});
            suggestionsList.innerHTML = '<p class="text-xs theme-danger">Network load failed.</p>';
            initializeOrUpdateCytoscape([]); // Attempt to clear the graph visualization
        }
    }


    /**
     * Refreshes the visualization with the latest data from the backend *without* full re-initialization.
     * Uses cy.json() for potentially faster updates if only data changes.
     * @param {boolean} runLayout - Whether to re-run the layout after updating elements.
     */
    async function refreshVisualization(runLayout = true) {
        console.log(`--- Refreshing Visualization (runLayout: ${runLayout}) ---`);
        // Fallback to full load if Cytoscape isn't initialized (shouldn't happen often)
        if (!cy) {
            console.warn("Refresh called but Cytoscape not initialized. Performing full load instead.");
            loadAndRenderNetwork();
            return;
        }
        showLoading();

        try {
            // 1. Fetch latest data
            const data = await apiCall(NETWORK_ENDPOINT);
            console.log("API data received for refresh.");

             // 2. Transform Data
            const elements = transformDataForCytoscape(data);
             if (elements === null) {
                 throw new Error("Data transformation failed during refresh.");
             }
            console.log("Data transformed successfully for refresh.");

            const lastSelectedId = selectedNodeId; // Store current selection ID

            // 3. Update Cytoscape Elements using cy.json()
            console.log("Updating Cytoscape elements using cy.json()...");
            cy.json({ elements: elements }); // Update elements in place

            // 4. Re-apply Style (dataStats might have changed)
            console.log("Re-applying style...");
            cy.style(getCytoscapeStyle(currentTheme));

            // 5. Run Layout (Optional) and Finalize
            const layoutPromise = runLayout ? cy.layout(layoutOptions.dagre).run().promiseOn('layoutstop') : Promise.resolve();

            layoutPromise.then(() => {
                 console.log("Layout complete (or skipped). Finalizing refresh...");
                 // Perform final updates after layout settles
                 finalizeRefresh(lastSelectedId, data.global_stats); // Pass stats to finalize
                 // hideLoading() is called inside finalizeRefresh
            }).catch(layoutError => {
                  console.error("Layout execution failed during refresh:", layoutError);
                  showToast("Error applying network layout during refresh.", "error");
                  // Still try to finalize display state even if layout fails
                  finalizeRefresh(lastSelectedId, data.global_stats);
            });


            // 6. Update UI Elements (Settings, Suggestions)
            if (data.settings) {
                minChildrenInput.value = data.settings.min_children_threshold ?? 2;
            }
            loadSuggestions(); // Refresh suggestions list


        } catch (error) {
            console.error("Failed to refresh network visualization:", error);
            hideLoading(); // Ensure loading is hidden on error
            showToast(`Error refreshing network: ${error.message}`, 'error');
            // Avoid clearing the whole graph on refresh error, just show toast.
        }
    }

    /**
     * Helper function called after elements are updated and layout is run during refresh.
     * Re-applies tooltips, search highlighting, isolation state, and selection.
     * @param {string | null} lastSelectedId - The ID of the node that was selected before refresh.
     * @param {object | null} globalStats - The latest global stats data.
     */
    function finalizeRefresh(lastSelectedId, globalStats) {
        console.log("Finalizing refresh operations...");
        if (!cy) { hideLoading(); return; } // Safety check

        // 1. Refresh tooltips for potentially new/updated elements
        setupTooltips();

        // 2. Re-apply search highlighting based on current input value
        handleSearch(searchInput.value, false); // Don't fit view on refresh search re-apply

        // 3. Re-apply subtree isolation if it was active and the node still exists
        let nodeForIsolationExists = lastSelectedId && cy.getElementById(lastSelectedId)?.length > 0;
        if (isSubtreeIsolated && nodeForIsolationExists) {
            isolateSubtree(lastSelectedId, false); // Re-isolate without fitting view
        } else {
            // If isolation node is gone or wasn't isolated, ensure full network is visible
             if (isSubtreeIsolated) isSubtreeIsolated = false; // Mark as not isolated anymore
            showAllNodes(false); // Ensure full network is visible (without fitting)
        }

        // 4. Reset current selection state variable before potentially restoring
        const previouslySelectedBulk = new Set(selectedNodesForBulk); // Keep track of bulk selected
        selectedNodeId = null;
        selectedNodesForBulk.clear(); // Clear bulk selection set too

        // Clear details panel initially (will be repopulated if selection is restored)
        updateNodeDetails(null);
        // Update bulk action button state (will be updated again if selection restored)
        updateBulkActionButtons();

        // 5. Restore selection if the nodes still exist (handle single and bulk)
        let restoredSingleSelection = false;
         if (lastSelectedId && cy.getElementById(lastSelectedId)?.length > 0) {
            const nodeToReselect = cy.getElementById(lastSelectedId);
            nodeToReselect.select(); // Programmatically select the node
            console.log(`Restored single selection: ${lastSelectedId}`);
            // updateNodeDetails will be called by the 'select' event listener
            // selectedNodesForBulk set will be updated by 'select' event listener
            restoredSingleSelection = true;
        }

        // Restore other bulk selected nodes if they still exist (and weren't the primary selection)
         previouslySelectedBulk.forEach(id => {
             if(id !== lastSelectedId && cy.getElementById(id)?.length > 0) {
                  cy.getElementById(id).select(); // Add to selection
                  console.log(`Restored additional bulk selection: ${id}`);
             }
         });


        // 6. Update isolate and bulk action buttons based on the final selection state
        updateIsolateButtons(selectedNodeId); // Uses the potentially restored primary selectedNodeId
        updateBulkActionButtons(); // Reflects the final state of cy.$(':selected')

        // 7. Update global stats display
        updateGlobalStats(globalStats ?? {}); // Update with new stats or clear if unavailable

        console.log("Refresh finalization complete.");
        hideLoading(); // Hide loading indicator at the very end
    }


    // --- UI Update Functions ---
    // updateGlobalStats, updateNodeDetails, loadSuggestions, applyTheme, toggleLayoutDirection
    // (Keep implementations from previous version, ensuring they check for element existence if needed)
    function updateGlobalStats(stats) { /* ... implementation ... */ }
    function updateNodeDetails(nodeData) { /* ... implementation ... */ }
    async function loadSuggestions() { /* ... implementation ... */ }
    function applyTheme(theme) { /* ... implementation ... */ }
    function toggleLayoutDirection() { /* ... implementation ... */ }

    // --- Tooltips & Context Menu Setup ---
    // setupTooltips, destroyTooltips, setupContextMenu, openAddChildModal
    // (Keep implementations from previous version)
    function setupTooltips() { /* ... implementation ... */ }
    function destroyTooltips() { /* ... implementation ... */ }
    function setupContextMenu() { /* ... implementation ... */ }
    function openAddChildModal(parentId) { /* ... implementation ... */ }

    // --- Action Handlers (API interactions) ---
    // handleAddNode, handleDeleteNode, handleUpdateSettings, handleImport, handleExport, handleSubtreeImport, handleBulkDelete
    // (Keep implementations from previous version)
    async function handleAddNode(formData) { /* ... implementation ... */ }
    async function handleDeleteNode(nodeId) { /* ... implementation ... */ }
    async function handleUpdateSettings(event) { /* ... implementation ... */ }
    async function handleImport(event) { /* ... implementation ... */ }
    async function handleExport() { /* ... implementation ... */ }
    async function handleSubtreeImport(event) { /* ... implementation ... */ }
    async function handleBulkDelete() { /* ... implementation ... */ }

    // --- Feature Handlers: Search, Isolate, Dragging ---
    // handleSearch, isolateSubtree, showAllNodes, updateIsolateButtons, updateBulkActionButtons
    // (Keep implementations from previous version)
    const handleSearch = debounce((searchTerm, fitView = false) => { /* ... */ }, 300);
    function isolateSubtree(nodeId, fitView = true) { /* ... implementation ... */ }
    function showAllNodes(fitView = true) { /* ... implementation ... */ }
    function updateIsolateButtons(currentSelectedNodeId) { /* ... implementation ... */ }
    function updateBulkActionButtons() { /* ... implementation ... */ }

    // --- Cytoscape Event Listeners Setup ---
    // setupCytoscapeEventListeners (Keep implementation from previous version)
    function setupCytoscapeEventListeners() { /* ... implementation ... */ }

    // --- Initial Setup & Load ---
    console.log("DOM Loaded. Starting application setup.");
    applyTheme(currentTheme);

    // Attach UI Event Listeners (Keep all attachments from previous version)
    console.log("Attaching UI event listeners...");
    themeToggleBtn?.addEventListener('click', () => applyTheme(currentTheme === 'light' ? 'dark' : 'light'));
    layoutToggleBtn?.addEventListener('click', toggleLayoutDirection);
    addNodeForm?.addEventListener('submit', (e) => { e.preventDefault(); handleAddNode(new FormData(addNodeForm)); });
    addNodeNearbyForm?.addEventListener('submit', (e) => { e.preventDefault(); handleAddNode(new FormData(addNodeNearbyForm)); });
    closeModalBtn?.addEventListener('click', () => addNodeModal.classList.add('hidden'));
    deleteNodeBtn?.addEventListener('click', () => { /* ... */ });
    bulkDeleteBtn?.addEventListener('click', handleBulkDelete);
    settingsForm?.addEventListener('submit', handleUpdateSettings);
    refreshSuggestionsBtn?.addEventListener('click', loadSuggestions);
    importFileInput?.addEventListener('change', handleImport);
    importSubtreeInput?.addEventListener('change', handleSubtreeImport);
    exportBtn?.addEventListener('click', handleExport);
    centerNetworkBtn?.addEventListener('click', () => cy?.animate({ fit: { padding: 30 } }, { duration: 400 }));
    zoomInBtn?.addEventListener('click', () => cy?.zoom(cy.zoom() * 1.2));
    zoomOutBtn?.addEventListener('click', () => cy?.zoom(cy.zoom() / 1.2));
    reapplyLayoutBtn?.addEventListener('click', () => { /* ... use refreshVisualization(true) or the layout logic from previous version */ });
    searchInput?.addEventListener('input', (e) => handleSearch(e.target.value, true));
    searchClearBtn?.addEventListener('click', () => { searchInput.value = ''; handleSearch('', true); });
    isolateSubtreeBtn?.addEventListener('click', () => { if (selectedNodeId) isolateSubtree(selectedNodeId, true); });
    showAllBtn?.addEventListener('click', () => showAllNodes(true));
    reapplyLayoutBtn?.addEventListener('click', () => {
        if (cy) {
            console.log("Re-applying layout via button...");
            showLoading(); // Show loading as layout can take time
            // showAllNodes(false); // Ensure all nodes are visible before layout - Optional, depends if you want layout on isolated view
            cy.layout(layoutOptions.dagre).run().promiseOn('layoutstop').then(() => {
                hideLoading(); // Hide loading when layout finishes
                console.log("Layout re-application complete.");
                // Tooltips might need repositioning after manual layout
                setupTooltips();
            }).catch(err => {
                 console.error("Error during manual layout re-application:", err);
                 hideLoading();
                 showToast("Failed to re-apply layout.", "error");
            });
        }
    });


    // Initial Data Load
    loadAndRenderNetwork(); // Start the process

    console.log("Initial setup and data load sequence initiated.");

}); // End DOMContentLoaded
// --- END OF FILE static/js/network.js ---