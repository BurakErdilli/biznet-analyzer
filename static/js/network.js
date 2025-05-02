/* static/js/network.js */

class NetworkVisualizer {
    constructor(containerId) {
        this.container = d3.select(`#${containerId}`);
        if (this.container.empty()) {
            console.error(`Container element with ID "${containerId}" not found.`);
            return;
        }
        this.width = this.container.node().getBoundingClientRect().width;
        this.height = 600; // Fixed height for the SVG container
        this.selectedNode = null;
        this.contextNode = null; // Node associated with the context menu
        this.zoomLevel = 1;
        this.transform = d3.zoomIdentity;
        this.tooltip = d3.select('#tooltip');
        this.contextMenu = d3.select('#contextMenu');
        this.addNodeModal = d3.select('#addNodeModal');
        this.nodeDetailsPanel = d3.select('#nodeDetails');
        this.nodeStatsContainer = d3.select('#nodeStats');
        this.deleteNodeBtn = d3.select('#deleteNodeBtn');
        this.suggestionsPanel = d3.select('#suggestionsPanel');
        this.suggestionsList = d3.select('#suggestionsList');
        this.data = null; // Store the raw network data
        this.settings = {
            minChildrenThreshold: 2,
            balanceFactor: 0.75,
            maxDepth: 0
        };
        this.margin = { top: 30, right: 90, bottom: 30, left: 90 }; // Adjusted margins for better fit
        this.useHorizontalLayout = false; // Default to vertical layout

        this.updateTreeLayout();
        this.initializeSVG();
        this.setupEventListeners();
        this.loadThemePreference(); // Load theme preference on init
    }

    updateTreeLayout() {
        const innerWidth = this.width - this.margin.left - this.margin.right;
        const innerHeight = this.height - this.margin.top - this.margin.bottom;

        if (this.useHorizontalLayout) {
            // Horizontal layout (left to right)
            this.treeLayout = d3.tree().size([innerHeight, innerWidth]);
        } else {
            // Vertical layout (top to bottom)
            this.treeLayout = d3.tree().size([innerWidth, innerHeight]);
        }
        // Optional: Adjust separation dynamically if needed
        // this.treeLayout.separation((a, b) => (a.parent == b.parent ? 1 : 1.5) / (a.depth + 1));
    }

    initializeSVG() {
        this.svg = this.container
            .append("svg")
            .attr("viewBox", [0, 0, this.width, this.height])
            .attr("width", "100%")
            .attr("height", "100%")
            .style("cursor", "grab")
            .on('contextmenu', (event) => {
                event.preventDefault(); // Prevent default browser context menu on SVG background
            });

        this.g = this.svg.append("g");
           // Removed transform here, applied by zoom later

        // Add zoom behavior
        this.zoom = d3.zoom()
            .extent([[0, 0], [this.width, this.height]])
            .scaleExtent([0.1, 3]) // Adjusted scale extent
            .on("zoom", ({ transform }) => {
                this.transform = transform;
                // Apply transform to the group 'g', considering margins
                this.g.attr("transform", `translate(${transform.x + this.margin.left},${transform.y + this.margin.top}) scale(${transform.k})`);
                this.zoomLevel = transform.k;
            });

        this.svg.call(this.zoom);

         // Apply initial transform to center the content slightly
        this.svg.call(this.zoom.transform, d3.zoomIdentity.translate(this.margin.left, this.margin.top));
    }

