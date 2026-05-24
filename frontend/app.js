// API Backend Host Configuration
const API_HOST = "http://127.0.0.1:8000";

// Global Variables
let network = null;
let allNodes = [];
let allEdges = [];
let activeIngestTab = "url";
let graphPhysicsEnabled = true;
let showDeprecated = true;

// Initialize App
window.addEventListener("DOMContentLoaded", () => {
    checkBackendStatus();
    loadGraph();
    
    // Periodically poll backend status
    setInterval(checkBackendStatus, 15000);
});

// ==========================================================================
// Ingestion Panel Actions
// ==========================================================================
function switchIngestTab(tab) {
    activeIngestTab = tab;
    
    // Toggle active tab buttons
    document.querySelectorAll(".ingest-tabs .tab-btn").forEach(btn => {
        btn.classList.remove("active");
    });
    event.currentTarget.classList.add("active");
    
    // Toggle active input panel
    document.getElementById("tab-url").classList.add("hidden");
    document.getElementById("tab-text").classList.add("hidden");
    document.getElementById("tab-consult").classList.add("hidden");
    
    const btn = document.getElementById("btn-ingest");
    const btnText = btn.querySelector(".btn-text");
    
    if (tab === "url") {
        document.getElementById("tab-url").classList.remove("hidden");
        btnText.textContent = "Ingest to Synapse";
    } else if (tab === "text") {
        document.getElementById("tab-text").classList.remove("hidden");
        btnText.textContent = "Ingest to Synapse";
    } else if (tab === "consult") {
        document.getElementById("tab-consult").classList.remove("hidden");
        btnText.textContent = "Bootstrap Context";
    }
}

async function triggerIngest() {
    if (activeIngestTab === "consult") {
        triggerBootstrap();
        return;
    }
    const btn = document.getElementById("btn-ingest");
    const spinner = document.getElementById("ingest-spinner");
    const statusBox = document.getElementById("ingest-status-box");
    
    let urlInput = document.getElementById("ingest-url").value.trim();
    let textInput = document.getElementById("ingest-text").value.trim();
    
    const payload = {};
    if (activeIngestTab === "url") {
        if (!urlInput) {
            alert("Please enter a valid URL to ingest.");
            return;
        }
        payload.url = urlInput;
    } else {
        if (!textInput) {
            alert("Please enter some knowledge text to ingest.");
            return;
        }
        payload.text = textInput;
    }
    
    // Set Ingestion UI state to Loading
    btn.disabled = true;
    spinner.classList.remove("hidden");
    statusBox.classList.add("hidden");
    
    try {
        const response = await fetch(`${API_HOST}/api/ingest`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });
        
        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail || "Ingestion service failed.");
        }
        
        const result = await response.json();
        
        // Populate Ingestion Status Panel
        document.getElementById("ingest-chunks").textContent = result.vector_chunks_created;
        document.getElementById("ingest-nodes").textContent = result.nodes_extracted;
        document.getElementById("ingest-edges").textContent = result.edges_extracted;
        
        statusBox.classList.remove("hidden");
        
        // Reset Inputs
        document.getElementById("ingest-url").value = "";
        document.getElementById("ingest-text").value = "";
        
        // Refresh API Stats and Topology Visualizer
        checkBackendStatus();
        loadGraph();
        
    } catch (e) {
        console.error(e);
        alert(`Ingestion failed: ${e.message}`);
    } finally {
        btn.disabled = false;
        spinner.classList.add("hidden");
    }
}

