/**
 * SRSMon Single Page Application Core
 * Real-time WebSockets, Live Telemetry, UI State Management
 */

class SRSApp {
  constructor() {
    this.currentServerId = 1;
    this.ws = null;
    this.trendChart = null;
    this.topologyView = null;
    this.activeFilter = "ALL";
    this.searchQuery = "";
    this.lastQueuesData = [];
    this.lastPartitionsData = [];
  }

  async init() {
    console.log("[SRSMon] Initializing application...");

    // Initialize Components
    this.trendChart = new SRSTrendChart("trendCanvas");
    this.topologyView = new SRSTopologyView("topologyContainer");
    ModalManager.setServerId(this.currentServerId);

    // Bind UI Events
    this.bindEvents();

    // Load initial servers list
    await this.loadServers();

    // Load initial historical chart data
    await this.loadChartHistory();

    // Connect WebSocket
    this.connectWebSocket();
  }

  bindEvents() {
    // Server Picker
    const srvSelect = document.getElementById("serverSelect");
    if (srvSelect) {
      srvSelect.addEventListener("change", (e) => {
        this.currentServerId = parseInt(e.target.value);
        ModalManager.setServerId(this.currentServerId);
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
          this.ws.send(JSON.stringify({
            action: "subscribe",
            server_id: this.currentServerId,
            interval_seconds: 5
          }));
        }
        this.loadChartHistory();
        this.loadTopology();
      });
    }

    // Tab Navigation
    document.querySelectorAll(".nav-tab").forEach(tab => {
      tab.addEventListener("click", () => {
        document.querySelectorAll(".nav-tab").forEach(t => t.classList.remove("active"));
        tab.classList.add("active");

        const tabName = tab.dataset.tab;
        document.querySelectorAll(".tab-pane").forEach(pane => {
          pane.style.display = pane.id === `tab-${tabName}` ? "block" : "none";
        });

        if (tabName === "topology") {
          this.loadTopology();
        } else if (tabName === "dashboard") {
          setTimeout(() => this.trendChart && this.trendChart.resize(), 100);
        }
      });
    });

    // Queue Filters
    document.querySelectorAll(".filter-btn").forEach(btn => {
      btn.addEventListener("click", () => {
        document.querySelectorAll(".filter-btn").forEach(b => b.classList.remove("active"));
        btn.classList.add("active");
        this.activeFilter = btn.dataset.filter;
        this.renderQueues(this.lastQueuesData);
      });
    });