    setupEventListeners() {
        // Theme toggle
        d3.select('#themeToggle').on('click', () => {
            const html = document.documentElement;
            const isDark = html.classList.toggle('dark');
            html.classList.toggle('light', !isDark);
            localStorage.setItem('theme', isDark ? 'dark' : 'light');
            this.updateThemeToggleButton(isDark);
            this.redrawVisualization(); // Redraw to apply new theme colors
        });

        // Layout toggle
        d3.select('#layoutToggle').on('click', () => {
            this.useHorizontalLayout = !this.useHorizontalLayout;
            d3.select('#layoutToggle').html(
                this.useHorizontalLayout
                    ? '<i class="fas fa-arrow-down mr-2"></i> Vertical Layout'
                    : '<i class="fas fa-arrow-right mr-2"></i> Horizontal Layout'
            );
            this.updateTreeLayout();
            if (this.data) { // Only update if data exists
                 this.update(this.data);
            }
        });

        // Suggestions refresh
        d3.select('#refreshSuggestions').on('click', () => {
            this.loadSuggestions();
        });

        // Import/Export buttons
        d3.select('#importFile').on('change', (event) => {
            const file = event.target.files[0];
            if (file) {
                this.importNetwork(file);
                event.target.value = null; // Reset file input
            }
        });

        d3.select('#exportBtn').on('click', () => {
            this.exportNetwork();
        });

        // Settings form
        d3.select('#settingsForm').on('submit', (event) => {
            event.preventDefault();
            const threshold = parseInt(d3.select('#minChildrenThreshold').property('value'));
            const balance = parseFloat(d3.select('#balanceFactor').property('value'));
            if (!isNaN(threshold) && !isNaN(balance)) {
                this.updateSettings({
                    min_children_threshold: threshold,
                    balance_factor: balance
                });
            } else {
                 alert("Invalid settings values.");
            }
        });

        // Center network button
        d3.select('#centerNetworkBtn').on('click', () => {
            this.svg.transition().duration(750).call(
                this.zoom.transform,
                d3.zoomIdentity.translate(this.margin.left, this.margin.top) // Reset to initial centered view
            );
        });

        // Zoom buttons
        d3.select('#zoomInBtn').on('click', () => {
            this.svg.transition().duration(300).call(this.zoom.scaleBy, 1.3);
        });

        d3.select('#zoomOutBtn').on('click', () => {
            this.svg.transition().duration(300).call(this.zoom.scaleBy, 1 / 1.3); // Correct zoom out factor
        });

        // Delete node button (in details panel)
        this.deleteNodeBtn.on('click', () => {
            if (this.selectedNode) {
                this.deleteNode(this.selectedNode.id);
            }
        });

        // Context menu items
        d3.select('#addNodeNearby').on('click', () => {
            if (this.contextNode) {
                const modalForm = d3.select('#addNodeNearbyForm');
                modalForm.select('#nearbyParentId').property('value', this.contextNode.id);
                // X and Y are not directly needed for API but can be stored if useful
                // modalForm.select('#nearbyX').property('value', this.contextNode.x);
                // modalForm.select('#nearbyY').property('value', this.contextNode.y);
                this.addNodeModal.classed('hidden', false);
            }
            this.hideContextMenu();
        });

        d3.select('#deleteNode').on('click', () => { // Context menu delete
            if (this.contextNode) {
                this.deleteNode(this.contextNode.id);
            }
            this.hideContextMenu();
        });

        // Modal close button
        d3.select('#closeModal').on('click', () => {
            this.addNodeModal.classed('hidden', true);
        });

        // Add node nearby form submission
        d3.select('#addNodeNearbyForm').on('submit', (event) => {
            event.preventDefault();
            const form = event.currentTarget;
            const formData = new FormData(form);
            const data = Object.fromEntries(formData.entries()); // Use .entries() for FormData

            // Remove empty optional fields
             if (!data.id) delete data.id;

            this.addNodeNearby(data);
            this.addNodeModal.classed('hidden', true);
            form.reset();
        });

        // Hide context menu on document click
        document.addEventListener('click', (event) => {
            // Check if the click is outside the context menu itself
            if (!this.contextMenu.node().contains(event.target)) {
                 this.hideContextMenu();
            }
        });

        // Hide tooltip when mouse leaves the SVG container
        this.svg.on('mouseleave', () => {
            this.hideTooltip();
        });
    }

    loadThemePreference() {
        const savedTheme = localStorage.getItem('theme');
        const prefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
        const isDark = savedTheme === 'dark' || (savedTheme === null && prefersDark);

        document.documentElement.classList.toggle('dark', isDark);
        document.documentElement.classList.toggle('light', !isDark);
        this.updateThemeToggleButton(isDark);
    }

    updateThemeToggleButton(isDark) {
        const toggleButton = d3.select('#themeToggle');
        toggleButton.select('.fa-moon').classed('hidden', isDark);
        toggleButton.select('.fa-sun').classed('hidden', !isDark);
    }

     redrawVisualization() {
        if (this.data) {
            this.update(this.data);
        }
    }

    update(data) {
        this.data = data; // Store the raw data

        // Update settings if available
        if (data.settings) {
            this.settings.minChildrenThreshold = data.settings.min_children_threshold ?? 2;
            this.settings.balanceFactor = data.settings.balance_factor ?? 0.75;
            this.settings.maxDepth = data.settings.max_depth ?? 0;

            // Update input fields in the settings form
            d3.select('#minChildrenThreshold').property('value', this.settings.minChildrenThreshold);
            d3.select('#balanceFactor').property('value', this.settings.balanceFactor);
        } else {
             // Reset to defaults if not provided
             this.settings.minChildrenThreshold = 2;
             this.settings.balanceFactor = 0.75;
             this.settings.maxDepth = 0;
             d3.select('#minChildrenThreshold').property('value', 2);
             d3.select('#balanceFactor').property('value', 0.75);
        }

        // Convert flat data to hierarchical data for tree layout
        const hierarchicalData = this.buildHierarchicalData(data);
        if (!hierarchicalData) {
             console.error("Failed to build hierarchical data. No root node found?");
             this.g.selectAll("*").remove(); // Clear visualization if data is invalid
             return;
        }

        // Render the tree
        this.renderTree(hierarchicalData);

        // Load suggestions panel content
        this.loadSuggestions();

         // If a node was selected, try to re-select it and update details
         if (this.selectedNode) {
             const reselectedNodeData = this.findNodeById(this.selectedNode.id);
             if (reselectedNodeData) {
                 this.selectNode(reselectedNodeData, false); // Re-select without recentering
             } else {
                 // Node was deleted or data changed, clear selection
                 this.selectedNode = null;
                 this.nodeDetailsPanel.classed("hidden", true);
             }
         }
    }