// ==========================================================================
// vis-network Visual Graph Projection
// ==========================================================================
async function loadGraph() {
    const container = document.getElementById("graph-container");
    const loader = document.getElementById("viewport-loading");
    
    loader.classList.remove("hidden");
    
    try {
        const response = await fetch(`${API_HOST}/api/graph?show_deprecated=${showDeprecated}`);
        if (!response.ok) throw new Error("Could not retrieve knowledge graph topology.");
        
        const data = await response.json();
        allNodes = data.nodes;
        allEdges = data.edges;
        
        // Define Custom Premium HSL Styling for Groups/Types
        const groupStyles = {
            agent: { color: { background: "#4f46e5", border: "#818cf8" }, font: { color: "#ffffff" } },
            skill: { color: { background: "#db2777", border: "#f472b6" }, font: { color: "#ffffff" } },
            tool: { color: { background: "#0891b2", border: "#22d3ee" }, font: { color: "#ffffff" } },
            best_practice: { color: { background: "#16a34a", border: "#4ade80" }, font: { color: "#ffffff" } },
            theoretical_knowledge: { color: { background: "#d97706", border: "#fbbf24" }, font: { color: "#ffffff" } },
            concept: { color: { background: "#ea580c", border: "#fb923c" }, font: { color: "#ffffff" } }
        };
        
        // Apply group styling rules
        const formattedNodes = allNodes.map(node => {
            let style = groupStyles[node.group] || { color: { background: "#4b5563", border: "#9ca3af" } };
            
            // Override styles for deprecated concepts
            if (node.status === "deprecated") {
                style = {
                    color: {
                        background: "#2d3748",
                        border: "#4a5568",
                        highlight: { background: "#4a5568", border: "#718096" }
                    },
                    font: { color: "#718096" }
                };
            }
            
            return {
                ...node,
                color: style.color,
                font: {
                    face: "Outfit",
                    size: 13,
                    color: node.status === "deprecated" ? "#718096" : "#e2e8f0",
                    ...style.font
                },
                shadow: {
                    enabled: true,
                    color: "rgba(0,0,0,0.4)",
                    size: 5,
                    x: 2,
                    y: 2
                },
                shape: "dot",
                size: node.group === "agent" ? 22 : 14,
                opacity: node.status === "deprecated" ? 0.5 : 1.0,
                shapeProperties: {
                    borderDashes: node.status === "deprecated"
                }
            };
        });
        
        const formattedEdges = allEdges.map(edge => {
            const isSupersedes = edge.relation_type === "SUPERSEDES";
            return {
                ...edge,
                color: {
                    color: isSupersedes ? "#ef4444" : "rgba(226, 232, 240, 0.15)",
                    highlight: isSupersedes ? "#f87171" : "#818cf8",
                    hover: isSupersedes ? "rgba(239, 68, 68, 0.35)" : "rgba(226, 232, 240, 0.35)"
                },
                font: {
                    face: "Inter",
                    size: 9,
                    color: isSupersedes ? "#ef4444" : "#64748b",
                    strokeWidth: 0
                },
                arrows: {
                    to: { enabled: true, scaleFactor: 0.5 }
                },
                smooth: {
                    type: "continuous"
                },
                dashes: isSupersedes,
                width: isSupersedes ? 2 : 1.5
            };
        });
        
        // vis-network Dataset configuration
        const graphData = {
            nodes: new vis.DataSet(formattedNodes),
            edges: new vis.DataSet(formattedEdges)
        };
        
        const options = {
            nodes: {
                borderWidth: 2,
                borderWidthSelected: 4
            },
            edges: {
                width: 1.5,
                selectionWidth: 3
            },
            interaction: {
                hover: true,
                selectConnectedEdges: true
            },
            physics: {
                enabled: graphPhysicsEnabled,
                solver: "forceAtlas2Based",
                forceAtlas2Based: {
                    gravitationalConstant: -36,
                    centralGravity: 0.015,
                    springLength: 80,
                    springConstant: 0.08
                },
                stabilization: {
                    iterations: 150,
                    updateInterval: 25
                }
            }
        };
        
        // Instantiating network projection
        network = new vis.Network(container, graphData, options);
        
        // Event Listeners for Topology Interaction
        network.on("selectNode", (params) => {
            const clickedNodeId = params.nodes[0];
            openInspector(clickedNodeId);
        });
        
        network.on("deselectNode", () => {
            closeInspector();
        });
        
    } catch (e) {
        console.error(e);
        container.innerHTML = `<div style="padding:2rem;color:hsl(0, 85%, 60%);">Failed to project synapse topology: ${e.message}</div>`;
    } finally {
        loader.classList.add("hidden");
    }
}

function fitGraph() {
    if (network) network.fit({ animation: { duration: 800, easingFunction: "easeInOutQuad" } });
}

