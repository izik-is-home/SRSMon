/**
 * Interactive Replication Topology DAG Component for SRSMon
 * Primary ASE -> RepAgent -> Inbound Queue -> DIST -> Outbound Queues -> DSI -> Targets
 */

class SRSTopologyView {
  constructor(containerId) {
    this.container = document.getElementById(containerId);
    this.nodes = [];
    this.links = [];
  }

  render(topologyData) {
    if (!this.container) return;
    this.nodes = topologyData.nodes || [];
    this.links = topologyData.links || [];

    const width = this.container.clientWidth || 900;
    const height = this.container.clientHeight || 380;

    // Fixed layout columns for clear replication flow
    const cols = {
      primary: width * 0.10,
      repagent: width * 0.25,
      inbound: width * 0.40,
      dist: width * 0.55,
      outbound: width * 0.70,
      dsi: width * 0.85,
      target: width * 0.95
    };

    const nodeCoords = {
      "primary_erp": { x: cols.primary, y: height * 0.45, w: 130, h: 54, icon: "🗄️", subtitle: "Primary ASE" },
      "rep_agent_erp": { x: cols.repagent, y: height * 0.45, w: 120, h: 48, icon: "⚙️", subtitle: "Log Scanner" },
      "srs_core": { x: cols.inbound, y: height * 0.15, w: 140, h: 45, icon: "⚡", subtitle: "SRS Engine" },
      "q_in_erp": { x: cols.inbound, y: height * 0.45, w: 130, h: 48, icon: "📥", subtitle: "Inbound Queue" },
      "dist": { x: cols.dist, y: height * 0.45, w: 110, h: 48, icon: "🔀", subtitle: "Distributor" },
      "q_out_crm": { x: cols.outbound, y: height * 0.25, w: 130, h: 48, icon: "📤", subtitle: "Outbound CRM" },
      "q_out_bi": { x: cols.outbound, y: height * 0.70, w: 130, h: 48, icon: "📤", subtitle: "Outbound BI" },
      "dsi_crm": { x: cols.dsi, y: height * 0.25, w: 110, h: 48, icon: "🛑", subtitle: "DSI Suspended" },
      "dsi_bi": { x: cols.dsi, y: height * 0.70, w: 110, h: 48, icon: "⚡", subtitle: "DSI Active" },
      "db_crm": { x: cols.target, y: height * 0.25, w: 90, h: 48, icon: "🎯", subtitle: "CRM Target" },
      "db_dw": { x: cols.target, y: height * 0.70, w: 90, h: 48, icon: "🎯", subtitle: "BI DW" },
      "rep_dr": { x: cols.target, y: height * 0.48, w: 90, h: 48, icon: "🌐", subtitle: "DR Server" }
    };

    let svgHtml = `
      <svg class="topology-svg" viewBox="0 0 ${width} ${height}" xmlns="http://www.w3.org/2000/svg">
        <defs>
          <linearGradient id="linkGradHealthy" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stop-color="#38bdf8" stop-opacity="0.6"/>
            <stop offset="100%" stop-color="#10b981" stop-opacity="0.8"/>
          </linearGradient>
          <linearGradient id="linkGradSuspended" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stop-color="#f59e0b" stop-opacity="0.5"/>
            <stop offset="100%" stop-color="#ef4444" stop-opacity="0.8"/>
          </linearGradient>
          <filter id="glowGreen" x="-20%" y="-20%" width="140%" height="140%">
            <feGaussianBlur stdDeviation="3" result="blur" />
            <feComposite in="SourceGraphic" in2="blur" operator="over" />
          </filter>
        </defs>
    `;

    // Render Connection Links
    this.links.forEach((link, idx) => {
      const src = nodeCoords[link.source];
      const tgt = nodeCoords[link.target];
      if (src && tgt) {
        const isSuspended = link.target.includes("crm") || link.source.includes("crm");
        const strokeColor = isSuspended ? "url(#linkGradSuspended)" : "url(#linkGradHealthy)";
        const strokeDash = isSuspended ? "stroke-dasharray='4 4'" : "";
        const mx = (src.x + tgt.x) / 2;

        svgHtml += `
          <path d="M ${src.x} ${src.y} C ${mx} ${src.y}, ${mx} ${tgt.y}, ${tgt.x} ${tgt.y}" 
                fill="none" stroke="${strokeColor}" stroke-width="2.5" ${strokeDash} opacity="0.85" />
        `;

        // Animated Pulse Particle along link if active
        if (!isSuspended) {
          svgHtml += `
            <circle r="3.5" fill="#38bdf8">
              <animateMotion path="M ${src.x} ${src.y} C ${mx} ${src.y}, ${mx} ${tgt.y}, ${tgt.x} ${tgt.y}" 
                             dur="${2.0 + (idx % 3) * 0.5}s" repeatCount="indefinite" />
            </circle>
          `;
        }
      }
    });

    // Render Nodes
    this.nodes.forEach(node => {
      const coord = nodeCoords[node.id];
      if (!coord) return;

      const isCritical = node.status === "SUSPENDED" || node.status === "CRITICAL";
      const isWarn = node.status === "WARNING";
      const borderColor = isCritical ? "#ef4444" : isWarn ? "#f59e0b" : "#38bdf8";
      const bgColor = isCritical ? "rgba(239, 68, 68, 0.15)" : "#1e293b";
      const textColor = isCritical ? "#fca5a5" : "#f8fafc";

      svgHtml += `
        <g class="topology-node" transform="translate(${coord.x - coord.w/2}, ${coord.y - coord.h/2})">
          <rect width="${coord.w}" height="${coord.h}" rx="8" ry="8" 
                fill="${bgColor}" stroke="${borderColor}" stroke-width="${isCritical ? 2 : 1.5}" 
                filter="${isCritical ? 'url(#glowGreen)' : 'none'}" />
          <text x="12" y="22" font-size="12" font-weight="700" fill="${textColor}" font-family="Inter, sans-serif">
            ${coord.icon} ${node.name.length > 14 ? node.name.substring(0, 12) + '...' : node.name}
          </text>
          <text x="12" y="38" font-size="9" fill="#94a3b8" font-family="Inter, sans-serif">
            ${coord.subtitle} ${node.size_mb ? `(${Math.round(node.size_mb)} MB)` : ''}
          </text>
        </g>
      `;
    });

    svgHtml += `</svg>`;
    this.container.innerHTML = svgHtml;
  }
}