    buildHierarchicalData(data) {
        if (!data || !data.nodes || Object.keys(data.nodes).length === 0) {
            // Handle empty data case: return a single dummy root or null
            // This prevents errors if the network is initially empty.
            return { id: "root", name: "No Network Data", children: [], data: { id: "root" } };
        }

        const nodes = data.nodes;
        const graph = data.graph || {};
        const nodeMap = new Map(Object.entries(nodes));
        const childrenMap = new Map();

        // Build children map from graph data
        Object.entries(graph).forEach(([parentId, edges]) => {
             childrenMap.set(parentId, edges.map(([childId]) => childId));
        });


        // Find the root node(s)
        const rootIds = Object.keys(nodes).filter(nodeId =>
            !nodes[nodeId].parents || nodes[nodeId].parents.length === 0
        );


        if (rootIds.length === 0) {
             // If no explicit root (e.g., circular refs or orphaned nodes),
             // try picking an arbitrary node or return null/error
             console.warn("No root node found. Network might be empty or improperly structured.");
             // As a fallback, let's pick the first node if available
             const firstNodeId = Object.keys(nodes)[0];
             if (firstNodeId) {
                 console.warn(`Using node "${firstNodeId}" as a fallback root.`);
                 rootIds.push(firstNodeId);
             } else {
                 return { id: "root", name: "Empty Network", children: [], data: { id: "root" } }; // Handle truly empty case
             }
        }

        // Recursive function to build the tree structure
        const buildTree = (nodeId) => {
             const nodeData = nodeMap.get(nodeId);
             if (!nodeData) return null; // Skip if node data doesn't exist (data integrity issue)

             const childrenIds = childrenMap.get(nodeId) || [];
             const children = childrenIds
                 .map(childId => buildTree(childId))
                 .filter(child => child !== null); // Filter out null children

             // Return the node structure expected by d3.hierarchy
             return {
                 id: nodeId, // Keep id for easy reference
                 // name: nodeId, // Optional: Use 'name' if you prefer for labels
                 data: nodeData, // Store the original node data here
                 children: children.length > 0 ? children : undefined // Use undefined for leaf nodes
             };
        };


        if (rootIds.length === 1) {
            // Single root case
            return buildTree(rootIds[0]);
        } else {
            // Multiple roots: create a virtual root
            console.warn("Multiple root nodes found. Creating a virtual root.");
            const virtualRoot = {
                id: "virtual_root",
                // name: "Network Roots",
                data: { id: "virtual_root", isVirtual: true }, // Mark as virtual
                children: rootIds.map(rootId => buildTree(rootId)).filter(child => child !== null)
            };
            return virtualRoot;
        }
    }


    renderTree(rootData) {
        this.g.selectAll("*").remove(); // Clear previous rendering

        if (!rootData || (rootData.id === "root" && (!rootData.children || rootData.children.length === 0))) {
             // Display a message if the network is empty
             this.g.append("text")
                 .attr("x", (this.width - this.margin.left - this.margin.right) / 2)
                 .attr("y", (this.height - this.margin.top - this.margin.bottom) / 2)
                 .attr("text-anchor", "middle")
                 .attr("class", "theme-text-secondary")
                 .text("Network is empty. Add a node to start.");
             return;
        }

        // Create tree hierarchy
        const root = d3.hierarchy(rootData, d => d.children);

        // Apply the tree layout
        const treeNodes = this.treeLayout(root);

        // Calculate coordinate swap based on layout
        const xCoord = this.useHorizontalLayout ? d => d.y : d => d.x;
        const yCoord = this.useHorizontalLayout ? d => d.x : d => d.y;

        // Links
        const linkGenerator = d3.link(this.useHorizontalLayout ? d3.linkHorizontal() : d3.linkVertical())
            .x(d => xCoord(d))
            .y(d => yCoord(d));

        this.g.append("g")
            .attr("class", "links")
            .selectAll("path")
            .data(treeNodes.links())
            .enter()
            .append("path")
            .attr("class", "link theme-border")
            .attr("d", linkGenerator)
            .attr("fill", "none")
            .attr("stroke", "var(--border-color)")
            .attr("stroke-opacity", 0.6)
            .attr("stroke-width", 1.5);

        // Nodes
        const node = this.g.append("g")
            .attr("class", "nodes")
            .selectAll("g")
            .data(treeNodes.descendants().filter(d => !d.data.data?.isVirtual)) // Filter out virtual root
            .enter()
            .append("g")
            .attr("class", "node-group")
            .attr("transform", d => `translate(${xCoord(d)},${yCoord(d)})`)
            .style("cursor", "pointer")
            .on("click", (event, d) => {
                event.stopPropagation(); // Prevent triggering SVG click/zoom
                 if (d.data?.data) { // Ensure data exists
                     this.selectNode(d.data.data); // Pass the original node data object
                 }
            })
            .on("contextmenu", (event, d) => {
                event.preventDefault();
                event.stopPropagation();
                 if (d.data?.data) {
                     this.showContextMenu(event, d.data.data); // Pass original node data
                 }
            })
            .on("mouseover", (event, d) => {
                 if (d.data?.data) {
                     this.showTooltip(event, d.data.data); // Pass original node data
                 }
            })
            .on("mouseout", () => this.hideTooltip());

        // Node Circles
        node.append("circle")
            .attr("class", "node-circle")
            .attr("data-id", d => d.data.id) // Add data-id for easier selection
            .attr("r", d => this.calculateNodeRadius(d.data.data))
            .attr("fill", d => this.getNodeColor(d.data.data))
            .attr("stroke", d => this.selectedNode && d.data.id === this.selectedNode.id ? 'var(--highlight)' : 'var(--border-color)')
            .attr("stroke-width", d => this.selectedNode && d.data.id === this.selectedNode.id ? 2.5 : 1);


        // Node Labels
        node.append("text")
            .attr("dy", "0.31em") // Vertically center
            .attr("x", d => this.useHorizontalLayout ? (d.children ? -12 : 12) : 0) // Position based on layout/children
            .attr("y", d => this.useHorizontalLayout ? 0 : (d.children ? -18 : 18))
            .attr("text-anchor", d => this.useHorizontalLayout ? (d.children ? "end" : "start") : "middle")
            .attr("class", "theme-text-primary")
            .style("font-size", "10px")
            .style("paint-order", "stroke") // Render stroke behind fill for readability
            .style("stroke", "var(--bg-secondary)") // Background color stroke
            .style("stroke-width", "3px")
            .style("stroke-linecap", "butt")
            .style("stroke-linejoin", "miter")
            .text(d => d.data.id);

        // Store node elements for potential future use (like highlighting)
        this.nodeElements = node.select("circle");
    }


