/**
 * Interactive Dual-Axis Trend Chart for SRSMon
 * Left Axis: Inbound & Outbound Throughput (MB/s)
 * Right Axis: Total Queue Size (MB)
 */

class SRSTrendChart {
  constructor(canvasId) {
    this.canvas = document.getElementById(canvasId);
    this.ctx = this.canvas ? this.canvas.getContext('2d') : null;
    this.data = [];
    this.hoverIndex = -1;

    if (this.canvas) {
      this.initEvents();
      this.resize();
      window.addEventListener('resize', () => this.resize());
    }
  }

  resize() {
    if (!this.canvas) return;
    const rect = this.canvas.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    this.canvas.width = rect.width * dpr;
    this.canvas.height = rect.height * dpr;
    this.ctx.scale(dpr, dpr);
    this.width = rect.width;
    this.height = rect.height;
    this.render();
  }

  setData(dataPoints) {
    this.data = dataPoints || [];
    this.render();
  }

  addDataPoint(pt) {
    this.data.push(pt);
    if (this.data.length > 60) {
      this.data.shift();
    }
    this.render();
  }

  initEvents() {
    this.canvas.addEventListener('mousemove', (e) => {
      const rect = this.canvas.getBoundingClientRect();
      const mouseX = e.clientX - rect.left;
      if (this.data.length < 2) return;

      const paddingLeft = 50;
      const paddingRight = 60;
      const chartWidth = this.width - paddingLeft - paddingRight;
      const step = chartWidth / (this.data.length - 1);

      let closestIdx = Math.round((mouseX - paddingLeft) / step);
      closestIdx = Math.max(0, Math.min(this.data.length - 1, closestIdx));

      if (this.hoverIndex !== closestIdx) {
        this.hoverIndex = closestIdx;
        this.render();
      }
    });

    this.canvas.addEventListener('mouseleave', () => {
      this.hoverIndex = -1;
      this.render();
    });
  }

