// --- START OF FILE static/js/network.js ---

document.addEventListener('DOMContentLoaded', () => {
    // --- Config ---
    const API_BASE = '/api';
    const NETWORK_ENDPOINT = `${API_BASE}/network`;
    const NODES_ENDPOINT = `${API_BASE}/nodes`;
    const SUGGESTIONS_ENDPOINT = `${API_BASE}/suggestions`;
    const SETTINGS_ENDPOINT = `${API_BASE}/settings`;
    const IMPORT_ENDPOINT = `${API_BASE}/import`;
    const EXPORT_ENDPOINT = `${API_BASE}/export`;
    const DEFAULT_NODE_VALUE = 1000.0;

    // --- State ---
    let cy; // Cytoscape instance
    let currentLayout = 'dagre';
    let currentRankDir = 'TB';
    let selectedNodeId = null;
    let networkDataCache = null;
    let tippyInstances = [];
    let currentTheme = localStorage.getItem('theme') || 'light';
    let isSubtreeIsolated = false;
    let dataStats = { minValue: DEFAULT_NODE_VALUE, maxValue: DEFAULT_NODE_VALUE, minProfit: 0, maxProfit: 1 };
    let draggedNodeInfo = null; // Stores info about node being dragged { node, subtreeNodes, initialPosition }

    // --- UI Elements ---
    const networkContainer = document.getElementById('network');
    const loadingIndicator = document.getElementById('loadingIndicator');
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
    const balanceFactorInput = document.getElementById('balanceFactor');
    const importFileLabel = document.querySelector('label[for="importFile"]');
    const importFileInput = document.getElementById('importFile');
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
    const reapplyLayoutBtn = document.getElementById('reapplyLayoutBtn'); // Added button
    const toastElement = document.getElementById('toast');

    // --- Helper Functions ---
    const showLoading = () => { console.log("Showing loading"); loadingIndicator.style.display = 'flex'; };
    const hideLoading = () => { console.log("Hiding loading"); loadingIndicator.style.display = 'none'; };

    const showToast = (message, type = 'info', duration = 3000) => {
        toastElement.textContent = message;
        toastElement.className = ''; // Clear previous classes
        toastElement.classList.add(type, 'show');
        void toastElement.offsetWidth; // Force reflow
        toastElement.style.opacity = 1;
        toastElement.style.visibility = 'visible';
        setTimeout(() => {
            toastElement.style.opacity = 0;
            toastElement.style.visibility = 'hidden';
            setTimeout(() => toastElement.className = '', 300);
        }, duration);
    };

    function debounce(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => { clearTimeout(timeout); func(...args); };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    };

    async function apiCall(endpoint, options = {}) {
        showLoading();
        try {
            const response = await fetch(endpoint, options);
            if (!response.ok) {
                let errorMsg = `Error ${response.status}: ${response.statusText}`;
                try { errorMsg = (await response.json()).detail || errorMsg; } catch (e) { /* Ignore */ }
                throw new Error(errorMsg);
            }
            if (response.status === 204) return { success: true };
            if (options.responseType === 'blob') return await response.blob();
            return await response.json();
        } catch (error) {
            console.error(`API Error (${endpoint}):`, error);
            showToast(error.message, 'error');
            throw error;
        } finally {
            hideLoading();
        }
    }

    // --- Color & Style Mapping ---
    function interpolateColor(value, minVal, maxVal, colors) {
        const clampedVal = Math.max(minVal, Math.min(value ?? 0, maxVal));
        if (maxVal <= minVal) return colors[0];
        const ratio = (clampedVal - minVal) / (maxVal - minVal);
        const index = Math.min(colors.length - 1, Math.floor(ratio * (colors.length - 1)));
        return colors[index];
    }
    function interpolateHeatmapColor(value, minVal, maxVal, colors) {
        const [colorLow, colorMid, colorHigh] = colors;
        const clampedVal = Math.max(minVal, Math.min(value ?? 0, maxVal));
        if (maxVal <= minVal) return colorLow;
        const ratio = (clampedVal - minVal) / (maxVal - minVal);
        const hexToRgb = (hex) => { const b = parseInt(hex.slice(1), 16); return [(b >> 16) & 255, (b >> 8) & 255, b & 255]; };
        const rgbToHex = (r, g, b) => "#" + [r, g, b].map(x => Math.round(x).toString(16).padStart(2, '0')).join('');
        const rgbLow = hexToRgb(colorLow); const rgbMid = hexToRgb(colorMid); const rgbHigh = hexToRgb(colorHigh);
        let r, g, b;
        if (ratio < 0.5) { const sR = ratio * 2; r = rgbLow[0] + (rgbMid[0] - rgbLow[0]) * sR; g = rgbLow[1] + (rgbMid[1] - rgbLow[1]) * sR; b = rgbLow[2] + (rgbMid[2] - rgbLow[2]) * sR; }
        else { const sR = (ratio - 0.5) * 2; r = rgbMid[0] + (rgbHigh[0] - rgbMid[0]) * sR; g = rgbMid[1] + (rgbHigh[1] - rgbMid[1]) * sR; b = rgbMid[2] + (rgbHigh[2] - rgbMid[2]) * sR; }
        return rgbToHex(r, g, b);
    }
    function mapValueToSize(value, minVal, maxVal, minSize, maxSize) {
        const clampedVal = Math.max(minVal, Math.min(value ?? 0, maxVal));
        if (maxVal <= minVal) return (minSize + maxSize) / 2;
        const ratio = (clampedVal - minVal) / (maxVal - minVal);
        return minSize + Math.sqrt(ratio) * (maxSize - minSize);
    }
    const getThemeColor = (varName) => getComputedStyle(document.documentElement).getPropertyValue(varName).trim();

    function calculateDataStats(nodes) {
        let minValue = Infinity, maxValue = -Infinity, minProfit = Infinity, maxProfit = -Infinity;
        if (!nodes || Object.keys(nodes).length === 0) return { minValue: DEFAULT_NODE_VALUE, maxValue: DEFAULT_NODE_VALUE, minProfit: 0, maxProfit: 1 };
        Object.values(nodes).forEach(node => { const v = node.value ?? DEFAULT_NODE_VALUE; const p = node.profit ?? 0; minValue = Math.min(minValue, v); maxValue = Math.max(maxValue, v); minProfit = Math.min(minProfit, p); maxProfit = Math.max(maxProfit, p); });
        minValue = (minValue === Infinity) ? DEFAULT_NODE_VALUE : minValue; maxValue = (maxValue === -Infinity) ? DEFAULT_NODE_VALUE : maxValue; if (minValue === maxValue) maxValue = minValue + 1;
        minProfit = (minProfit === Infinity) ? 0 : minProfit; maxProfit = (maxProfit === -Infinity) ? 0 : maxProfit; if (minProfit === maxProfit) maxProfit = minProfit + 1;
        console.log("Calculated Stats:", { minValue, maxValue, minProfit, maxProfit });
        return { minValue, maxValue, minProfit, maxProfit };
    }

    const getCytoscapeStyle = (theme) => {
        const { minValue, maxValue, minProfit, maxProfit } = dataStats;
        const nodeValueLow = getThemeColor('--node-value-low'), nodeValueMed = getThemeColor('--node-value-med'), nodeValueHigh = getThemeColor('--node-value-high');
        const nodeBorderLow = getThemeColor('--node-border-low'), nodeBorderMed = getThemeColor('--node-border-med'), nodeBorderHigh = getThemeColor('--node-border-high');
        const edgeColor = getThemeColor('--edge-color'), selectedColor = getThemeColor('--selected-color');
        const textColor = theme === 'light' ? '#212529' : '#f8f9fa', highlightColor = getThemeColor('--highlight');
        return [
            { selector: 'node', style: {
                'background-color': (ele) => interpolateColor(ele.data('value') ?? DEFAULT_NODE_VALUE, minValue, maxValue, [nodeValueLow, nodeValueMed, nodeValueHigh]),
                'border-width': (ele) => ele.data('criticality') > 0 ? mapValueToSize(ele.data('criticality'), 0, 1, 2, 6) : 1.5,
                'border-color': (ele) => ele.data('criticality') > 0 ? interpolateHeatmapColor(ele.data('criticality'), 0, 1, [nodeBorderLow, nodeBorderMed, nodeBorderHigh]) : edgeColor,
                'width': (ele) => mapValueToSize(ele.data('profit') ?? 0, minProfit, maxProfit, 25, 75),
                'height': (ele) => mapValueToSize(ele.data('profit') ?? 0, minProfit, maxProfit, 25, 75),
                'label': 'data(id)', 'color': textColor, 'font-size': '10px', 'text-valign': 'bottom', 'text-halign': 'center', 'text-margin-y': 5,
                'text-wrap': 'wrap', 'text-max-width': '80px', 'shape': 'ellipse', 'transition-property': 'background-color, border-color, border-width, width, height, opacity',
                'transition-duration': '0.2s', 'opacity': 1, 'min-zoomed-font-size': 8 } },
            { selector: 'edge', style: { 'width': 1.5, 'line-color': edgeColor, 'target-arrow-color': edgeColor, 'target-arrow-shape': 'triangle', 'curve-style': 'bezier', 'transition-property': 'line-color, target-arrow-color, opacity', 'transition-duration': '0.2s', 'opacity': 1 } },
            { selector: 'node:selected', style: { 'border-color': selectedColor, 'border-width': 4 } },
            { selector: '.highlighted', style: { 'overlay-color': highlightColor, 'overlay-padding': 8, 'overlay-opacity': 0.25 } },
            { selector: '.dimmed', style: { 'opacity': 0.15 } },
            { selector: '.search-match', style: { 'outline-color': highlightColor, 'outline-width': 3, 'outline-offset': 3 } },
            { selector: '.hidden', style: { 'display': 'none' } },
            { selector: '.grabbing', style: { /* Optional: 'border-style': 'dashed', 'border-color': selectedColor */ } } // Style for grabbed node
        ];
    };

    // --- Cytoscape Initialization & Data Loading ---
    const layoutOptions = { dagre: { name: 'dagre', rankDir: currentRankDir, spacingFactor: 1.2, fit: true, padding: 30, animate: true, animationDuration: 500 } };

    function initializeCytoscape(elements) {
        console.log("Attempting to initialize Cytoscape...");
        if (cy) { console.log("Destroying previous Cytoscape instance."); destroyTooltips(); cy.destroy(); cy = null; }
        if (!networkContainer) { console.error("FATAL: Network container div (#network) not found!"); showToast("Error: Visualization container missing.", "error", 10000); hideLoading(); return; }
        if (!elements || elements.length === 0) { console.warn("Initializing Cytoscape with zero elements."); }
        else { console.log(`Initializing Cytoscape with ${elements.filter(e=>e.group === 'nodes').length} nodes and ${elements.filter(e=>e.group === 'edges').length} edges.`); }

        try {
            cy = cytoscape({
                container: networkContainer, elements: elements,
                layout: { name: 'preset' }, // Use preset initially
                zoom: 1, minZoom: 0.1, maxZoom: 3.0,
                wheelSensitivity: 0.35, // Increased sensitivity
                boxSelectionEnabled: true, autounselectify: false, autoungrabify: false,
            });
            console.log("Applying Cytoscape style...");
            cy.style(getCytoscapeStyle(currentTheme));
            console.log("Setting up Cytoscape event listeners...");
            setupCytoscapeEventListeners();
            console.log("Setting up context menu...");
            setupContextMenu();
            console.log("Setting up tooltips...");
            setupTooltips();
            cy.ready(() => { // Run layout after setup
                console.log("Cytoscape ready. Running initial layout.");
                if (cy.elements().length > 0) { cy.layout(layoutOptions.dagre).run(); }
                else { console.warn("Cytoscape ready, but no elements to display."); }
            });
        } catch (error) {
            console.error("FATAL: Cytoscape initialization failed:", error);
            showToast(`Error initializing visualization: ${error.message}`, "error", 10000);
            networkContainer.innerHTML = `<div class="p-4 text-center theme-danger">Failed... ${error.message}</div>`;
        } finally {
            hideLoading();
        }
    }

    function transformDataForCytoscape(data) {
        console.log("Transforming data for Cytoscape...");
        const elements = []; networkDataCache = data;
        if (!data || !data.nodes || typeof data.nodes !== 'object') { console.error("Invalid 'nodes' data."); return elements; }
        dataStats = calculateDataStats(data.nodes); // Calculate stats for styling
        console.log(`Transforming ${Object.keys(data.nodes).length} nodes.`);
        for (const nodeId in data.nodes) { const node = data.nodes[nodeId]; if (node && node.id) { elements.push({ group: 'nodes', data: { id: node.id, ...node } }); } else { console.warn(`Skipping invalid node data: ${nodeId}`); } }
        let edgeCount = 0;
        if (data.graph && typeof data.graph === 'object') {
             console.log(`Transforming edges.`);
             for (const parentId in data.graph) { const children = data.graph[parentId]; if (Array.isArray(children)) { children.forEach(([childId, capacity]) => { if (data.nodes[parentId] && data.nodes[childId]) { elements.push({ group: 'edges', data: { id: `${parentId}->${childId}`, source: parentId, target: childId, capacity: capacity ?? 1.0 } }); edgeCount++; } else { /* console.warn(`Skipping edge: ${parentId} -> ${childId} (Node missing)`); */ } }); } }
        } else { console.warn("Missing or invalid 'graph' data."); }
        console.log(`Transformation complete: ${elements.filter(e=>e.group === 'nodes').length} nodes, ${edgeCount} edges.`);
        return elements;
    }

    async function loadAndRenderNetwork() {
        console.log("Loading and rendering network...");
        showLoading(); selectedNodeId = null; isSubtreeIsolated = false;
        updateNodeDetails(null); updateIsolateButtons(null);
        try {
            const data = await apiCall(NETWORK_ENDPOINT); console.log("API data received:", data);
            const elements = transformDataForCytoscape(data); console.log("Elements transformed:", elements.length);
            initializeCytoscape(elements);
            if (data.settings) { minChildrenInput.value = data.settings.min_children_threshold ?? 2; balanceFactorInput.value = data.settings.balance_factor ?? 0.75; }
            loadSuggestions();
        } catch (error) { console.error("Failed to load network data:", error); initializeCytoscape([]); }
    }

    async function refreshVisualization(runLayout = true) {
        console.log("Refreshing visualization...");
        if (!cy) { console.warn("Refresh called but Cytoscape not initialized."); return; }
        showLoading();
        try {
            const data = await apiCall(NETWORK_ENDPOINT);
            const elements = transformDataForCytoscape(data);
            const lastSelectedId = selectedNodeId;

            console.log("Updating Cytoscape elements using cy.json()...");
            cy.json({ elements: elements });

            console.log("Applying style and layout...");
            cy.style(getCytoscapeStyle(currentTheme));

            const layoutPromise = runLayout ? cy.layout(layoutOptions.dagre).run().promiseOn('layoutstop') : Promise.resolve();
            layoutPromise.then(() => { console.log("Layout complete (or skipped). Finalizing refresh..."); finalizeRefresh(lastSelectedId); });

            if (data.settings) { minChildrenInput.value = data.settings.min_children_threshold ?? 2; balanceFactorInput.value = data.settings.balance_factor ?? 0.75; }
            loadSuggestions();

        } catch (error) { console.error("Failed to refresh network:", error); hideLoading(); }
    }

    function finalizeRefresh(lastSelectedId) {
        console.log("Finalizing refresh...");
        if (!cy) return;
        setupTooltips(); // Refresh tooltips
        handleSearch(searchInput.value, false); // Re-apply search without fit
        if(isSubtreeIsolated && lastSelectedId && cy.getElementById(lastSelectedId)?.length > 0) { isolateSubtree(lastSelectedId, false); } // Re-apply isolate without fit
        else { showAllNodes(false); } // Ensure full network if isolate invalid, no fit
        selectedNodeId = null; updateNodeDetails(null); // Reset selection
        if(lastSelectedId && cy.getElementById(lastSelectedId)?.length > 0) { const node = cy.getElementById(lastSelectedId); node.select(); console.log(`Restored selection: ${lastSelectedId}`); updateIsolateButtons(lastSelectedId); } // Restore selection & update buttons
        else { updateIsolateButtons(null); }
        console.log("Refresh finalization complete.");
        hideLoading();
    }

    // --- UI Update Functions ---
    function updateNodeDetails(nodeData) { // (Same logic as previous version)
        if (!nodeData) { nodeStatsContainer.innerHTML = '<p class="theme-text-muted italic">Click node...</p>'; nodeDetailsPanel.classList.add('hidden'); deleteNodeBtn.disabled = true; deleteNodeMsg.textContent = 'Select leaf node.'; selectedNodeId = null; updateIsolateButtons(null); return; }
        nodeDetailsPanel.classList.remove('hidden'); selectedNodeId = nodeData.id;
        const isLeaf = cy && cy.getElementById(nodeData.id)?.outgoers()?.nodes()?.length === 0;
        let detailsHtml = `<p><strong>ID:</strong> <span class="break-all">${nodeData.id}</span></p>`;
        const formatNum = (v, d = 2) => (v !== undefined && v !== null) ? parseFloat(v).toFixed(d) : 'N/A';
        const detailsMap = [
             { label: 'Node Value', value: formatNum(nodeData.value, 2) }, { label: 'Profit (Children Value)', value: formatNum(nodeData.profit, 2) }, { label: 'Depth', value: nodeData.depth ?? 'N/A' },
             { label: 'Direct Children', value: nodeData.children_count ?? 'N/A' }, { label: 'Total Descendants', value: nodeData.total_children ?? 'N/A' }, { label: 'Criticality', value: formatNum(nodeData.criticality, 3), highlight: nodeData.criticality > 0 },
             { label: 'Needed Children', value: nodeData.needed_children ?? 'N/A', highlight: nodeData.needed_children > 0 }, { label: 'Suggested Children', value: nodeData.suggested_child_count ?? 'N/A' },
             { label: 'Subtree Balance', value: formatNum(nodeData.balance_score, 3) }, { label: 'Is Chokepoint', value: nodeData.is_chokepoint ? 'Yes' : 'No', highlight: nodeData.is_chokepoint }, ];
        detailsMap.forEach(item => { const vC = item.highlight ? 'theme-warning font-bold' : ''; detailsHtml += `<p><strong>${item.label}:</strong> <span class="${vC}">${item.value}</span></p>`; });
        const parents = nodeData.parents ?? []; const children = nodeData.children ?? [];
        detailsHtml += `<p><strong>Parents:</strong> ${parents.length > 0 ? parents.join(', ') : '(Root)'}</p>`; detailsHtml += `<p><strong>Direct Children:</strong> ${children.length > 0 ? children.join(', ') : '(None)'}</p>`;
        const knownKeys = ['id', 'value', 'depth', 'children_count', 'total_children', 'profit', 'criticality', 'is_chokepoint', 'needed_children', 'suggested_children', 'balance_score', 'parents', 'children', 'risk', 'ponzi_value', 'position', 'selected', 'selectable', 'locked', 'grabbable', 'classes'];
        const customProps = Object.entries(nodeData).filter(([key]) => !knownKeys.includes(key) && !key.startsWith('_'));
        if (customProps.length > 0) { detailsHtml += '<p class="mt-2 pt-2 border-t theme-border"><strong>Custom Properties:</strong></p>'; customProps.forEach(([key, value]) => { detailsHtml += `<p><span class="italic theme-text-secondary">${key}:</span> ${value}</p>`; }); }
        nodeStatsContainer.innerHTML = detailsHtml;
        deleteNodeBtn.disabled = !isLeaf; deleteNodeMsg.textContent = isLeaf ? 'Node can be deleted.' : 'Cannot delete with children.'; updateIsolateButtons(nodeData.id);
    }
    async function loadSuggestions() { // (Same logic as previous version)
        suggestionsPanel.classList.remove('hidden'); suggestionsList.innerHTML = '<p class="text-xs italic theme-text-muted">Loading...</p>';
        try {
            const data = await apiCall(SUGGESTIONS_ENDPOINT + '?limit=7');
            if (data.suggestions && data.suggestions.length > 0) {
                suggestionsList.innerHTML = data.suggestions.map(s => `<div class="suggestion-item theme-bg-primary p-2 rounded border theme-border cursor-pointer hover:shadow-md" data-node-id="${s.id}"><div class="flex justify-between items-center text-xs"><span class="font-semibold theme-text-primary truncate" title="${s.id}">${s.id}</span><span class="theme-danger font-medium ml-2 flex-shrink-0">Needs ${s.needed_children}</span></div><div class="text-xs theme-text-secondary mt-1">Crit: ${s.criticality?.toFixed(2)} | Depth: ${s.depth} | Bal: ${s.balance_score?.toFixed(2)}</div></div>`).join('');
                suggestionsList.querySelectorAll('.suggestion-item').forEach(item => { item.addEventListener('click', () => { const nodeId = item.getAttribute('data-node-id'); if (cy) { const node = cy.getElementById(nodeId); if (node && !node.empty()) { cy.elements().removeClass('highlighted'); node.addClass('highlighted'); cy.animate({ center: { eles: node }, zoom: Math.max(cy.zoom(), 1.2) }, { duration: 500 }); } } }); });
            } else { suggestionsList.innerHTML = '<p class="text-xs italic theme-text-muted">Network looks balanced!</p>'; }
        } catch (error) { suggestionsList.innerHTML = '<p class="text-xs theme-danger">Load failed.</p>'; }
    }
    function applyTheme(theme) { // (Same logic as previous version)
        currentTheme = theme; document.documentElement.classList.remove('light', 'dark'); document.documentElement.classList.add(theme); localStorage.setItem('theme', theme);
        themeIconMoon.classList.toggle('hidden', theme === 'dark'); themeIconSun.classList.toggle('hidden', theme === 'light');
        if (cy) { destroyTooltips(); cy.style(getCytoscapeStyle(theme)); setupTooltips(); }
    }
    function toggleLayoutDirection() { // (Same logic as previous version)
        currentRankDir = currentRankDir === 'TB' ? 'LR' : 'TB'; layoutOptions.dagre.rankDir = currentRankDir;
        layoutToggleText.textContent = currentRankDir === 'TB' ? 'Vertical Layout' : 'Horizontal Layout'; layoutToggleIcon.className = `fas ${currentRankDir === 'TB' ? 'fa-arrow-down' : 'fa-arrow-right'} mr-2`;
        if (cy) { cy.layout(layoutOptions.dagre).run(); }
    }

    // --- Tooltips & Context Menu Setup ---
    function setupTooltips() { // (Same logic as previous version - content updated)
        if (!cy) return; destroyTooltips();
        cy.nodes().forEach(node => {
            const d = node.data(); const c = `<strong>${d.id}</strong><br>Value: ${d.value?.toFixed(0)??'N/A'}<br>Profit: ${d.profit?.toFixed(0)??'N/A'}<br>Crit: ${d.criticality?.toFixed(2)??'N/A'} | Bal: ${d.balance_score?.toFixed(2)??'N/A'}`;
            const r = node.popperRef(); const t = tippy(document.createElement('div'), { getReferenceClientRect: r.getBoundingClientRect, trigger: 'manual', content: c, allowHTML: true, arrow: true, placement: 'top', hideOnClick: false, interactive: false, appendTo: document.body, theme: 'light-border', });
            tippyInstances.push(t); node.on('mouseover', () => t.show()); node.on('mouseout', () => t.hide()); node.on('position', () => t.popperInstance?.update()); });
        cy.on('zoom pan', debounce(() => tippyInstances.forEach(tip => tip.hide()), 50));
    }
    function destroyTooltips() { tippyInstances.forEach(instance => instance?.destroy()); tippyInstances = []; }
    function setupContextMenu() { // (Same logic as previous version)
        if (!cy || !cy.contextMenus) { console.warn("Ctx menu setup skipped."); return; } if (cy.contextMenusInstance) cy.contextMenusInstance.destroy();
        cy.contextMenusInstance = cy.contextMenus({ menuItems: [ { id: 'view-details', content: '<i class="fas fa-info-circle fa-fw mr-2"></i> Details', selector: 'node', onClickFunction: (e) => { const n = e.target || e.cyTarget; n.select();} }, { id: 'add-child', content: '<i class="fas fa-plus-circle fa-fw mr-2"></i> Add Child', selector: 'node', onClickFunction: (e) => { openAddChildModal((e.target || e.cyTarget).id()); } }, { id: 'isolate', content: '<i class="fas fa-sitemap fa-fw mr-2"></i> Isolate', selector: 'node', onClickFunction: (e) => { const n = e.target || e.cyTarget; isolateSubtree(n.id(), true); n.select(); } }, { id: 'center-node', content: '<i class="fas fa-crosshairs fa-fw mr-2"></i> Center', selector: 'node', onClickFunction: (e) => { const n = e.target || e.cyTarget; cy.animate({ center: { eles: n }, zoom: Math.max(cy.zoom(), 1.0) }, { duration: 400 }); } }, { id: 'delete-node', content: '<i class="fas fa-trash-alt fa-fw mr-2 theme-danger"></i> Delete', selector: 'node', enabled: (ele) => ele.outgoers().nodes().length === 0, onClickFunction: (e) => { const n = e.target || e.cyTarget; if (confirm(`Delete "${n.id()}"?`)) handleDeleteNode(n.id()); } } ] });
    }
    function openAddChildModal(parentId) { // (Same logic as previous version)
        document.getElementById('nearbyParentId').value = parentId; document.getElementById('modalParentNodeId').textContent = parentId;
        document.getElementById('nearbyNodeId').value = ''; document.getElementById('nearbyNodeValue').value = '';
        addNodeModal.classList.remove('hidden'); document.getElementById('nearbyNodeId').focus();
    }

    // --- Action Handlers (API interactions) ---
    async function handleAddNode(formData) { // (Same logic as previous version)
        const payload = { id: formData.get('id') || null, parent_id: formData.get('parent_id') || null, value: formData.get('value') };
        try { const result = await apiCall(NODES_ENDPOINT, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) }); if (result.status === 'success') { showToast(`Node "${result.id}" added.`, 'success'); await refreshVisualization(true); addNodeForm.reset(); if (!addNodeModal.classList.contains('hidden')) { addNodeModal.classList.add('hidden'); addNodeNearbyForm.reset(); } } } catch (error) { /* Handled by apiCall */ } }
    async function handleDeleteNode(nodeId) { // (Same logic as previous version)
        if (!nodeId) return; try { await apiCall(`${NODES_ENDPOINT}/${nodeId}`, { method: 'DELETE' }); showToast(`Node "${nodeId}" deleted.`, 'success'); await refreshVisualization(true); } catch (error) { /* Handled by apiCall */ } }
    async function handleUpdateSettings(event) { // (Same logic as previous version)
        event.preventDefault(); const payload = { min_children_threshold: parseInt(minChildrenInput.value, 10), balance_factor: parseFloat(balanceFactorInput.value), }; try { const result = await apiCall(SETTINGS_ENDPOINT, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) }); if (result.status === 'success') { showToast('Settings updated.', 'success'); await refreshVisualization(true); } } catch (error) { /* Handled by apiCall */ } }
    async function handleImport(event) { // (Same logic as previous version)
        const file = event.target.files[0]; if (!file || file.type !== 'application/json') { showToast('Select JSON file.', 'error'); return; } const formData = new FormData(); formData.append('file', file); showToast('Importing network...', 'info', 5000); try { const result = await apiCall(IMPORT_ENDPOINT, { method: 'POST', body: formData }); if (result.success) { showToast('Imported.', 'success'); await loadAndRenderNetwork(); } } catch (error) { /* Handled by apiCall */ } finally { event.target.value = null; } }
    async function handleExport() { // (Same logic as previous version)
        try { const blob = await apiCall(EXPORT_ENDPOINT, { responseType: 'blob' }); const url = window.URL.createObjectURL(blob); const a = document.createElement('a'); a.style.display = 'none'; a.href = url; const timestamp = new Date().toISOString().replace(/[:.]/g, '-'); a.download = `network_export_${timestamp}.json`; document.body.appendChild(a); a.click(); window.URL.revokeObjectURL(url); document.body.removeChild(a); showToast('Exported.', 'success'); } catch (error) { /* Handled by apiCall */ } }

    // --- Feature Handlers: Search, Isolate, Dragging ---
    const handleSearch = debounce((searchTerm, fitView = false) => { // (Same logic as previous version)
        console.log(`Searching for: "${searchTerm}"`); if (!cy) return; const term = searchTerm.trim().toLowerCase();
        cy.batch(() => { cy.elements().removeClass('dimmed search-match'); searchClearBtn.classList.toggle('hidden', !term); if (!term) return; const matchedNodes = cy.nodes().filter(node => node.id().toLowerCase().includes(term)); console.log(`Found ${matchedNodes.length} matches.`); if (matchedNodes.length > 0) { const elementsToConsider = isSubtreeIsolated ? cy.elements().not('.hidden') : cy.elements(); const neighborhood = matchedNodes.union(matchedNodes.connectedEdges()); const nonMatched = elementsToConsider.not(neighborhood); nonMatched.addClass('dimmed'); matchedNodes.addClass('search-match'); if (fitView && matchedNodes.length < 20) { console.log("Fitting view to search."); cy.animate({ fit: { eles: matchedNodes, padding: 50 } }, { duration: 400 }); } } else { console.log("No matches, dimming."); const elementsToConsider = isSubtreeIsolated ? cy.elements().not('.hidden') : cy.elements(); elementsToConsider.addClass('dimmed'); if (fitView) showToast('No matches found.', 'info', 1500); } }); }, 300);

    function isolateSubtree(nodeId, fitView = true) { // (Same logic as previous version)
        console.log(`Isolating subtree for: ${nodeId}`); if (!cy || !nodeId) return; const node = cy.getElementById(nodeId); if (node.empty()) { console.error("Node not found."); showToast("Node not found.", "error"); return; } const subtree = node.union(node.successors()); console.log(`Subtree: ${subtree.nodes().length} nodes, ${subtree.edges().length} edges.`); cy.batch(() => { cy.elements().not(subtree).addClass('hidden'); subtree.removeClass('hidden dimmed search-match'); }); isSubtreeIsolated = true; updateIsolateButtons(nodeId); handleSearch(searchInput.value, false); if (fitView) { console.log("Fitting view to isolate."); cy.animate({ fit: { eles: subtree, padding: 50 } }, { duration: 400 }); } }
    function showAllNodes(fitView = true) { // (Same logic as previous version)
        console.log("Showing all nodes."); if (!cy) return; cy.batch(() => { cy.elements().removeClass('hidden'); }); isSubtreeIsolated = false; updateIsolateButtons(selectedNodeId); handleSearch(searchInput.value, false); if (fitView) { console.log("Fitting view to all."); cy.animate({ fit: { padding: 30 } }, { duration: 400 }); } }
    function updateIsolateButtons(currentSelectedNodeId) { // (Same logic as previous version)
        const nodeSelected = currentSelectedNodeId && cy && cy.getElementById(currentSelectedNodeId)?.length > 0; isolateSubtreeBtn.classList.toggle('hidden', !nodeSelected || isSubtreeIsolated); showAllBtn.classList.toggle('hidden', !isSubtreeIsolated); }

    // --- Cytoscape Event Listeners Setup ---
    function setupCytoscapeEventListeners() {
        if (!cy) return;
        console.log("Setting up Cytoscape listeners...");
        // Selection
        cy.on('select', 'node', (e) => updateNodeDetails(e.target.data()));
        cy.on('unselect', 'node', (e) => { setTimeout(() => { if (cy && !cy.$('node:selected').length) updateNodeDetails(null); }, 0); });
        cy.on('tap', (e) => { if (e.target === cy && cy.$(':selected').length) cy.$(':selected').unselect(); });

        // Dragging Subtree
        cy.on('grab', 'node', (e) => {
            const node = e.target;
            console.log(`Grabbing node: ${node.id()}`);
            draggedNodeInfo = { node: node, subtreeNodes: node.successors().nodes(), initialPosition: { ...node.position() } };
            node.addClass('grabbing');
            // Store initial positions of subtree for relative drag calculation
            node.scratch('_initialDragPos', { ...node.position() });
            draggedNodeInfo.subtreeNodes.forEach(n => n.scratch('_initialDragPos', { ...n.position() }));
            networkContainer.classList.add('grabbing'); // Add grabbing cursor to container
        });
        cy.on('drag', 'node', (e) => {
            if (!draggedNodeInfo || e.target !== draggedNodeInfo.node) return;
            const pos = e.target.position();
            const initialPos = draggedNodeInfo.node.scratch('_initialDragPos'); // Use stored initial pos
            if(!initialPos) return; // Should not happen if grab worked
            const dx = pos.x - initialPos.x;
            const dy = pos.y - initialPos.y;

            if (draggedNodeInfo.subtreeNodes.length > 0) {
                 cy.batch(() => { // Batch moves for performance
                    draggedNodeInfo.subtreeNodes.forEach(descendant => {
                        const initialDescendantPos = descendant.scratch('_initialDragPos');
                        if (initialDescendantPos) { descendant.position({ x: initialDescendantPos.x + dx, y: initialDescendantPos.y + dy }); }
                        // No fallback needed as initial pos is stored on grab now
                    });
                 });
            }
        });
        cy.on('free', 'node', (e) => {
            if (draggedNodeInfo && e.target === draggedNodeInfo.node) {
                console.log(`Freed node: ${draggedNodeInfo.node.id()}`);
                draggedNodeInfo.node.removeClass('grabbing');
                // Clear scratch data
                draggedNodeInfo.node.removeScratch('_initialDragPos');
                draggedNodeInfo.subtreeNodes.forEach(n => n.removeScratch('_initialDragPos'));
                draggedNodeInfo = null; // Clear drag state
                networkContainer.classList.remove('grabbing'); // Remove grabbing cursor
                // Layout is NOT reapplied automatically
            }
        });
        console.log("Cytoscape listeners set up.");
    }

    // --- Initial Setup & Load ---
    console.log("DOM Loaded. Starting setup.");
    applyTheme(currentTheme);
    // Attach UI Event Listeners
    themeToggleBtn.addEventListener('click', () => applyTheme(currentTheme === 'light' ? 'dark' : 'light'));
    layoutToggleBtn.addEventListener('click', toggleLayoutDirection);
    addNodeForm.addEventListener('submit', (e) => { e.preventDefault(); handleAddNode(new FormData(addNodeForm)); });
    addNodeNearbyForm.addEventListener('submit', (e) => { e.preventDefault(); handleAddNode(new FormData(addNodeNearbyForm)); });
    closeModalBtn.addEventListener('click', () => addNodeModal.classList.add('hidden'));
    deleteNodeBtn.addEventListener('click', () => { if (selectedNodeId && !deleteNodeBtn.disabled && confirm(`Delete node "${selectedNodeId}"?`)) handleDeleteNode(selectedNodeId); });
    settingsForm.addEventListener('submit', handleUpdateSettings);
    refreshSuggestionsBtn.addEventListener('click', loadSuggestions);
    importFileInput.addEventListener('change', handleImport);
    exportBtn.addEventListener('click', handleExport);
    centerNetworkBtn.addEventListener('click', () => cy?.animate({ fit: { padding: 30 } }, { duration: 400 }));
    zoomInBtn.addEventListener('click', () => cy?.zoom(cy.zoom() * 1.2));
    zoomOutBtn.addEventListener('click', () => cy?.zoom(cy.zoom() / 1.2));
    searchInput.addEventListener('input', (e) => handleSearch(e.target.value, true));
    searchClearBtn.addEventListener('click', () => { searchInput.value = ''; handleSearch('', true); });
    isolateSubtreeBtn.addEventListener('click', () => { if (selectedNodeId) isolateSubtree(selectedNodeId, true); });
    showAllBtn.addEventListener('click', () => showAllNodes(true));
    reapplyLayoutBtn.addEventListener('click', () => { if (cy) { console.log("Re-applying layout via button..."); showAllNodes(false); cy.layout(layoutOptions.dagre).run(); } }); // Re-run layout button

    // Initial Data Load
    loadAndRenderNetwork();
    console.log("Initial load sequence initiated.");

}); // End DOMContentLoaded
// --- END OF FILE static/js/network.js ---