    calculateNodeRadius(node) {
        // Base radius
        let radius = 8;

        // Increase radius based on total descendants (importance in hierarchy)
        const totalChildren = node?.total_children ?? 0;
        radius += Math.min(10, Math.sqrt(totalChildren + 1)); // Cap increase

        // Adjust slightly based on profit (economic value)
        const profit = node?.profit ?? 0;
        radius += Math.min(5, Math.log1p(profit / 100)); // Use log1p for stability, cap increase

         // Maybe increase size slightly for chokepoints
         if (node?.is_chokepoint) {
             radius += 1;
         }

        return Math.max(6, radius); // Ensure a minimum radius
    }

    getNodeColor(node) {
         if (!node) return 'gray'; // Handle cases where node data might be missing

         const theme = document.documentElement.classList.contains('dark') ? 'dark' : 'light';

         // Color based on Ponzi Value (using a blue scale)
         const ponziValue = node.ponzi_value ?? 0.5; // Default to medium if missing
         const ponziColorScale = d3.scaleSequential(theme === 'dark' ? d3.interpolateCool : d3.interpolateBlues)
                                   .domain([0.1, 1.0]); // Adjust domain based on expected value range
         let baseColor = ponziColorScale(ponziValue);

         // Override color for Chokepoints based on criticality
         if (node.is_chokepoint) {
             const criticality = node.criticality ?? 0; // 0 to 1
             const chokepointColorScale = d3.scaleSequential(d3.interpolateOranges) // Orange to Red spectrum
                                         .domain([0, 1]); // Criticality range
             baseColor = chokepointColorScale(criticality);
         }

         // Add visual indicator for Balance Status (e.g., using stroke or opacity)
         // We'll modify stroke color/width or add an outer ring later if needed.
         // For now, color is primarily determined by value/chokepoint status.

         // Highlight selected node
         if (this.selectedNode && node.id === this.selectedNode.id) {
              return theme === 'dark' ? '#68D391' : '#38A169'; // Selected color (Green)
         }

         return baseColor;
    }


    showTooltip(event, node) {
         if (!node || node.isVirtual) return; // Don't show tooltip for virtual root or invalid data

         // Get tooltip content
         const minThreshold = this.settings.minChildrenThreshold ?? 2;
         const childrenCount = node.children_count ?? 0;
         const neededChildren = Math.max(0, (node.suggested_child_count ?? minThreshold) - childrenCount);
         const isChokepoint = node.is_chokepoint ?? false;
         const balanceScore = node.balance_score ?? 1.0;

         let content = `<div class="font-bold text-base mb-1">${node.id}</div>`;
         content += `<div class="grid grid-cols-2 gap-x-3 text-xs">`;
         content += `<div class="font-medium text-right">Depth:</div><div>${node.depth ?? 'N/A'}</div>`;
         content += `<div class="font-medium text-right">Children:</div><div class="${isChokepoint ? 'text-red-400' : 'text-green-400'}">${childrenCount} / ${node.suggested_child_count ?? minThreshold}</div>`;
         content += `<div class="font-medium text-right">Total Desc:</div><div>${node.total_children ?? 'N/A'}</div>`;
         content += `<div class="font-medium text-right">Profit:</div><div>$${(node.profit ?? 0).toFixed(0)}</div>`;
         content += `<div class="font-medium text-right">Risk:</div><div>${((node.risk ?? 0) * 100).toFixed(0)}%</div>`;
         content += `<div class="font-medium text-right">Value:</div><div>${((node.ponzi_value ?? 0) * 100).toFixed(0)}%</div>`;
         content += `<div class="font-medium text-right">Balance:</div><div class="${balanceScore < 0.5 ? 'text-red-400' : balanceScore < 0.8 ? 'text-yellow-400' : 'text-green-400'}">${(balanceScore * 100).toFixed(0)}%</div>`;
         content += `</div>`; // End grid

         if (isChokepoint && neededChildren > 0) {
             content += `<div class="mt-1 text-red-400 text-xs"><i class="fas fa-exclamation-triangle mr-1"></i>Needs ${neededChildren} more</div>`;
         }

         this.tooltip
             .style("display", "block")
             .html(content);

         // Position tooltip - Adjust based on mouse position relative to SVG container
         const [svgX, svgY] = d3.pointer(event, this.svg.node()); // Get pointer relative to SVG
         const svgRect = this.svg.node().getBoundingClientRect();
         const tooltipRect = this.tooltip.node().getBoundingClientRect();

         let left = event.pageX + 15;
         let top = event.pageY + 15;

        // Prevent tooltip going off-screen
        if (left + tooltipRect.width > window.innerWidth + window.scrollX) {
            left = event.pageX - tooltipRect.width - 15;
        }
         if (top + tooltipRect.height > window.innerHeight + window.scrollY) {
             top = event.pageY - tooltipRect.height - 15;
         }
         if (top < window.scrollY) {
             top = window.scrollY + 5;
         }
          if (left < window.scrollX) {
             left = window.scrollX + 5;
         }


         this.tooltip.style("left", `${left}px`)
                    .style("top", `${top}px`);
    }


