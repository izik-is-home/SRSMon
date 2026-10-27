/**
 * Modal & Drawer Manager for SRSMon
 * Handles: Lead Blocker Modal, Alerts Drawer, and Admin ISQL Execution
 */

const ModalManager = {
  currentServerId: 1,

  setServerId(id) {
    this.currentServerId = id;
  },

  // =========================================================================
  // Lead Blocker Modal
  // =========================================================================
  async openLeadBlocker(queueName) {
    const overlay = document.getElementById("blockerModalOverlay");
    const titleEl = document.getElementById("blockerModalQueueTitle");
    const contentEl = document.getElementById("blockerModalBodyContent");
    const killBtn = document.getElementById("btnKillBlocker");

    titleEl.textContent = `Primary ASE Truncation Blocker: ${queueName}`;
    contentEl.innerHTML = `
      <div style="text-align: center; padding: 2rem; color: var(--text-muted);">
        <div class="pulse-dot" style="margin-bottom: 0.5rem;"></div>
        <p>Querying master..syslogshold & master..sysprocesses on Primary ASE...</p>
      </div>
    `;
    overlay.classList.add("active");

    try {
      const resp = await fetch(`/api/v1/servers/${this.currentServerId}/queues/${encodeURIComponent(queueName)}/blockers`);
      const data = await resp.json();

      if (!data.lead_blocker) {
        contentEl.innerHTML = `
          <div style="text-align: center; padding: 1.5rem; background: rgba(16, 185, 129, 0.1); border-radius: 8px; border: 1px solid rgba(16, 185, 129, 0.3);">
            <p style="color: var(--color-healthy); font-weight: 700; font-size: 1.1rem; margin-bottom: 0.5rem;">✅ No Active Blocker Found</p>
            <p style="color: var(--text-muted); font-size: 0.85rem;">The Secondary Truncation Point is advancing normally. No transactions are holding the transaction log.</p>
          </div>
        `;
        if (killBtn) killBtn.style.display = "none";
        return;
      }

      const b = data.lead_blocker;
      if (killBtn) {
        killBtn.style.display = "inline-flex";
        killBtn.onclick = () => this.simulateKillBlocker(b.spid, queueName);
      }

      contentEl.innerHTML = `
        <div class="blocker-explanation">
          <strong>⚠️ Root Cause Identified:</strong><br>
          ${b.impact || 'Holding Secondary Truncation Point in master..syslogshold, preventing log truncation and causing Inbound Queue expansion.'}
        </div>

        <div class="blocker-grid">
          <div class="blocker-field">
            <span class="lbl">Blocking SPID</span>
            <span class="val" style="color: #ef4444; font-size: 1.2rem;">${b.spid}</span>
          </div>
          <div class="blocker-field">
            <span class="lbl">Transaction Name</span>
            <span class="val">${b.transaction_name || '$unnamed'}</span>
          </div>
          <div class="blocker-field">
            <span class="lbl">Open Duration</span>
            <span class="val" style="color: #f59e0b;">${b.duration_formatted || (b.duration_seconds + 's')}</span>
          </div>
          <div class="blocker-field">
            <span class="lbl">Client Hostname</span>
            <span class="val">${b.hostname}</span>
          </div>
          <div class="blocker-field">
            <span class="lbl">Application / Program</span>
            <span class="val">${b.program_name}</span>
          </div>
          <div class="blocker-field">
            <span class="lbl">Current SQL Command</span>
            <span class="val">${b.cmd}</span>
          </div>
          <div class="blocker-field" style="grid-column: span 2;">
            <span class="lbl">Transaction Start Time</span>
            <span class="val" style="font-size: 0.78rem;">${b.login_time}</span>
          </div>
        </div>

        <div style="background: #0f172a; padding: 0.75rem 1rem; border-radius: 8px; border: 1px solid var(--border-subtle);">
          <div style="font-size: 0.72rem; color: var(--text-dim); text-transform: uppercase; font-weight: 600; margin-bottom: 0.35rem;">DBA Resolution Guidance</div>
          <div style="font-size: 0.8rem; color: #cbd5e1;">${b.recommended_action}</div>
        </div>
      `;
    } catch (err) {
      contentEl.innerHTML = `<p style="color: #ef4444;">Failed to fetch blocker data: ${err.message}</p>`;
    }
  },

  closeLeadBlocker() {
    const overlay = document.getElementById("blockerModalOverlay");
    overlay.classList.remove("active");
  },

  async simulateKillBlocker(spid, queueName) {
    if (!confirm(`Are you sure you want to simulate executing 'KILL ${spid}' on Primary ASE?`)) return;
    try {
      const resp = await fetch(`/api/v1/servers/${this.currentServerId}/simulate_scenario`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ scenario: "kill_blocker", enable: true })
      });
      const res = await resp.json();
      alert(`[DBA Action Executed]: ${res.message}. Secondary Truncation Point released!`);
      this.openLeadBlocker(queueName);
    } catch (err) {
      alert("Error: " + err.message);
    }
  },

  // =========================================================================
  // Alerts Drawer
  // =========================================================================
  async toggleAlertsDrawer(forceOpen = null) {
    const drawer = document.getElementById("alertsDrawer");
    const isOpen = drawer.classList.contains("open");
    const nextState = forceOpen !== null ? forceOpen : !isOpen;

    if (nextState) {
      drawer.classList.add("open");
      await this.loadAlerts();
    } else {
      drawer.classList.remove("open");
    }
  },

  async loadAlerts() {
    const listEl = document.getElementById("alertsDrawerList");
    try {
      const resp = await fetch("/api/v1/alerts?active_only=true");
      const alerts = await resp.json();

      if (alerts.length === 0) {
        listEl.innerHTML = `
          <div style="text-align: center; padding: 2rem; color: var(--text-dim);">
            <p>🎉 No active alerts for this server.</p>
          </div>
        `;
        return;
      }

      listEl.innerHTML = alerts.map(a => `
        <div class="alert-item ${a.severity}">
          <div class="alert-top-row">
            <span class="alert-badge ${a.severity}">${a.severity}</span>
            <span class="alert-time">${a.alert_time ? a.alert_time.split("T")[1].substring(0, 8) : ''}</span>
          </div>
          <div style="font-size: 0.75rem; color: var(--color-cyan); font-weight: 600;">${a.category} &bull; ${a.source_entity}</div>
          <div class="alert-msg">${a.message}</div>
          <div style="display: flex; justify-content: flex-end; margin-top: 0.25rem;">
            <button class="btn-action" style="font-size: 0.7rem; padding: 0.2rem 0.5rem;" onclick="ModalManager.resolveAlert(${a.alert_id})">
              ✓ Acknowledge
            </button>
          </div>
        </div>
      `).join("");
    } catch (err) {
      listEl.innerHTML = `<p style="color: #ef4444;">Failed to load alerts: ${err.message}</p>`;
    }
  },

  async resolveAlert(alertId) {
    try {
      await fetch(`/api/v1/alerts/${alertId}/resolve`, { method: "POST" });
      await this.loadAlerts();
    } catch (err) {
      console.error(err);
    }
  },

  // =========================================================================
  // Admin ISQL Command Runner
  // =========================================================================
  async runAdminCommand(cmdText = null) {
    const input = document.getElementById("consoleCommandInput");
    const output = document.getElementById("consoleOutputBox");
    const cmd = cmdText || (input ? input.value : "admin who");

    if (!cmd.trim()) return;
    if (input) input.value = cmd;

    output.textContent = `Executing: ${cmd} on server ${this.currentServerId}...\n`;

    try {
      const resp = await fetch(`/api/v1/servers/${this.currentServerId}/admin_cmd`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ command: cmd })
      });
      const data = await resp.json();
      output.textContent = data.raw_output || JSON.stringify(data, null, 2);
    } catch (err) {
      output.textContent = `[ERROR]: ${err.message}`;
    }
  }
};