function togglePhysics(changeState = true) {
    if (!network) return;
    if (changeState) graphPhysicsEnabled = !graphPhysicsEnabled;
    
    network.setOptions({ physics: { enabled: graphPhysicsEnabled } });
    
    const btn = document.getElementById("btn-physics");
    btn.textContent = graphPhysicsEnabled ? "Physics: On" : "Physics: Off";
}

// ==========================================================================
// Node Details Inspector Panel
// ==========================================================================
function openInspector(nodeId) {
    const node = allNodes.find(n => n.id === nodeId);
    if (!node) return;
    
    const inspector = document.getElementById("node-inspector");
    const badge = document.getElementById("inspect-badge");
    const name = document.getElementById("inspect-name");
    const desc = document.getElementById("inspect-desc");
    const props = document.getElementById("inspect-props");
    
    badge.textContent = node.group.toUpperCase();
    badge.className = `node-badge group-${node.group}`;
    
    // Handle badge inline styling color
    const colors = {
        agent: "var(--color-agent)",
        skill: "var(--color-skill)",
        tool: "var(--color-tool)",
        best_practice: "var(--color-practice)",
        theoretical_knowledge: "var(--color-theory)",
        concept: "var(--color-concept)"
    };
    badge.style.backgroundColor = colors[node.group] || "gray";
    
    name.textContent = node.label;
    desc.textContent = node.description || "No description provided.";
    
    // Clear and build properties
    props.innerHTML = `
        <div style="font-size:0.65rem;color:var(--text-muted);margin-bottom:0.25rem;">NODE SIGNATURE:</div>
        <div style="font-family:monospace;font-size:0.7rem;background:var(--bg-dark);padding:0.4rem;border-radius:6px;word-break:break-all;color:var(--accent-cyan);">${node.id}</div>
    `;
    
    inspector.classList.remove("hidden");
}

function closeInspector() {
    document.getElementById("node-inspector").classList.add("hidden");
    if (network) network.unselectAll();
}

// ==========================================================================
// Hybrid Retrieval Console Operations
// ==========================================================================
function handleSearchKey(event) {
    if (event.key === "Enter") {
        triggerSearch();
    }
}

async function triggerSearch() {
    const queryInput = document.getElementById("search-query");
    const query = queryInput.value.trim();
    if (!query) return;
    
    const placeholder = document.getElementById("search-placeholder");
    const loader = document.getElementById("search-loader");
    const answerBox = document.getElementById("answer-box");
    
    // UI state loading
    placeholder.classList.add("hidden");
    answerBox.classList.add("hidden");
    loader.classList.remove("hidden");
    queryInput.disabled = true;
    
    try {
        const response = await fetch(`${API_HOST}/api/search`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ query: query, top_k: 5 })
        });
        
        if (!response.ok) throw new Error("Search service execution failed.");
        const result = await response.json();
        
        // Render Synthesized Text Answer with primitive Markdown conversion
        const textElement = document.getElementById("answer-text");
        textElement.innerHTML = parseSimpleMarkdown(result.answer);
        
        // Highlight corresponding nodes on the Graph Canvas!
        highlightGraphMatches(result.subgraph.nodes);
        
        // Populates source reference chunks
        const sourceList = document.getElementById("source-list");
        const sourceCount = document.getElementById("source-count");
        sourceList.innerHTML = "";
        sourceCount.textContent = result.sources.length;
        
        result.sources.forEach((hit, idx) => {
            const item = document.createElement("div");
            item.className = "source-item";
            item.innerHTML = `
                <div class="source-meta">
                    <span>Rank #${idx + 1} (Sim: ${Math.round(hit.score * 100)}%)</span>
                    <span>Node: ${hit.node_id}</span>
                </div>
                <div class="source-text">"${hit.text}"</div>
            `;
            sourceList.appendChild(item);
        });
        
        // Display Answer Panel
        loader.classList.add("hidden");
        answerBox.classList.remove("hidden");
        
    } catch (e) {
        console.error(e);
        alert(`Search execution failed: ${e.message}`);
        placeholder.classList.remove("hidden");
        loader.classList.add("hidden");
    } finally {
        queryInput.disabled = false;
        queryInput.focus();
    }
}