    hideTooltip() {
        this.tooltip.style("display", "none");
    }

    showContextMenu(event, node) {
         if (!node || node.isVirtual) return; // Don't show for virtual root

        this.contextNode = node; // Store the node associated with the context menu

        // Position and show the context menu
        this.contextMenu
            .style("left", `${event.pageX}px`)
            .style("top", `${event.pageY}px`)
            .style("display", "block");

        // Enable/disable delete option based on whether the node has children
        const canDelete = (node.children_count ?? 0) === 0;
        d3.select('#deleteNode') // Context menu delete item
             .style("display", canDelete ? "block" : "none")
             .attr("disabled", canDelete ? null : true)
             .style("opacity", canDelete ? 1 : 0.5)
             .style("cursor", canDelete ? "pointer" : "not-allowed");

         // Always allow adding nearby
         d3.select('#addNodeNearby')
             .style("display", "block");
    }

    hideContextMenu() {
        if (this.contextMenu) {
            this.contextMenu.style("display", "none");
        }
        this.contextNode = null; // Clear the context node
    }

    selectNode(nodeData, recenter = true) {
         if (!nodeData || nodeData.isVirtual) return; // Ignore clicks on virtual root

        // --- Update Visual Selection ---
        // Deselect previous
        this.nodeElements
             .filter(d => this.selectedNode && d.data.id === this.selectedNode.id)
             .attr('stroke', 'var(--border-color)') // Reset stroke color
             .attr("stroke-width", 1); // Reset stroke width

        // Select new
        this.selectedNode = nodeData;
        this.nodeElements
            .filter(d => d.data.id === nodeData.id)
            .attr('stroke', 'var(--highlight)') // Highlight stroke color
            .attr("stroke-width", 2.5); // Increase stroke width

        // --- Update Details Panel ---
        this.updateNodeDetails(nodeData);

         // --- Recenter View ---
         if (recenter) {
             this.centerOnNode(nodeData.id);
         }
    }

    centerOnNode(nodeId) {
        // Find the D3 data point corresponding to the node ID
        let targetNode = null;
         this.g.selectAll('.node-group').each(function(d) {
             if (d.data?.id === nodeId) {
                 targetNode = d;
             }
         });


         if (targetNode) {
             const xCoord = this.useHorizontalLayout ? targetNode.y : targetNode.x;
             const yCoord = this.useHorizontalLayout ? targetNode.x : targetNode.y;

             const scale = 1.2; // Zoom in slightly when centering
             const targetX = this.width / 2 - (xCoord * scale + this.margin.left);
             const targetY = this.height / 2 - (yCoord * scale + this.margin.top);


             const transform = d3.zoomIdentity
                 .translate(targetX, targetY)
                 .scale(scale);


             this.svg.transition().duration(750)
                 .call(this.zoom.transform, transform);
         }
    }