  render() {
    if (!this.ctx || !this.width || !this.height) return;
    const ctx = this.ctx;
    const w = this.width;
    const h = this.height;

    ctx.clearRect(0, 0, w, h);

    const padL = 55;
    const padR = 65;
    const padT = 25;
    const padB = 35;
    const cw = w - padL - padR;
    const ch = h - padT - padB;

    if (this.data.length === 0) {
      ctx.fillStyle = "#64748b";
      ctx.font = "12px Inter, sans-serif";
      ctx.textAlign = "center";
      ctx.fillText("Waiting for telemetry stream...", w / 2, h / 2);
      return;
    }

    // Find Max Values
    let maxThroughput = 10.0;
    let maxQueueMb = 1000.0;

    this.data.forEach(d => {
      const inT = d.inbound_throughput_mb_sec || 0;
      const outT = d.outbound_throughput_mb_sec || 0;
      const qMb = d.total_queue_mb || 0;
      if (inT > maxThroughput) maxThroughput = inT;
      if (outT > maxThroughput) maxThroughput = outT;
      if (qMb > maxQueueMb) maxQueueMb = qMb;
    });

    maxThroughput = Math.ceil(maxThroughput * 1.25);
    maxQueueMb = Math.ceil(maxQueueMb * 1.2);

    // Draw Grid Lines
    ctx.strokeStyle = "rgba(255, 255, 255, 0.05)";
    ctx.lineWidth = 1;
    ctx.beginPath();
    const rows = 4;
    for (let i = 0; i <= rows; i++) {
      const y = padT + (ch / rows) * i;
      ctx.moveTo(padL, y);
      ctx.lineTo(w - padR, y);

      // Left axis label (MB/s)
      const tVal = ((rows - i) / rows * maxThroughput).toFixed(1);
      ctx.fillStyle = "#38bdf8";
      ctx.font = "10px JetBrains Mono, monospace";
      ctx.textAlign = "right";
      ctx.fillText(`${tVal} MB/s`, padL - 8, y + 3);

      // Right axis label (Total Queue MB)
      const qVal = Math.round((rows - i) / rows * maxQueueMb);
      ctx.fillStyle = "#f59e0b";
      ctx.textAlign = "left";
      ctx.fillText(`${qVal} MB`, w - padR + 8, y + 3);
    }
    ctx.stroke();

    const n = this.data.length;
    const getX = (i) => padL + (n > 1 ? (cw / (n - 1)) * i : cw / 2);
    const getYThroughput = (val) => padT + ch - (val / maxThroughput) * ch;
    const getYQueue = (val) => padT + ch - (val / maxQueueMb) * ch;

    // 1. Draw Queue Size Filled Area (Amber / Yellow)
    ctx.beginPath();
    ctx.moveTo(getX(0), padT + ch);
    for (let i = 0; i < n; i++) {
      ctx.lineTo(getX(i), getYQueue(this.data[i].total_queue_mb || 0));
    }
    ctx.lineTo(getX(n - 1), padT + ch);
    ctx.closePath();
    const qGrad = ctx.createLinearGradient(0, padT, 0, padT + ch);
    qGrad.addColorStop(0, "rgba(245, 158, 11, 0.25)");
    qGrad.addColorStop(1, "rgba(245, 158, 11, 0.0)");
    ctx.fillStyle = qGrad;
    ctx.fill();

    // Queue Size Line
    ctx.strokeStyle = "#f59e0b";
    ctx.lineWidth = 2;
    ctx.beginPath();
    for (let i = 0; i < n; i++) {
      const x = getX(i);
      const y = getYQueue(this.data[i].total_queue_mb || 0);
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.stroke();

    // 2. Draw Inbound Throughput Line (Cyan)
    ctx.strokeStyle = "#38bdf8";
    ctx.lineWidth = 2;
    ctx.beginPath();
    for (let i = 0; i < n; i++) {
      const x = getX(i);
      const y = getYThroughput(this.data[i].inbound_throughput_mb_sec || 0);
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.stroke();

    // 3. Draw Outbound Throughput Line (Purple)
    ctx.strokeStyle = "#a855f7";
    ctx.lineWidth = 2;
    ctx.beginPath();
    for (let i = 0; i < n; i++) {
      const x = getX(i);
      const y = getYThroughput(this.data[i].outbound_throughput_mb_sec || 0);
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.stroke();

    // Draw X-axis timestamps
    ctx.fillStyle = "#64748b";
    ctx.font = "9px JetBrains Mono, monospace";
    ctx.textAlign = "center";
    const xInterval = Math.max(1, Math.floor(n / 5));
    for (let i = 0; i < n; i += xInterval) {
      const d = this.data[i];
      if (d && d.timestamp) {
        const timeStr = d.timestamp.split("T")[1]?.substring(0, 8) || "";
        ctx.fillText(timeStr, getX(i), h - 12);
      }
    }

    // Hover Tooltip Crosshair
    if (this.hoverIndex >= 0 && this.hoverIndex < n) {
      const hData = this.data[this.hoverIndex];
      const hX = getX(this.hoverIndex);

      ctx.strokeStyle = "rgba(255, 255, 255, 0.4)";
      ctx.setLineDash([4, 4]);
      ctx.beginPath();
      ctx.moveTo(hX, padT);
      ctx.lineTo(hX, padT + ch);
      ctx.stroke();
      ctx.setLineDash([]);

      // Draw Tooltip Box
      const boxW = 190;
      const boxH = 75;
      let boxX = hX + 12;
      if (boxX + boxW > w - 10) boxX = hX - boxW - 12;
      const boxY = padT + 10;

      ctx.fillStyle = "rgba(15, 23, 42, 0.95)";
      ctx.strokeStyle = "rgba(255, 255, 255, 0.2)";
      ctx.lineWidth = 1;
      ctx.fillRect(boxX, boxY, boxW, boxH);
      ctx.strokeRect(boxX, boxY, boxW, boxH);

      ctx.textAlign = "left";
      ctx.fillStyle = "#f8fafc";
      ctx.font = "10px JetBrains Mono, monospace";
      const tStr = hData.timestamp ? hData.timestamp.split("T")[1]?.substring(0, 8) : "";
      ctx.fillText(`Time: ${tStr}`, boxX + 8, boxY + 16);

      ctx.fillStyle = "#f59e0b";
      ctx.fillText(`Queue Size: ${hData.total_queue_mb?.toLocaleString()} MB`, boxX + 8, boxY + 32);

      ctx.fillStyle = "#38bdf8";
      ctx.fillText(`Inbound:  ${hData.inbound_throughput_mb_sec} MB/s`, boxX + 8, boxY + 48);

      ctx.fillStyle = "#a855f7";
      ctx.fillText(`Outbound: ${hData.outbound_throughput_mb_sec} MB/s`, boxX + 8, boxY + 64);
    }
  }
}
