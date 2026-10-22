"""Interactive Web UI HTML template for DAMF (Dashboard, Devices, Dynamic Lab Topology, Jobs, Setup Wizard)."""

from __future__ import annotations

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>DAMF — Device Automation &amp; Management Framework</title>
  <style>
    :root {
      --bg: #0f172a;
      --panel: #1e293b;
      --panel-hover: #263449;
      --border: #334155;
      --text: #f8fafc;
      --muted: #94a3b8;
      --accent: #38bdf8;
      --accent-dark: #0284c7;
      --green: #22c55e;
      --amber: #f59e0b;
      --red: #ef4444;
      --purple: #a855f7;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Inter, sans-serif;
      background: var(--bg);
      color: var(--text);
    }
    header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0.85rem 1.75rem;
      background: #0b1120;
      border-bottom: 1px solid var(--border);
      position: sticky;
      top: 0;
      z-index: 20;
    }
    .brand {
      display: flex;
      align-items: center;
      gap: 0.75rem;
      font-weight: 700;
      font-size: 1.15rem;
      letter-spacing: 0.03em;
    }
    .brand-badge {
      background: linear-gradient(135deg, var(--accent), var(--purple));
      color: #0b1120;
      font-weight: 800;
      padding: 0.25rem 0.55rem;
      border-radius: 6px;
      font-size: 0.85rem;
    }
    nav {
      display: flex;
      gap: 0.5rem;
    }
    nav button {
      background: transparent;
      color: var(--muted);
      border: 1px solid transparent;
      padding: 0.45rem 0.9rem;
      border-radius: 6px;
      cursor: pointer;
      font-size: 0.9rem;
      font-weight: 600;
    }
    nav button.active, nav button:hover {
      color: var(--text);
      background: var(--panel);
      border-color: var(--border);
    }
    main {
      max-width: 1360px;
      margin: 1.5rem auto;
      padding: 0 1.5rem 3rem;
    }
    .kpi-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
      gap: 1rem;
      margin-bottom: 1.5rem;
    }
    .card {
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 1.15rem 1.25rem;
    }
    .kpi-label {
      color: var(--muted);
      font-size: 0.8rem;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }
    .kpi-value {
      font-size: 1.85rem;
      font-weight: 700;
      margin-top: 0.35rem;
    }
    .toolbar {
      display: flex;
      flex-wrap: wrap;
      justify-content: space-between;
      align-items: center;
      gap: 0.75rem;
      margin-bottom: 1rem;
    }
    .btn {
      background: var(--accent-dark);
      color: white;
      border: none;
      padding: 0.45rem 0.82rem;
      border-radius: 6px;
      cursor: pointer;
      font-weight: 600;
      font-size: 0.82rem;
    }
    .btn:hover { background: var(--accent); color: #0b1120; }
    .btn-secondary {
      background: #334155;
      color: var(--text);
    }
    .btn-warning {
      background: #b45309;
      color: #fef3c7;
    }
    .btn-danger {
      background: #991b1b;
      color: #fee2e2;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 0.88rem;
    }
    th, td {
      text-align: left;
      padding: 0.7rem 0.75rem;
      border-bottom: 1px solid var(--border);
    }
    th {
      color: var(--muted);
      font-weight: 600;
      font-size: 0.76rem;
      text-transform: uppercase;
    }
    .pill {
      display: inline-block;
      padding: 0.18rem 0.55rem;
      border-radius: 999px;
      font-size: 0.75rem;
      font-weight: 600;
    }
    .pill-available { background: rgba(34, 197, 94, 0.18); color: #4ade80; }
    .pill-reserved { background: rgba(245, 158, 11, 0.2); color: #fbbf24; }
    .pill-offline { background: rgba(239, 68, 68, 0.2); color: #f87171; }
    .tag {
      display: inline-block;
      background: #0f172a;
      border: 1px solid var(--border);
      color: var(--muted);
      border-radius: 4px;
      padding: 0.1rem 0.4rem;
      font-size: 0.72rem;
      margin-right: 0.25rem;
    }
    .section { display: none; }
    .section.active { display: block; }
    .grid-2 {
      display: grid;
      grid-template-columns: 2fr 1fr;
      gap: 1.25rem;
    }
    .form-row {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 0.65rem;
    }
    @media (max-width: 900px) {
      .grid-2, .form-row { grid-template-columns: 1fr; }
    }
    input, select, textarea {
      width: 100%;
      padding: 0.48rem 0.65rem;
      background: #0b1120;
      border: 1px solid var(--border);
      color: var(--text);
      border-radius: 6px;
      margin-top: 0.22rem;
      margin-bottom: 0.65rem;
      font-size: 0.86rem;
    }
    input[type="checkbox"] {
      width: auto;
      margin-right: 0.4rem;
    }
    label {
      font-size: 0.78rem;
      color: var(--muted);
      font-weight: 600;
    }
    pre.console {
      background: #020617;
      border: 1px solid var(--border);
      padding: 0.85rem;
      border-radius: 8px;
      color: #38bdf8;
      font-size: 0.81rem;
      overflow-x: auto;
      min-height: 95px;
      white-space: pre-wrap;
    }
    #topology-svg {
      width: 100%;
      height: 470px;
      background: #0b1120;
      border: 1px solid var(--border);
      border-radius: 8px;
    }
  </style>
</head>
<body>
  <header>
    <div class="brand">
      <span class="brand-badge">DAMF v2.0</span>
      <span id="header-lab-name">Device Automation &amp; Management Framework</span>
    </div>
    <nav>
      <button id="tab-dashboard" class="active" onclick="switchTab('dashboard')">Dashboard</button>
      <button id="tab-devices" onclick="switchTab('devices')">Devices</button>
      <button id="tab-lab" onclick="switchTab('lab')">Dynamic Lab View</button>
      <button id="tab-jobs" onclick="switchTab('jobs')">Test Jobs</button>
      <button id="tab-setup" onclick="switchTab('setup')">Setup Wizard</button>
    </nav>
  </header>

  <main>
    <div class="kpi-grid">
      <div class="card">
        <div class="kpi-label">Total Boards</div>
        <div class="kpi-value" id="kpi-total">0</div>
      </div>
      <div class="card">
        <div class="kpi-label">Available</div>
        <div class="kpi-value" style="color: var(--green)" id="kpi-available">0</div>
      </div>
      <div class="card">
        <div class="kpi-label">Reserved / In-Use</div>
        <div class="kpi-value" style="color: var(--amber)" id="kpi-reserved">0</div>
      </div>
      <div class="card">
        <div class="kpi-label">Test Jobs Executed</div>
        <div class="kpi-value" style="color: var(--accent)" id="kpi-jobs">0</div>
      </div>
    </div>

    <!-- DASHBOARD SECTION -->
    <section id="sec-dashboard" class="section active">
      <div class="grid-2">
        <div class="card">
          <div class="toolbar">
            <h3 style="margin:0">Active Reservations &amp; Lab Pool</h3>
            <button class="btn" onclick="triggerDiscovery()">Scan Network / USB / ADB</button>
          </div>
          <table>
            <thead>
              <tr>
                <th>Board</th>
                <th>Type / Arch</th>
                <th>IP / SSH</th>
                <th>State</th>
                <th>Owner</th>
              </tr>
            </thead>
            <tbody id="dashboard-devices-body"></tbody>
          </table>
        </div>
        <div class="card">
          <h3 style="margin-top:0">SSH &amp; Target Operations Console</h3>
          <label>Target Device</label>
          <select id="quick-device"></select>
          <div style="display:flex; gap:0.45rem; flex-wrap:wrap; margin-bottom:0.65rem;">
            <button class="btn" onclick="connectSelectedSSH()">Connect SSH &amp; Detect OS</button>
            <button class="btn btn-warning" onclick="rebootSelectedSSH()">Reboot Target (SSH)</button>
            <button class="btn btn-secondary" onclick="runQuickTestSuite()">Run Smoke Suite</button>
          </div>
          <label>Shell / SSH / ADB Command</label>
          <input id="quick-cmd" value="uname -a && cat /etc/os-release" />
          <button class="btn" style="margin-bottom:0.75rem;" onclick="runQuickCommand()">Execute Command</button>
          <label>Console Output</label>
          <pre class="console" id="quick-output">Ready.</pre>
        </div>
      </div>
    </section>

    <!-- DEVICES SECTION -->
    <section id="sec-devices" class="section">
      <div class="grid-2">
        <div class="card">
          <div class="toolbar">
            <h3 style="margin:0">Managed Lab Devices</h3>
            <div>
              <button class="btn" onclick="triggerDiscovery()">Auto-Discover</button>
              <button class="btn btn-secondary" onclick="refreshAll()">Refresh</button>
            </div>
          </div>
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Board / OS</th>
                <th>SSH / IP / Subnet</th>
                <th>Power</th>
                <th>State</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody id="devices-table-body"></tbody>
          </table>
        </div>
        <div class="card">
          <h3 style="margin-top:0">Define / Edit Device in Lab</h3>
          <div class="form-row">
            <div>
              <label>Device Name</label>
              <input id="dev-name" placeholder="e.g. rpi4-rack2-01" />
            </div>
            <div>
              <label>Board Type</label>
              <input id="dev-type" placeholder="raspberry-pi-4, ti-am62x..." value="raspberry-pi-4" />
            </div>
          </div>
          <div class="form-row">
            <div>
              <label>IP Address</label>
              <input id="dev-ip" placeholder="192.168.10.150" />
            </div>
            <div>
              <label>Subnet CIDR</label>
              <input id="dev-subnet" value="192.168.10.0/24" />
            </div>
          </div>
          <div class="form-row">
            <div>
              <label>Transport</label>
              <select id="dev-transport">
                <option value="ssh">ssh</option>
                <option value="serial">serial</option>
                <option value="adb">adb</option>
                <option value="local">local</option>
              </select>
            </div>
            <div>
              <label>Architecture</label>
              <input id="dev-arch" value="arm64" />
            </div>
          </div>
          <div class="form-row">
            <div>
              <label>SSH Username</label>
              <input id="dev-ssh-user" value="root" />
            </div>
            <div>
              <label>SSH Port</label>
              <input id="dev-ssh-port" type="number" value="22" />
            </div>
          </div>
          <div class="form-row">
            <div>
              <label>SSH Key Path (optional)</label>
              <input id="dev-ssh-key" placeholder="~/.ssh/id_ed25519" />
            </div>
            <div>
              <label>Target OS Hint</label>
              <input id="dev-os-hint" placeholder="debian, busybox, yocto, freebsd..." />
            </div>
          </div>
          <label>Tags (comma-separated)</label>
          <input id="dev-tags" placeholder="gpio, i2c, can-bus" />
          <label>Connected Topology Peers (comma-separated device names)</label>
          <input id="dev-peers" placeholder="ti-am62x-evm-01" />
          <div style="margin: 0.35rem 0 0.85rem;">
            <label style="cursor:pointer; color:var(--text);">
              <input type="checkbox" id="dev-simulated" checked />
              Simulated Mode (uncheck for live network SSH connection)
            </label>
          </div>
          <button class="btn" onclick="saveDevice()">Save Device to Pool &amp; Topology</button>
        </div>
      </div>
    </section>

    <!-- DYNAMIC LAB VIEW SECTION -->
    <section id="sec-lab" class="section">
      <div class="grid-2">
        <div class="card">
          <div class="toolbar">
            <h3 style="margin:0">Dynamic Lab Network &amp; Topology View</h3>
            <span style="color:var(--muted); font-size:0.82rem;">Click any board node to inspect, connect via SSH, or reboot</span>
          </div>
          <svg id="topology-svg" viewBox="0 0 860 450"></svg>
        </div>
        <div style="display:flex; flex-direction:column; gap:1.15rem;">
          <div class="card">
            <h3 style="margin-top:0">Selected Node Inspector</h3>
            <div id="node-inspector" style="color:var(--muted); font-size:0.88rem;">
              Select a device node in the topology diagram to inspect its subnet, SSH endpoint, detected OS, and peer links.
            </div>
          </div>
          <div class="card">
            <h3 style="margin-top:0">Quick-Add Device to Topology</h3>
            <div class="form-row">
              <div>
                <label>Device Name</label>
                <input id="topo-dev-name" placeholder="ti-sitara-02" />
              </div>
              <div>
                <label>Board Type</label>
                <input id="topo-dev-type" value="ti-am62x" />
              </div>
            </div>
            <div class="form-row">
              <div>
                <label>IP Address</label>
                <input id="topo-dev-ip" placeholder="192.168.10.120" />
              </div>
              <div>
                <label>Subnet CIDR</label>
                <input id="topo-dev-subnet" value="192.168.10.0/24" />
              </div>
            </div>
            <div class="form-row">
              <div>
                <label>SSH User</label>
                <input id="topo-dev-user" value="root" />
              </div>
              <div>
                <label>Target OS</label>
                <input id="topo-dev-os" placeholder="poky / debian / busybox" value="poky" />
              </div>
            </div>
            <label>Connect to Peer Node(s)</label>
            <input id="topo-dev-peers" placeholder="rpi4-lab-01" />
            <button class="btn" onclick="saveTopologyDevice()">Add Node to Topology</button>
          </div>
        </div>
      </div>
    </section>

    <!-- TEST JOBS SECTION -->
    <section id="sec-jobs" class="section">
      <div class="card">
        <div class="toolbar">
          <h3 style="margin:0">Test Job Execution History</h3>
          <button class="btn" onclick="runQuickTestSuite()">Trigger Sample HIL Suite</button>
        </div>
        <table>
          <thead>
            <tr>
              <th>Job ID</th>
              <th>Suite Name</th>
              <th>Device</th>
              <th>Owner</th>
              <th>Status</th>
              <th>Passed / Failed / Skipped</th>
            </tr>
          </thead>
          <tbody id="jobs-table-body"></tbody>
        </table>
      </div>
    </section>

    <!-- SETUP WIZARD SECTION -->
    <section id="sec-setup" class="section">
      <div class="card" style="max-width:680px">
        <h3 style="margin-top:0">Lab First-Run &amp; Global Configuration Wizard</h3>
        <label>Lab Name</label>
        <input id="cfg-lab-name" />
        <label>Lab Scope / Description</label>
        <input id="cfg-lab-scope" />
        <label>Primary Lab Subnet</label>
        <input id="cfg-subnet" />
        <label>Additional Subnets (comma-separated)</label>
        <input id="cfg-extra-subnets" />
        <label>Administrator Name</label>
        <input id="cfg-admin-name" />
        <label>Administrator Email</label>
        <input id="cfg-admin-email" />
        <label>SMTP Server</label>
        <input id="cfg-smtp" />
        <button class="btn" onclick="saveSettings()">Save Lab Configuration</button>
        <span id="cfg-saved-msg" style="margin-left:1rem; color:var(--green); display:none;">Saved!</span>
      </div>
    </section>
  </main>

  <script>
    let cachedDevices = [];
    let cachedTopology = { subnets: {}, devices: [], links: [] };
    let selectedNodeName = null;

    function switchTab(tab) {
      document.querySelectorAll('nav button').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
      document.getElementById('tab-' + tab).classList.add('active');
      document.getElementById('sec-' + tab).classList.add('active');
      if (tab === 'lab') renderTopology();
    }

    async function api(path, method = 'GET', body = null) {
      const opts = { method, headers: { 'Content-Type': 'application/json' } };
      if (body !== null) opts.body = JSON.stringify(body);
      const res = await fetch(path, opts);
      return await res.json();
    }

    async function refreshAll() {
      const [status, devResp, jobsResp, topoResp, settingsResp] = await Promise.all([
        api('/api/v1/status'),
        api('/api/v1/devices'),
        api('/api/v1/jobs'),
        api('/api/v1/topology'),
        api('/api/v1/settings')
      ]);

      document.getElementById('kpi-total').textContent = status.total_devices;
      document.getElementById('kpi-available').textContent = status.available_devices;
      document.getElementById('kpi-reserved').textContent = status.reserved_devices;
      document.getElementById('kpi-jobs').textContent = status.total_jobs;

      cachedDevices = devResp.devices || [];
      cachedTopology = topoResp;

      const dashBody = document.getElementById('dashboard-devices-body');
      const select = document.getElementById('quick-device');
      const currentVal = select.value;
      dashBody.innerHTML = '';
      select.innerHTML = '';
      cachedDevices.forEach(d => {
        const pillClass = 'pill-' + (d.state || 'available');
        const user = (d.transport_config && d.transport_config.user) || 'root';
        const port = (d.transport_config && d.transport_config.port) || 22;
        const endpoint = d.ip_address ? `${user}@${d.ip_address}:${port}` : 'local';
        dashBody.innerHTML += `<tr>
          <td><strong>${d.name}</strong></td>
          <td>${d.board_type} <span class="tag">${d.arch}</span></td>
          <td><code>${endpoint}</code> <span class="tag">${d.transport}</span></td>
          <td><span class="pill ${pillClass}">${d.state}</span></td>
          <td>${d.owner || '—'}</td>
        </tr>`;
        const opt = document.createElement('option');
        opt.value = d.name;
        opt.textContent = `${d.name} (${d.board_type} - ${d.ip_address || d.transport})`;
        select.appendChild(opt);
      });
      if (currentVal) select.value = currentVal;

      const devBody = document.getElementById('devices-table-body');
      devBody.innerHTML = '';
      cachedDevices.forEach(d => {
        const pillClass = 'pill-' + (d.state || 'available');
        const resBtn = d.state === 'reserved'
          ? `<button class="btn btn-secondary" onclick="releaseDevice('${d.name}')">Release</button>`
          : `<button class="btn" onclick="reserveDevice('${d.name}')">Reserve</button>`;
        const pwrAction = d.power_state === 'on' ? 'off' : 'on';
        const tagsHtml = (d.tags || []).map(t => `<span class="tag">${t}</span>`).join('');
        const osInfo = (d.attributes && d.attributes.os_info && d.attributes.os_info.pretty_name) || d.deployed_image || '—';
        const user = (d.transport_config && d.transport_config.user) || 'root';
        const port = (d.transport_config && d.transport_config.port) || 22;
        devBody.innerHTML += `<tr>
          <td><strong>${d.name}</strong><br/>${tagsHtml}</td>
          <td>${d.board_type} (${d.arch})<br/><small style="color:var(--muted)">${osInfo}</small></td>
          <td><code>${user}@${d.ip_address || 'local'}:${port}</code><br/><small style="color:var(--muted)">${d.subnet}</small></td>
          <td><span class="tag">${d.power_state}</span></td>
          <td><span class="pill ${pillClass}">${d.state}</span></td>
          <td style="display:flex; gap:0.35rem; flex-wrap:wrap;">
            ${resBtn}
            <button class="btn btn-secondary" onclick="connectDeviceSSH('${d.name}')">SSH Connect</button>
            <button class="btn btn-warning" onclick="rebootDeviceSSH('${d.name}')">Reboot (SSH)</button>
            <button class="btn btn-secondary" onclick="powerDevice('${d.name}', '${pwrAction}')">Power ${pwrAction.toUpperCase()}</button>
            <button class="btn btn-secondary" onclick="populateEdit('${d.name}')">Edit</button>
            <button class="btn btn-danger" onclick="deleteDevice('${d.name}')">Delete</button>
          </td>
        </tr>`;
      });

      const jobsBody = document.getElementById('jobs-table-body');
      jobsBody.innerHTML = '';
      (jobsResp.jobs || []).forEach(j => {
        const pill = j.status === 'PASS' ? 'pill-available' : 'pill-offline';
        jobsBody.innerHTML += `<tr>
          <td><code>${j.job_id}</code></td>
          <td>${j.suite_name}</td>
          <td>${j.device_name}</td>
          <td>${j.owner}</td>
          <td><span class="pill ${pill}">${j.status}</span></td>
          <td>${j.passed} / ${j.failed} / ${j.skipped}</td>
        </tr>`;
      });

      document.getElementById('header-lab-name').textContent = settingsResp.lab_name || 'DAMF';
      document.getElementById('cfg-lab-name').value = settingsResp.lab_name || '';
      document.getElementById('cfg-lab-scope').value = settingsResp.lab_scope || '';
      document.getElementById('cfg-subnet').value = settingsResp.primary_subnet || '';
      document.getElementById('cfg-extra-subnets').value = (settingsResp.additional_subnets || []).join(', ');
      document.getElementById('cfg-admin-name').value = settingsResp.admin_name || '';
      document.getElementById('cfg-admin-email').value = settingsResp.admin_email || '';
      document.getElementById('cfg-smtp').value = settingsResp.smtp_server || '';

      renderTopology();
      if (selectedNodeName) inspectNode(selectedNodeName);
    }

    function renderTopology() {
      const svg = document.getElementById('topology-svg');
      if (!svg) return;
      svg.innerHTML = '';
      const subnets = Object.entries(cachedTopology.subnets || {});
      const nodeCoords = {};

      subnets.forEach(([subnetName, devs], sIdx) => {
        const boxX = 20 + sIdx * 275;
        const boxY = 20;
        const boxW = 255;
        const boxH = 410;

        svg.innerHTML += `<rect x="${boxX}" y="${boxY}" width="${boxW}" height="${boxH}" rx="10"
          fill="#111c33" stroke="#334155" stroke-dasharray="5,4" />
          <text x="${boxX + 14}" y="${boxY + 26}" fill="#94a3b8" font-size="12" font-weight="bold">
            Subnet: ${subnetName}
          </text>`;

        devs.forEach((d, dIdx) => {
          const cx = boxX + 127;
          const cy = boxY + 82 + dIdx * 85;
          nodeCoords[d.name] = { x: cx, y: cy, device: d };
        });
      });

      (cachedTopology.links || []).forEach(link => {
        const a = nodeCoords[link.source];
        const b = nodeCoords[link.target];
        if (a && b) {
          svg.innerHTML += `<line x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}"
            stroke="#38bdf8" stroke-width="2" stroke-opacity="0.65" />`;
        }
      });

      Object.values(nodeCoords).forEach(({ x, y, device }) => {
        const strokeColor = device.state === 'reserved' ? '#f59e0b' : '#22c55e';
        svg.innerHTML += `<g style="cursor:pointer" onclick="inspectNode('${device.name}')">
          <rect x="${x - 98}" y="${y - 26}" width="196" height="52" rx="8"
            fill="#1e293b" stroke="${strokeColor}" stroke-width="2" />
          <text x="${x}" y="${y - 4}" text-anchor="middle" fill="#f8fafc" font-size="12.5" font-weight="bold">${device.name}</text>
          <text x="${x}" y="${y + 14}" text-anchor="middle" fill="#94a3b8" font-size="10.5">${device.board_type} • ${device.ip_address || device.transport}</text>
        </g>`;
      });
    }

    function inspectNode(name) {
      selectedNodeName = name;
      const d = cachedDevices.find(x => x.name === name);
      if (!d) return;
      const user = (d.transport_config && d.transport_config.user) || 'root';
      const port = (d.transport_config && d.transport_config.port) || 22;
      const osInfo = (d.attributes && d.attributes.os_info) || {};
      const lastReboot = (d.attributes && d.attributes.last_reboot_command) || osInfo.reboot_command || 'Auto-detect on reboot';
      const el = document.getElementById('node-inspector');
      el.innerHTML = `
        <h4 style="margin-top:0; color:var(--text)">${d.name}</h4>
        <p><strong>Board Type / Arch:</strong> ${d.board_type} (${d.arch})</p>
        <p><strong>SSH Endpoint:</strong> <code>ssh -p ${port} ${user}@${d.ip_address || 'local'}</code></p>
        <p><strong>Subnet:</strong> ${d.subnet}</p>
        <p><strong>State / Power:</strong> ${d.state} / ${d.power_state}</p>
        <p><strong>Detected OS:</strong> ${osInfo.pretty_name || d.deployed_image || 'Not probed yet'}</p>
        <p><strong>OS Reboot Cmd:</strong> <code>${lastReboot}</code></p>
        <p><strong>Connected Peers:</strong> ${(d.connected_to || []).join(', ') || 'None'}</p>
        <div style="display:flex; gap:0.4rem; flex-wrap:wrap; margin-top:0.65rem;">
          <button class="btn" onclick="connectDeviceSSH('${d.name}')">Connect SSH &amp; Probe OS</button>
          <button class="btn btn-warning" onclick="rebootDeviceSSH('${d.name}')">Reboot via SSH</button>
          <a class="btn btn-secondary" href="/api/v1/devices/${encodeURIComponent(d.name)}/export" target="_blank" style="text-decoration:none;">Export YAML</a>
        </div>
      `;
    }

    async function connectDeviceSSH(name) {
      const res = await api(`/api/v1/devices/${encodeURIComponent(name)}/connect`, 'POST', {});
      const os = res.os_info || {};
      document.getElementById('quick-output').textContent =
        `[SSH Connected to ${res.user}@${res.host}:${res.port}]\\n` +
        `Interactive CLI: ${res.interactive_cmd}\\n` +
        `Detected OS: ${os.pretty_name} (kernel=${os.kernel}, distro=${os.distro}, init=${os.init_system})\\n` +
        `Context Reboot Command: ${os.reboot_command}`;
      await refreshAll();
    }

    async function rebootDeviceSSH(name) {
      const res = await api(`/api/v1/devices/${encodeURIComponent(name)}/reboot`, 'POST', { via_ssh: true });
      const os = res.os_info || {};
      document.getElementById('quick-output').textContent =
        `[SSH Reboot Issued on ${name}]\\n` +
        `Detected OS: ${os.pretty_name || 'Linux'}\\n` +
        `Reboot Command Executed: ${res.reboot_command}\\n` +
        `${res.stdout || ''}`;
      await refreshAll();
    }

    async function connectSelectedSSH() {
      const dev = document.getElementById('quick-device').value;
      if (dev) await connectDeviceSSH(dev);
    }

    async function rebootSelectedSSH() {
      const dev = document.getElementById('quick-device').value;
      if (dev) await rebootDeviceSSH(dev);
    }

    async function reserveDevice(name) {
      await api(`/api/v1/devices/${encodeURIComponent(name)}/reserve`, 'POST', { owner: 'web-admin', ttl_seconds: 1800 });
      await refreshAll();
    }

    async function releaseDevice(name) {
      await api(`/api/v1/devices/${encodeURIComponent(name)}/release`, 'POST', {});
      await refreshAll();
    }

    async function powerDevice(name, action) {
      await api(`/api/v1/devices/${encodeURIComponent(name)}/power`, 'POST', { action });
      await refreshAll();
    }

    async function deleteDevice(name) {
      await api(`/api/v1/devices/${encodeURIComponent(name)}`, 'DELETE');
      await refreshAll();
    }

    function populateEdit(name) {
      const d = cachedDevices.find(x => x.name === name);
      if (!d) return;
      document.getElementById('dev-name').value = d.name;
      document.getElementById('dev-type').value = d.board_type;
      document.getElementById('dev-arch').value = d.arch;
      document.getElementById('dev-ip').value = d.ip_address;
      document.getElementById('dev-subnet').value = d.subnet;
      document.getElementById('dev-transport').value = d.transport;
      document.getElementById('dev-ssh-user').value = (d.transport_config && d.transport_config.user) || 'root';
      document.getElementById('dev-ssh-port').value = (d.transport_config && d.transport_config.port) || 22;
      document.getElementById('dev-ssh-key').value = (d.transport_config && d.transport_config.identity_file) || '';
      document.getElementById('dev-os-hint').value = (d.attributes && d.attributes.os) || '';
      document.getElementById('dev-simulated').checked = Boolean(d.transport_config && d.transport_config.simulated);
      document.getElementById('dev-tags').value = (d.tags || []).join(', ');
      document.getElementById('dev-peers').value = (d.connected_to || []).join(', ');
    }

    async function saveDevice() {
      const payload = {
        name: document.getElementById('dev-name').value.trim(),
        board_type: document.getElementById('dev-type').value.trim(),
        arch: document.getElementById('dev-arch').value.trim(),
        ip_address: document.getElementById('dev-ip').value.trim(),
        subnet: document.getElementById('dev-subnet').value.trim(),
        transport: document.getElementById('dev-transport').value,
        ssh_user: document.getElementById('dev-ssh-user').value.trim() || 'root',
        ssh_port: parseInt(document.getElementById('dev-ssh-port').value || '22', 10),
        identity_file: document.getElementById('dev-ssh-key').value.trim(),
        os_hint: document.getElementById('dev-os-hint').value.trim(),
        simulated: document.getElementById('dev-simulated').checked,
        tags: document.getElementById('dev-tags').value.split(',').map(s => s.trim()).filter(Boolean),
        connected_to: document.getElementById('dev-peers').value.split(',').map(s => s.trim()).filter(Boolean),
      };
      if (!payload.name) return;
      await api('/api/v1/devices', 'POST', payload);
      await refreshAll();
    }

    async function saveTopologyDevice() {
      const payload = {
        name: document.getElementById('topo-dev-name').value.trim(),
        board_type: document.getElementById('topo-dev-type').value.trim() || 'generic-linux',
        ip_address: document.getElementById('topo-dev-ip').value.trim(),
        subnet: document.getElementById('topo-dev-subnet').value.trim() || '192.168.10.0/24',
        ssh_user: document.getElementById('topo-dev-user').value.trim() || 'root',
        os_hint: document.getElementById('topo-dev-os').value.trim(),
        simulated: true,
        connected_to: document.getElementById('topo-dev-peers').value.split(',').map(s => s.trim()).filter(Boolean),
      };
      if (!payload.name) return;
      await api('/api/v1/topology/devices', 'POST', payload);
      selectedNodeName = payload.name;
      await refreshAll();
    }

    async function runQuickCommand() {
      const dev = document.getElementById('quick-device').value;
      const cmd = document.getElementById('quick-cmd').value;
      const res = await api(`/api/v1/devices/${encodeURIComponent(dev)}/exec`, 'POST', { command: cmd });
      document.getElementById('quick-output').textContent =
        `$ ${res.command}\\n[exit ${res.returncode} in ${res.duration_sec}s]\\n${res.stdout}${res.stderr || ''}`;
    }

    async function runQuickTestSuite() {
      const dev = document.getElementById('quick-device').value || (cachedDevices[0] && cachedDevices[0].name);
      if (!dev) return;
      const res = await api('/api/v1/jobs', 'POST', {
        device_name: dev,
        suite_name: 'hil-smoke-suite',
        owner: 'web-admin',
        commands: {
          'kernel_version_check': 'uname -r',
          'network_loopback_check': 'ip addr show lo',
          'storage_mount_check': 'df -h'
        }
      });
      document.getElementById('quick-output').textContent =
        `Suite ${res.suite_name} on ${dev}: ${res.passed} passed, ${res.failed} failed`;
      await refreshAll();
    }

    async function triggerDiscovery() {
      const res = await api('/api/v1/discover', 'POST', {});
      document.getElementById('quick-output').textContent =
        `Discovery scan complete. Found ${res.discovered_count} device(s).`;
      await refreshAll();
    }

    async function saveSettings() {
      await api('/api/v1/settings', 'POST', {
        lab_name: document.getElementById('cfg-lab-name').value,
        lab_scope: document.getElementById('cfg-lab-scope').value,
        primary_subnet: document.getElementById('cfg-subnet').value,
        additional_subnets: document.getElementById('cfg-extra-subnets').value.split(',').map(s => s.trim()).filter(Boolean),
        admin_name: document.getElementById('cfg-admin-name').value,
        admin_email: document.getElementById('cfg-admin-email').value,
        smtp_server: document.getElementById('cfg-smtp').value,
      });
      const msg = document.getElementById('cfg-saved-msg');
      msg.style.display = 'inline';
      setTimeout(() => { msg.style.display = 'none'; }, 2500);
      await refreshAll();
    }

    refreshAll();
  </script>
</body>
</html>
"""