    updateNodeDetails(node) {
        if (!node || node.isVirtual) {
            this.nodeDetailsPanel.classed("hidden", true);
            return;
        }

        this.nodeDetailsPanel.classed("hidden", false);

        // Prepare data for display
        const minThreshold = this.settings.minChildrenThreshold ?? 2;
        const childrenCount = node.children_count ?? 0;
        const suggestedCount = node.suggested_child_count ?? minThreshold;
        const isChokepoint = node.is_chokepoint ?? (childrenCount < suggestedCount);
        const neededChildren = Math.max(0, suggestedCount - childrenCount);
        const balanceScore = node.balance_score ?? 1.0;

        let childrenStatusHtml = `<span class="${isChokepoint ? 'text-red-500 font-bold' : 'text-green-500 font-bold'}">${childrenCount} / ${suggestedCount}</span>`;
        if (isChokepoint && neededChildren > 0) {
            childrenStatusHtml += ` <span class="text-xs text-red-500">(${neededChildren} needed)</span>`;
        }

        let statusHtml = isChokepoint
            ? `<span class="text-red-500"><i class="fas fa-exclamation-triangle mr-1"></i>Chokepoint</span>`
            : `<span class="text-green-500"><i class="fas fa-check-circle mr-1"></i>Balanced</span>`;
        if (node.criticality && node.criticality > 0) {
             statusHtml += ` <span class="text-xs theme-text-secondary">(Crit: ${(node.criticality * 100).toFixed(0)}%)</span>`;
        }

        // Build node stats content
        let content = `
            <h3 class="text-lg font-bold mb-3 border-b theme-border pb-2 node-title">${node.id}</h3>
            <div class="grid grid-cols-2 gap-x-4 gap-y-1.5 text-sm mb-4">
                <div class="font-semibold text-right theme-text-secondary">Depth:</div>
                <div class="theme-text-primary">${node.depth ?? 'N/A'}</div>

                <div class="font-semibold text-right theme-text-secondary">Children:</div>
                <div class="theme-text-primary">${childrenStatusHtml}</div>

                <div class="font-semibold text-right theme-text-secondary">Total Desc:</div>
                <div class="theme-text-primary">${node.total_children ?? 'N/A'}</div>

                <div class="font-semibold text-right theme-text-secondary">Profit:</div>
                <div class="theme-text-primary">$${(node.profit ?? 0).toFixed(0)}</div>

                <div class="font-semibold text-right theme-text-secondary">Risk:</div>
                <div class="theme-text-primary ${ (node.risk ?? 0) > 0.7 ? 'text-red-500' : (node.risk ?? 0) > 0.4 ? 'text-yellow-500' : 'text-green-500' }">
                     ${((node.risk ?? 0) * 100).toFixed(0)}%
                </div>

                <div class="font-semibold text-right theme-text-secondary">Ponzi Value:</div>
                 <div class="theme-text-primary">${((node.ponzi_value ?? 0) * 100).toFixed(0)}%</div>

                <div class="font-semibold text-right theme-text-secondary">Balance:</div>
                 <div class="theme-text-primary ${balanceScore < 0.5 ? 'text-red-500' : balanceScore < 0.8 ? 'text-yellow-500' : 'text-green-500'}">
                      ${(balanceScore * 100).toFixed(0)}%
                 </div>

                <div class="font-semibold text-right theme-text-secondary">Status:</div>
                <div class="theme-text-primary">${statusHtml}</div>
            </div>
        `;

        // Add Chokepoint actions if needed
        if (isChokepoint && neededChildren > 0) {
            content += `
                <div class="bg-red-100 dark:bg-red-900 dark:bg-opacity-30 border border-red-300 dark:border-red-700 rounded p-3 mb-4 text-sm">
                    <h4 class="font-bold mb-1 text-red-700 dark:text-red-400">
                        <i class="fas fa-exclamation-circle mr-1"></i> Chokepoint Action
                    </h4>
                    <p class="mb-2 theme-text-secondary">This node needs ${neededChildren} more child${neededChildren === 1 ? '' : 'ren'} to meet the suggested threshold (${suggestedCount}).</p>
                    <button class="add-child-btn w-full text-xs py-1.5 bg-red-500 hover:bg-red-600 text-white rounded transition duration-200">
                        <i class="fas fa-plus-circle mr-1"></i> Add Child Node Here
                    </button>
                </div>
            `;
        }

        // Add direct children section (fetching from original data structure)
        const directChildrenIds = this.data?.graph?.[node.id]?.map(([childId]) => childId) ?? [];
        if (directChildrenIds.length > 0) {
            content += `
                <div class="mt-3">
                    <h4 class="text-sm font-semibold mb-2 theme-text-primary">Direct Children (${directChildrenIds.length})</h4>
                    <ul class="bg-gray-100 dark:bg-gray-700 rounded p-2 max-h-32 overflow-y-auto text-xs space-y-1">
                        ${directChildrenIds.map(childId => `
                            <li class="py-1 px-2 hover:bg-gray-200 dark:hover:bg-gray-600 rounded cursor-pointer child-link theme-text-primary"
                                data-node-id="${childId}">
                                <i class="fas fa-share-alt fa-xs mr-1.5 text-blue-500"></i> ${childId}
                            </li>
                        `).join('')}
                    </ul>
                </div>
            `;
        }

        // Update the node stats container
        this.nodeStatsContainer.html(content);

        // --- Add Event Listeners ---
        // Child links
        this.nodeStatsContainer.selectAll('.child-link').on('click', (event) => {
            const childId = event.currentTarget.dataset.nodeId;
            const childNodeData = this.findNodeById(childId);
            if (childNodeData) {
                this.selectNode(childNodeData); // Select and recenter
            } else {
                 console.warn(`Child node ${childId} not found in data.`);
            }
        });

        // "Add Child Node Here" button
        this.nodeStatsContainer.selectAll('.add-child-btn').on('click', () => {
            const form = document.getElementById("addNodeForm");
            if (form) {
                const parentInput = form.querySelector('[name="parent_id"]');
                if (parentInput) {
                    parentInput.value = node.id; // Pre-fill parent ID
                    form.scrollIntoView({ behavior: 'smooth', block: 'start' }); // Scroll to form
                    // Optionally focus the 'id' input
                    form.querySelector('[name="id"]')?.focus();
                }
            }
        });

         // Enable/disable the main delete button based on children count
         const canDelete = (node.children_count ?? 0) === 0;
         this.deleteNodeBtn
             .attr("disabled", canDelete ? null : true)
             .style("opacity", canDelete ? 1 : 0.5)
             .style("cursor", canDelete ? "pointer" : "not-allowed")
             .attr("title", canDelete ? "Delete this node" : "Cannot delete node with children");

    }