function toggleAccordion(id) {
    const panel = document.getElementById(id);
    const header = panel.previousElementSibling;
    const arrow = header.querySelector(".acc-arrow");
    
    const isHidden = panel.classList.toggle("hidden");
    arrow.textContent = isHidden ? "▼" : "▲";
}

function highlightGraphMatches(matchedNodes) {
    if (!network || !matchedNodes || matchedNodes.length === 0) return;
    
    const matchedIds = matchedNodes.map(n => n.id);
    
    // Select matched node keys on vis network projection
    network.selectNodes(matchedIds, true);
    
    // Focus/Zoom network viewport to center the first (most relevant) node matching
    const primaryId = matchedIds[0];
    network.focus(primaryId, {
        scale: 1.1,
        animation: {
            duration: 1000,
            easingFunction: "easeInOutQuad"
        }
    });
    
    // Automatically trigger Inspector Panel for primary retrieved entity
    openInspector(primaryId);
}

// Helper to update DB status indicators
async function checkBackendStatus() {
    const apiStatus = document.getElementById("api-status");
    const statNodes = document.getElementById("stat-nodes");
    const statEdges = document.getElementById("stat-edges");
    const statBar = document.getElementById("db-status-bar");
    
    try {
        const response = await fetch(`${API_HOST}/api/status`);
        if (!response.ok) throw new Error();
        
        const data = await response.json();
        
        apiStatus.innerHTML = `ONLINE ${data.gemini_api_active ? "⚡" : "⚙️"}`;
        apiStatus.style.color = "var(--accent-cyan)";
        statNodes.textContent = data.node_count;
        statEdges.textContent = data.edge_count;
        
    } catch (e) {
        apiStatus.textContent = "OFFLINE";
        apiStatus.style.color = "hsl(0, 85%, 60%)";
    }
}

// Simple Markdown parser utility
function parseSimpleMarkdown(md) {
    if (!md) return "";
    
    let html = md;
    
    // Bullet lists
    html = html.replace(/^\s*-\s+(.+)$/gm, "<li>$1</li>");
    html = html.replace(/(<li>.*<\/li>)/gs, "<ul>$1</ul>");
    
    // Bold matches
    html = html.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");
    
    // Headers
    html = html.replace(/^### (.*?)$/gm, "<h4>$1</h4>");
    html = html.replace(/^#### (.*?)$/gm, "<h5>$1</h5>");
    html = html.replace(/^## (.*?)$/gm, "<h3>$1</h3>");
    
    // Code blocks / inline code
    html = html.replace(/`(.*?)`/g, "<code>$1</code>");
    
    // Paragraph spaces
    html = html.replace(/\n\n/g, "<br><br>");
    
    return html;
}

// Project Consultant Bootstrapping Trigger Actions
async function triggerBootstrap() {
    const btn = document.getElementById("btn-ingest");
    const spinner = document.getElementById("ingest-spinner");
    const pathInput = document.getElementById("consult-path").value.trim();
    
    if (!pathInput) {
        alert("Please enter a valid project root path.");
        return;
    }
    
    btn.disabled = true;
    spinner.classList.remove("hidden");
    
    try {
        const response = await fetch(`${API_HOST}/api/consult/bootstrap`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ project_path: pathInput })
        });
        
        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail || "Bootstrap consultant service failed.");
        }
        
        const result = await response.json();
        
        // Open the report panel and display the compiled GEMINI.md context
        const reportPanel = document.getElementById("consultant-report");
        const reportContent = document.getElementById("report-markdown-content");
        
        reportContent.textContent = result.markdown_output;
        reportPanel.classList.remove("hidden");
        
        // Refresh status metrics and reload graph
        checkBackendStatus();
        loadGraph();
    } catch (e) {
        console.error(e);
        alert(`Bootstrap failed: ${e.message}`);
    } finally {
        btn.disabled = false;
        spinner.classList.add("hidden");
    }
}

function closeConsultantReport() {
    document.getElementById("consultant-report").classList.add("hidden");
}

function toggleShowDeprecated() {
    showDeprecated = !showDeprecated;
    const btn = document.getElementById("btn-deprecated");
    btn.textContent = showDeprecated ? "Deprecated: On" : "Deprecated: Off";
    loadGraph();
}