    // Queue Search
    const searchInput = document.getElementById("queueSearchInput");
    if (searchInput) {
      searchInput.addEventListener("input", (e) => {
        this.searchQuery = e.target.value.toLowerCase().trim();
        this.renderQueues(this.lastQueuesData);
      });
    }
  }

  async loadServers() {
    try {
      const resp = await fetch("/api/v1/servers");
      const servers = await resp.json();
      const srvSelect = document.getElementById("serverSelect");
      if (srvSelect) {
        srvSelect.innerHTML = servers.map(s => `
          <option value="${s.server_id}">${s.server_name} (${s.environment})</option>
        `).join("");
      }
    } catch (err) {
      console.error("[SRSMon] Error loading servers:", err);
    }
  }

  async loadChartHistory() {
    try {
      const resp = await fetch(`/api/v1/servers/${this.currentServerId}/history?range_hours=1`);
      const data = await resp.json();
      if (this.trendChart) {
        this.trendChart.setData(data);
      }
    } catch (err) {
      console.error("[SRSMon] Error loading chart history:", err);
    }
  }

  async loadTopology() {
    try {
      const resp = await fetch(`/api/v1/servers/${this.currentServerId}/topology`);
      const data = await resp.json();
      if (this.topologyView) {
        this.topologyView.render(data);
      }
    } catch (err) {
      console.error("[SRSMon] Error loading topology:", err);
    }
  }

  connectWebSocket() {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${protocol}//${window.location.host}/ws/v1/live`;

    console.log(`[SRSMon] Connecting WebSocket: ${wsUrl}`);
    this.ws = new WebSocket(wsUrl);

    this.ws.onopen = () => {
      console.log("[SRSMon] WebSocket connected!");
      const liveDot = document.getElementById("wsLiveIndicator");
      if (liveDot) liveDot.style.opacity = "1";

      this.ws.send(JSON.stringify({
        action: "subscribe",
        server_id: this.currentServerId,
        interval_seconds: 5
      }));
    };

    this.ws.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        if (payload.event === "METRICS_UPDATE") {
          this.handleLiveUpdate(payload);
        }
      } catch (err) {
        console.error("[SRSMon] WS Message parse error:", err);
      }
    };

    this.ws.onclose = () => {
      console.warn("[SRSMon] WebSocket disconnected. Reconnecting in 3s...");
      const liveDot = document.getElementById("wsLiveIndicator");
      if (liveDot) liveDot.style.opacity = "0.4";
      setTimeout(() => this.connectWebSocket(), 3000);
    };

    this.ws.onerror = (err) => {
      console.error("[SRSMon] WS error:", err);
    };
  }

  handleLiveUpdate(data) {
    // 1. Health Status Badge
    const healthBadge = document.getElementById("globalHealthBadge");
    const healthText = document.getElementById("globalHealthText");
    if (healthBadge && healthText) {
      healthBadge.className = `health-badge ${data.system_health}`;
      healthText.textContent = data.system_health;
    }

    // 2. Threads KPI
    const th = data.threads_summary || {};
    const thEl = document.getElementById("threadsKpiVal");
    const thPill = document.getElementById("threadsKpiPill");
    if (thEl) {
      thEl.textContent = `${th.active || 0} / ${th.total || 0}`;
      if (th.suspended > 0 || th.down > 0) {
        thPill.classList.add("danger");
      } else {
        thPill.classList.remove("danger");
      }
    }

    // 3. Overall Lag KPI
    const lagEl = document.getElementById("lagKpiVal");
    const lagPill = document.getElementById("lagKpiPill");
    if (lagEl) {
      const lag = data.overall_lag_seconds || 0.0;
      lagEl.textContent = `${lag.toFixed(1)}s`;
      if (lag > 120.0) {
        lagPill.classList.add("danger");
      } else {
        lagPill.classList.remove("danger");
      }
    }

    // 4. Alerts Count Badge
    const alertBtn = document.getElementById("activeAlertsBtn");
    const alertCountEl = document.getElementById("activeAlertsCount");
    const count = data.active_alerts_count || 0;
    if (alertCountEl) alertCountEl.textContent = count;
    if (alertBtn) {
      alertBtn.style.display = count > 0 ? "inline-flex" : "none";
    }

    // 5. Partitions Grid
    this.lastPartitionsData = data.partitions || [];
    this.renderPartitions(this.lastPartitionsData);

    // 6. Queues Grid
    this.lastQueuesData = data.queues || [];
    this.renderQueues(this.lastQueuesData);

    // 7. Push to Trend Chart
    if (this.trendChart) {
      const totQueueMb = (data.queues || []).reduce((acc, q) => acc + (q.size_mb || 0), 0);
      const inTput = (data.queues || []).filter(q => q.type === "Inbound").reduce((acc, q) => acc + (q.throughput_mb_sec || 0), 0);
      const outTput = (data.queues || []).filter(q => q.type === "Outbound").reduce((acc, q) => acc + (q.throughput_mb_sec || 0), 0);

      this.trendChart.addDataPoint({
        timestamp: data.timestamp,
        total_queue_mb: Math.round(totQueueMb),
        inbound_throughput_mb_sec: parseFloat(inTput.toFixed(2)),
        outbound_throughput_mb_sec: parseFloat(outTput.toFixed(2)),
        overall_lag_seconds: data.overall_lag_seconds
      });
    }
  }

  renderPartitions(partitions) {
    const grid = document.getElementById("partitionsGrid");
    if (!grid) return;

    grid.innerHTML = partitions.map(p => {
      const usedPct = p.used_pct || 0;
      const statusClass = usedPct >= 85 ? "critical" : usedPct >= 70 ? "warning" : "healthy";
      const isCriticalBorder = usedPct >= 90 ? "critical-border" : "";
      const estHours = p.estimated_hours_until_full || 0;

      let predictionHtml = "";
      if (usedPct >= 85) {
        predictionHtml = `
          <div class="prediction-callout critical">
            <span>⚠️ בקצב הנוכחי, המחיצה תתמלא בתוך <strong>${estHours} שעות</strong></span>
            <span style="font-weight: 700;">דחוף</span>
          </div>
        `;
      } else if (usedPct >= 70) {
        predictionHtml = `
          <div class="prediction-callout warning">
            <span>ℹ️ צפי התמלאות: בעוד כ-${estHours} שעות</span>
          </div>
        `;
      }

      return `
        <div class="partition-card ${isCriticalBorder}">
          <div class="partition-card-header">
            <div class="partition-name-group">
              <span class="partition-logical">${p.name}</span>
              <span class="partition-path">${p.device_path}</span>
            </div>
            <span class="partition-state-tag">${p.state || 'ON-LINE'}</span>
          </div>

          <div class="partition-numbers">
            <span class="used-pct-big ${statusClass}">${usedPct.toFixed(1)}%</span>
            <div class="partition-bytes-info">
              <strong>${Math.round(p.free_mb).toLocaleString()} MB</strong> פנוי מתוך ${Math.round(p.total_mb).toLocaleString()} MB
            </div>
          </div>

          <div class="progress-container">
            <div class="progress-bar-fill ${statusClass}" style="width: ${Math.min(100, usedPct)}%;"></div>
          </div>

          ${predictionHtml}
        </div>
      `;
    }).join("");
  }

  renderQueues(queues) {
    const tbody = document.getElementById("queuesTableBody");
    if (!tbody) return;

    let filtered = queues;

    // Apply Filter
    if (this.activeFilter === "INBOUND") {
      filtered = filtered.filter(q => q.type === "Inbound");
    } else if (this.activeFilter === "OUTBOUND") {
      filtered = filtered.filter(q => q.type === "Outbound");
    } else if (this.activeFilter === "PROBLEMATIC") {
      filtered = filtered.filter(q => q.status === "Suspended" || (q.lag || 0) > 60 || (q.size_mb || 0) > 10000);
    }

    // Apply Search
    if (this.searchQuery) {
      filtered = filtered.filter(q => (q.name || "").toLowerCase().includes(this.searchQuery));
    }

    if (filtered.length === 0) {
      tbody.innerHTML = `<tr><td colspan="9" style="text-align: center; color: var(--text-dim); padding: 2rem;">No matching queues found.</td></tr>`;
      return;
    }

    tbody.innerHTML = filtered.map(q => {
      const isSuspended = q.status === "Suspended";
      const isHuge = (q.size_mb || 0) > 10000;
      const rowClass = isSuspended || isHuge ? "row-problematic" : "";

      const sizeClass = (q.size_mb || 0) > 10000 ? "huge" : (q.size_mb || 0) > 2000 ? "large" : "";

      return `
        <tr class="${rowClass}">
          <td>
            <div class="queue-name-cell">
              <span>${q.name}</span>
            </div>
          </td>
          <td>
            <span class="badge-type ${q.type}">${q.type}</span>
          </td>
          <td>
            <span class="size-mb-val ${sizeClass}">${Math.round(q.size_mb || 0).toLocaleString()} MB</span>
          </td>
          <td>
            <span class="seg-block-code">${q.first_seg_block || '-'} &rarr; ${q.last_seg_block || '-'}</span>
          </td>
          <td>
            <span class="seg-block-code">${q.next_read || '-'}</span>
          </td>
          <td>
            <span class="status-badge ${q.status}">
              <span class="pulse-dot" style="width: 6px; height: 6px;"></span>
              ${q.status}
            </span>
          </td>
          <td>
            <span style="font-family: var(--font-mono); font-weight: 600; color: ${(q.lag || 0) > 60 ? '#ef4444' : '#f8fafc'};">
              ${(q.lag || 0).toFixed(1)}s
            </span>
          </td>
          <td>
            <span style="font-family: var(--font-mono); color: #38bdf8;">
              ${(q.throughput_mb_sec || 0).toFixed(1)} MB/s
            </span>
          </td>
          <td style="text-align: right;">
            ${q.type === 'Inbound' ? `
              <button class="btn-action btn-cyan" style="font-size: 0.72rem; padding: 0.25rem 0.55rem;" onclick="ModalManager.openLeadBlocker('${q.name}')">
                🔍 Lead Blocker
              </button>
            ` : `
              <button class="btn-action" style="font-size: 0.72rem; padding: 0.25rem 0.55rem;" onclick="ModalManager.runAdminCommand('admin who, sqm')">
                ℹ️ Inspect SQM
              </button>
            `}
          </td>
        </tr>
      `;
    }).join("");
  }

  // =========================================================================
  // DBA Simulation Scenario Injections
  // =========================================================================
  async triggerScenario(scenario, enable = true) {
    try {
      const resp = await fetch(`/api/v1/servers/${this.currentServerId}/simulate_scenario`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ scenario, enable })
      });
      const data = await resp.json();
      alert(`[DBA Scenario Updated]: ${data.message}`);
    } catch (err) {
      alert("Error: " + err.message);
    }
  }
}

// Global App Instance
window.SRS_APP = new SRSApp();
document.addEventListener("DOMContentLoaded", () => window.SRS_APP.init());