    // --- API Interaction Methods ---

    async fetchApi(url, options = {}) {
        try {
            const response = await fetch(url, options);
            if (!response.ok) {
                let errorDetail = `HTTP error! status: ${response.status}`;
                try {
                    const errorData = await response.json();
                    errorDetail = errorData.detail || JSON.stringify(errorData);
                } catch (e) { /* Ignore if response is not JSON */ }
                console.error(`API Error (${options.method || 'GET'} ${url}):`, errorDetail);
                alert(`API Error: ${errorDetail}`);
                return null; // Indicate failure
            }
            if (response.headers.get("content-type")?.includes("application/json")) {
                return await response.json(); // Parse JSON response
            }
             if (response.headers.get("content-disposition")) {
                 // Handle file download
                 const blob = await response.blob();
                 const downloadUrl = window.URL.createObjectURL(blob);
                 const a = document.createElement('a');
                 const filenameMatch = response.headers.get("content-disposition").match(/filename="(.+?)"/);
                 a.href = downloadUrl;
                 a.download = filenameMatch ? filenameMatch[1] : 'export.json';
                 document.body.appendChild(a);
                 a.click();
                 a.remove();
                 window.URL.revokeObjectURL(downloadUrl);
                 return { success: true, type: 'file' }; // Indicate success for file download
             }
            return { success: true, type: 'nodata' }; // For successful responses with no data (e.g., DELETE)
        } catch (error) {
            console.error(`Network Error (${options.method || 'GET'} ${url}):`, error);
            alert(`Network Error: ${error.message}. Check console for details.`);
            return null; // Indicate failure
        }
    }


    async deleteNode(nodeId) {
         if (!confirm(`Are you sure you want to delete node "${nodeId}"? This cannot be undone.`)) {
             return;
         }
        const result = await this.fetchApi(`/api/nodes/${nodeId}`, { method: "DELETE" });
        if (result && result.success) {
             // Clear selection if the deleted node was selected
             if (this.selectedNode && this.selectedNode.id === nodeId) {
                 this.selectedNode = null;
                 this.nodeDetailsPanel.classed("hidden", true);
             }
             await this.loadNetworkData(); // Reload data
             // No success message needed, visual update is enough
        }
         // Error handled by fetchApi
    }

    async addNode(data) {
         // Remove empty optional 'id' field before sending
         if (!data.id) delete data.id;
         // Add parent_id validation maybe?

        const result = await this.fetchApi("/api/nodes", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(data)
        });
         if (result && result.id) { // Check for returned ID
             await this.loadNetworkData(); // Reload data
             return true; // Indicate success
         }
         return false; // Indicate failure
    }

    async addNodeNearby(data) {
         // Remove empty optional 'id' field
         if (!data.id) delete data.id;
         // Remove x, y if they exist, as API doesn't need them
         delete data.x;
         delete data.y;

         const result = await this.fetchApi("/api/nodes/near", { // Assuming same endpoint or a dedicated one
             method: "POST",
             headers: { "Content-Type": "application/json" },
             body: JSON.stringify(data)
         });
         if (result && result.id) {
             await this.loadNetworkData();
         }
         // Error handled by fetchApi
    }

    async updateSettings(settings) {
         const result = await this.fetchApi("/api/settings", {
             method: "POST",
             headers: { "Content-Type": "application/json" },
             body: JSON.stringify(settings)
         });
         if (result && result.status === 'success') {
             await this.loadNetworkData(); // Reload to reflect changes
             // alert("Settings updated successfully!"); // Optional feedback
         }
         // Error handled by fetchApi
    }

    async importNetwork(file) {
         const formData = new FormData();
         formData.append('file', file);

         const result = await this.fetchApi("/api/import", {
             method: "POST",
             body: formData
             // Content-Type is set automatically for FormData
         });

         if (result && result.success) {
             this.selectedNode = null; // Clear selection after import
             this.nodeDetailsPanel.classed("hidden", true);
             await this.loadNetworkData(); // Reload the new network
             alert("Network imported successfully!");
         }
         // Error handled by fetchApi
    }

    async exportNetwork() {
        // Trigger download directly via GET request, handled by fetchApi
        const result = await this.fetchApi("/api/export");
         // fetchApi handles the download logic
         if (!result) {
             // Error message already shown by fetchApi
         }
    }

    async loadSuggestions() {
         if (!this.suggestionsPanel || !this.suggestionsList) return; // Ensure elements exist

         try {
             // Use fetchApi without error alerting for suggestions
             const response = await fetch("/api/suggestions");
             if (!response.ok) {
                 console.warn("Could not load suggestions:", response.statusText);
                 this.suggestionsPanel.classed("hidden", true);
                 return;
             }
             const data = await response.json();
             const suggestions = data.suggestions || [];

             this.suggestionsPanel.classed("hidden", suggestions.length === 0);
             if (suggestions.length === 0) return;

             // Create suggestion items
             const html = suggestions.map(s => `
                <div class="suggestion-item p-3 mb-2 theme-bg-primary rounded-lg border theme-border transition duration-150 ease-in-out hover:shadow-lg">
                    <div class="flex justify-between items-center mb-1">
                        <div class="font-semibold text-sm truncate pr-2" title="${s.id}">${s.id}</div>
                        <div class="text-xs theme-text-secondary">Depth: ${s.depth}</div>
                    </div>
                    <div class="text-xs theme-text-secondary mb-1.5">
                        Children: ${s.current_children}/${s.suggested_children} | Profit: $${s.profit.toFixed(0)}
                    </div>
                    <div class="mb-2">
                        <div class="text-xs mb-0.5 theme-text-secondary">Balance: ${Math.round(s.balance_score * 100)}%</div>
                        <div class="h-1.5 bg-gray-300 dark:bg-gray-600 rounded overflow-hidden">
                            <div class="h-full rounded ${s.balance_score < 0.5 ? 'bg-red-500' : s.balance_score < 0.8 ? 'bg-yellow-500' : 'bg-green-500'}"
                                 style="width: ${Math.max(5, Math.round(s.balance_score * 100))}%;"></div>
                        </div>
                    </div>
                    <button class="add-to-node w-full text-center text-xs py-1 bg-blue-500 hover:bg-blue-600 text-white rounded transition duration-200"
                            data-node-id="${s.id}" data-needed="${s.needed_children}">
                        <i class="fas fa-plus-circle fa-xs mr-1"></i> Add ${s.needed_children} Node${s.needed_children !== 1 ? 's' : ''}
                    </button>
                </div>
             `).join('');

             this.suggestionsList.html(html);

             // Add event listeners to the suggestion buttons
             this.suggestionsList.selectAll('.add-to-node').on('click', (event) => {
                 const button = event.currentTarget;
                 const nodeId = button.dataset.nodeId;
                 const form = document.getElementById("addNodeForm");
                 if (form) {
                     const parentInput = form.querySelector('[name="parent_id"]');
                     if (parentInput) {
                         parentInput.value = nodeId;
                         form.scrollIntoView({ behavior: 'smooth', block: 'start' });
                         form.querySelector('[name="id"]')?.focus();
                     }
                 }
             });

         } catch (error) {
             console.warn("Error loading suggestions:", error);
             this.suggestionsPanel.classed("hidden", true);
         }
    }

    async loadNetworkData() {
        const networkData = await this.fetchApi("/api/network");
        if (networkData) {
             this.update(networkData);
        } else {
             // Handle case where initial load fails (e.g., show error message)
             this.g.selectAll("*").remove();
             this.g.append("text")
                 .attr("x", (this.width - this.margin.left - this.margin.right) / 2)
                 .attr("y", (this.height - this.margin.top - this.margin.bottom) / 2)
                 .attr("text-anchor", "middle")
                 .attr("class", "theme-text-secondary")
                 .text("Failed to load network data.");
        }
        return networkData; // Return data or null
    }

    // --- Helper Methods ---

    findNodeById(nodeId) {
        // Find node data directly from the stored raw data
        return this.data?.nodes?.[nodeId] ?? null;
    }
}


// --- Initialization ---
let visualizer = null;

document.addEventListener('DOMContentLoaded', () => {
    visualizer = new NetworkVisualizer("network");

    if (visualizer) {
        // Load initial network data
        visualizer.loadNetworkData();

        // Handle main form submission for adding nodes
        const addNodeForm = document.getElementById("addNodeForm");
        if (addNodeForm) {
             addNodeForm.addEventListener("submit", async (e) => {
                 e.preventDefault();
                 const formData = new FormData(e.target);
                 const data = Object.fromEntries(formData.entries());

                 if (!data.parent_id && visualizer.data && Object.keys(visualizer.data.nodes).length > 0) {
                     alert("Parent ID is required unless the network is empty.");
                     return;
                 }

                 const success = await visualizer.addNode(data);
                 if (success) {
                     e.target.reset(); // Clear form on success
                 }
                 // Error messages handled within addNode -> fetchApi
             });
        } else {
             console.error("Add Node Form not found.");
        }


        // Close modal when clicking the backdrop
        const addNodeModal = document.getElementById("addNodeModal");
        if (addNodeModal) {
             addNodeModal.addEventListener("click", (event) => {
                 if (event.target === addNodeModal) {
                     addNodeModal.classList.add("hidden");
                 }
             });
        }

         // Handle window resize - Debounced for performance
         let resizeTimer;
         window.addEventListener("resize", () => {
             clearTimeout(resizeTimer);
             resizeTimer = setTimeout(() => {
                 if (visualizer) {
                     visualizer.width = visualizer.container.node().getBoundingClientRect().width;
                     visualizer.svg.attr("viewBox", [0, 0, visualizer.width, visualizer.height]);
                     visualizer.updateTreeLayout(); // Update layout sizes
                     visualizer.redrawVisualization(); // Redraw with new dimensions
                 }
             }, 250); // Adjust debounce delay as needed
         });

    } else {
        console.error("Failed to initialize NetworkVisualizer.");
        // Optionally display an error message to the user in the container
        d3.select("#network").html('<p class="text-red-500 p-4 text-center">Error initializing the network visualizer. Check console for details.</p>');
    }
});