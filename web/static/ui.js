(function () {
  const API = (window.API_BASE || "/api").replace(/\/+$/, "");
  const $  = (sel) => document.querySelector(sel);
  const $$ = (sel) => Array.from(document.querySelectorAll(sel));

  // Elements
  const statusBadge = $("#status-badge");
  const btnStart    = $("#start-btn");
  const btnStop     = $("#stop-btn");
  const logOut      = $("#log-output");
  const logBox      = $(".log-container");
  const dhtPill     = $("#dht-pill");
  const stalledPill = $("#stalled-pill");

  // ----- View & Tabs -----
  const settingsSubnav  = $("#settings-subnav");
  const settingsNavItem = $(".nav-item[data-view='settings']");

  $$(".nav-item").forEach(b => b.addEventListener("click", () => {
    const view = b.dataset.view;

    if (view === "settings") {
      const isExpanded = settingsSubnav.classList.contains("expanded");
      if (isExpanded) {
        settingsSubnav.classList.remove("expanded");
        settingsNavItem.classList.remove("expanded");
      } else {
        settingsSubnav.classList.add("expanded");
        settingsNavItem.classList.add("expanded");
        $$(".nav-item").forEach(x => x.classList.remove("active"));
        b.classList.add("active");
        $$(".view").forEach(v => v.classList.toggle("visible", v.id === "view-settings"));
        if (!currentSection && Object.keys(settingsSchema).length > 0) {
          showSettingsSection(Object.keys(settingsSchema)[0]);
        }
      }
      return;
    }

    $$(".nav-item").forEach(x => x.classList.remove("active"));
    b.classList.add("active");
    $$(".view").forEach(v => v.classList.toggle("visible", v.id === `view-${view}`));
    settingsSubnav.classList.remove("expanded");
    settingsNavItem.classList.remove("expanded");
  }));

  // ----- Status -----
  function setRunningUI(running) {
    if (running) {
      statusBadge.textContent = "Running";
      statusBadge.className = "badge badge-running";
      btnStart.disabled = true; btnStop.disabled = false;
    } else {
      statusBadge.textContent = "Stopped";
      statusBadge.className = "badge badge-stopped";
      btnStart.disabled = false; btnStop.disabled = true;
    }
  }

  function formatUptime(sec) {
    if (!sec || sec <= 0) return "--";
    const h = Math.floor(sec / 3600);
    const m = Math.floor((sec % 3600) / 60);
    const s = sec % 60;
    if (h > 0) return `${h}h ${m}m`;
    if (m > 0) return `${m}m ${s}s`;
    return `${s}s`;
  }

  async function updateStatus() {
    try {
      const r = await fetch(`${API}/status`, {headers:{Accept:"application/json"}, cache:"no-store"});
      const d = r.ok ? await r.json() : {};
      const running = d.running === true;
      setRunningUI(running);

      // Update cards
      $("#card-status").textContent = running ? "Running" : "Stopped";
      $("#card-status").style.color = running ? "var(--ok)" : "var(--danger)";
      $("#card-uptime").textContent = running ? `Uptime: ${formatUptime(d.uptime)}` : "Not running";

      const dht = d.dht_nodes || 0;
      $("#card-dht").textContent = dht;
      $("#card-dht").style.color = dht > 0 ? "var(--ok)" : "var(--danger)";

      const stalled = d.stalled_count || 0;
      $("#card-stalled").textContent = stalled;
      $("#card-stalled").style.color = stalled > 0 ? "var(--warn)" : "var(--ok)";
      $("#card-restarts").textContent = `Restarts: ${d.restarts || 0} | Checks: ${d.checks || 0}`;

      // Header pills
      dhtPill.textContent = `DHT: ${dht}`;
      dhtPill.className = `stat-pill ${dht > 0 ? "ok" : "bad"}`;
      stalledPill.textContent = `Stalled: ${stalled}`;
      stalledPill.className = `stat-pill ${stalled > 0 ? "warn" : "ok"}`;

      // Sidebar info
      $("#sidebar-container").textContent = d.container || "--";
      $("#sidebar-interval").textContent = d.check_interval || "--";
    } catch {
      setRunningUI(false);
    }
  }

  // ----- Logs (byte-offset tail) -----
  let tailPos   = 0;
  let tailInode = null;

  function atBottom(){
    return logBox.scrollTop + logBox.clientHeight >= logBox.scrollHeight - 8;
  }
  function scrollToBottom(){ logBox.scrollTop = logBox.scrollHeight; }
  function appendText(txt){
    if (!txt) return;
    const stick = atBottom();
    logOut.textContent += txt.replace(/\r\n/g, "\n");
    const lines = logOut.textContent.split("\n");
    if (lines.length > 5000) logOut.textContent = lines.slice(-5000).join("\n");
    if (stick) scrollToBottom();
  }

  async function pollLogs(){
    try{
      const url = new URL(`${API}/logs/tail`, window.location.origin);
      url.searchParams.set("pos", String(tailPos));
      if (tailInode) url.searchParams.set("inode", tailInode);
      const r = await fetch(url, {headers:{Accept:"application/json"}, cache:"no-store"});
      if (!r.ok) return;
      const d = await r.json();
      if (d.reset || (tailInode && d.inode && d.inode !== tailInode)) {
        logOut.textContent = "";
      }
      if (typeof d.text === "string" && d.text.length) appendText(d.text);
      if (typeof d.pos === "number") tailPos = d.pos;
      if (d.inode) tailInode = d.inode;
    } catch {}
  }

  // ----- Events -----
  function formatTs(ts) {
    if (!ts) return "--";
    const d = new Date(ts * 1000);
    return d.toLocaleTimeString([], {hour:"2-digit", minute:"2-digit", second:"2-digit"});
  }

  async function loadEvents() {
    try {
      const r = await fetch(`${API}/events`, {headers:{Accept:"application/json"}, cache:"no-store"});
      if (!r.ok) return;
      const events = await r.json();
      const body = $("#events-body");

      if (!events.length) {
        body.innerHTML = `<tr><td colspan="4" class="empty-state">No events yet</td></tr>`;
        return;
      }

      body.innerHTML = events.slice(0, 50).map(e => `
        <tr>
          <td style="white-space:nowrap;font-size:12px;color:var(--muted)">${formatTs(e.ts)}</td>
          <td><span class="event-badge event-${e.type}">${e.type.replace(/_/g," ")}</span></td>
          <td style="font-size:13px">${escapeHtml(e.message)}</td>
          <td style="font-size:12px;color:var(--muted);max-width:250px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${escapeHtml(e.torrent || "")}</td>
        </tr>
      `).join("");
    } catch {}
  }

  // ----- Torrents -----
  function formatBytes(b) {
    if (!b || b <= 0) return "0 B";
    const units = ["B","KB","MB","GB","TB"];
    const i = Math.floor(Math.log(b) / Math.log(1024));
    return (b / Math.pow(1024, i)).toFixed(1) + " " + units[i];
  }

  function stateClass(state) {
    const s = (state || "").toLowerCase();
    if (s.includes("stalled")) return "stalled";
    if (s.includes("download")) return "downloading";
    if (s.includes("upload") || s.includes("seed")) return "seeding";
    if (s.includes("paused")) return "paused";
    if (s.includes("error") || s.includes("missing")) return "error";
    if (s.includes("meta") || s.includes("check")) return "metadl";
    return "";
  }

  async function loadTorrents() {
    try {
      const r = await fetch(`${API}/torrents`, {headers:{Accept:"application/json"}, cache:"no-store"});
      if (!r.ok) return;
      const torrents = await r.json();
      const body = $("#torrents-body");

      if (!torrents.length) {
        body.innerHTML = `<tr><td colspan="6" class="empty-state"><div class="empty-icon">&#128230;</div>No torrents</td></tr>`;
        return;
      }

      body.innerHTML = torrents.map(t => {
        const pct = ((t.progress || 0) * 100).toFixed(1);
        const sc = stateClass(t.state);
        return `
          <tr>
            <td style="max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${escapeHtml(t.name || "")}">${escapeHtml(t.name || "Unknown")}</td>
            <td><span class="torrent-state state-${sc}">${escapeHtml(t.state || "unknown")}</span></td>
            <td>${pct}%</td>
            <td style="white-space:nowrap">${formatBytes(t.dlspeed || 0)}/s</td>
            <td>${t.num_seeds || 0}</td>
            <td><button class="btn btn-sm" data-action="reannounce" data-hash="${t.hash}">Reannounce</button></td>
          </tr>
        `;
      }).join("");
    } catch {}
  }

  // ----- Actions -----
  btnStart.addEventListener("click", async () => {
    btnStart.disabled = true;
    try {
      await fetch(`${API}/start`, {method:"POST"});
      await updateStatus();
    } catch {}
  });

  btnStop.addEventListener("click", async () => {
    btnStop.disabled = true;
    try {
      await fetch(`${API}/stop`, {method:"POST"});
      await updateStatus();
    } catch {}
  });

  $("#clear-log").addEventListener("click", () => {
    logOut.textContent = "";
  });

  $("#refresh-events").addEventListener("click", () => loadEvents());
  $("#refresh-torrents").addEventListener("click", () => loadTorrents());

  $("#restart-qbit-btn").addEventListener("click", async () => {
    if (!confirm("Restart qBittorrent container?")) return;
    try {
      const r = await fetch(`${API}/restart-qbit`, {method:"POST"});
      const d = await r.json();
      showToast(d.ok ? "success" : "error", d.message || d.error || "Unknown result");
    } catch (e) {
      showToast("error", "Request failed");
    }
  });

  // Delegate reannounce clicks
  document.addEventListener("click", async (e) => {
    const btn = e.target.closest("[data-action='reannounce']");
    if (!btn) return;
    const hash = btn.dataset.hash;
    btn.disabled = true;
    try {
      await fetch(`${API}/reannounce`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({hash}),
      });
      showToast("success", "Reannounce sent");
    } catch {
      showToast("error", "Reannounce failed");
    }
    setTimeout(() => btn.disabled = false, 2000);
  });

  // ----- Settings -----
  let settingsSchema = {};
  let settingsOriginal = {};
  let settingsModified = {};
  let currentSection = null;

  async function loadSettings() {
    const container = $("#settings-container");
    const navContainer = $("#settings-subnav");
    container.innerHTML = `<div style="padding:40px;text-align:center;color:var(--muted)">Loading...</div>`;
    navContainer.innerHTML = "";

    try {
      const r = await fetch(`${API}/settings`, {headers:{Accept:"application/json"}});
      const data = await r.json();

      if (!r.ok || data.error) {
        throw new Error(data.error || `HTTP ${r.status}`);
      }

      settingsSchema = data.schema;
      settingsOriginal = {...data.values};
      settingsModified = {...data.values};

      renderSettingsNav();
      const firstSection = Object.keys(settingsSchema)[0];
      if (firstSection) showSettingsSection(firstSection);
    } catch (e) {
      container.innerHTML = `<div style="padding:40px;text-align:center;color:var(--danger)">Failed to load: ${e.message}</div>`;
    }
  }

  function renderSettingsNav() {
    const navContainer = $("#settings-subnav");
    navContainer.innerHTML = "";

    for (const [sectionKey, section] of Object.entries(settingsSchema)) {
      const btn = document.createElement("button");
      btn.className = "nav-subitem";
      btn.dataset.section = sectionKey;
      btn.textContent = section.label;
      btn.addEventListener("click", () => {
        $$(".nav-item").forEach(x => x.classList.remove("active"));
        settingsNavItem.classList.add("active");
        $$(".view").forEach(v => v.classList.toggle("visible", v.id === "view-settings"));
        showSettingsSection(sectionKey);
      });
      navContainer.appendChild(btn);
    }
  }

  function showSettingsSection(sectionKey) {
    currentSection = sectionKey;
    const section = settingsSchema[sectionKey];
    if (!section) return;

    $$(".nav-subitem").forEach(btn => {
      btn.classList.toggle("active", btn.dataset.section === sectionKey);
    });

    $("#settings-section-title").textContent = section.label;

    const container = $("#settings-container");
    container.innerHTML = "";

    const fieldsDiv = document.createElement("div");
    fieldsDiv.className = "settings-fields";

    for (const [fieldKey, field] of Object.entries(section.fields)) {
      const value = settingsModified[fieldKey] || "";
      const isModified = settingsModified[fieldKey] !== settingsOriginal[fieldKey];
      const isPassword = field.type === "password";
      const isSelect = field.type === "select";

      const fieldEl = document.createElement("div");
      fieldEl.className = `setting-field${isModified ? " modified" : ""}`;
      fieldEl.dataset.key = fieldKey;

      if (isSelect) {
        const optionsHtml = (field.options || []).map(opt =>
          `<option value="${escapeHtml(opt.value)}"${opt.value === value ? " selected" : ""}>${escapeHtml(opt.label)}</option>`
        ).join("");

        fieldEl.innerHTML = `
          <label for="set-${fieldKey}">${field.label}</label>
          <div class="input-wrap">
            <select id="set-${fieldKey}" data-key="${fieldKey}">${optionsHtml}</select>
          </div>
        `;
        fieldsDiv.appendChild(fieldEl);

        const select = fieldEl.querySelector("select");
        select.addEventListener("change", (e) => {
          settingsModified[fieldKey] = e.target.value;
          updateSettingsUI();
        });
      } else {
        fieldEl.innerHTML = `
          <label for="set-${fieldKey}">${field.label}</label>
          <div class="input-wrap">
            <input type="${isPassword ? "password" : "text"}"
                   id="set-${fieldKey}"
                   data-key="${fieldKey}"
                   placeholder="${field.placeholder || ""}"
                   value="${escapeHtml(value)}"
                   autocomplete="off">
            ${isPassword ? `<button type="button" class="btn-reveal" data-for="set-${fieldKey}">Show</button>` : ""}
          </div>
        `;
        fieldsDiv.appendChild(fieldEl);

        const input = fieldEl.querySelector("input");
        input.addEventListener("input", (e) => {
          settingsModified[fieldKey] = e.target.value;
          updateSettingsUI();
        });

        if (isPassword) {
          const revealBtn = fieldEl.querySelector(".btn-reveal");
          revealBtn.addEventListener("click", () => {
            const isHidden = input.type === "password";
            input.type = isHidden ? "text" : "password";
            revealBtn.textContent = isHidden ? "Hide" : "Show";
          });
        }
      }
    }

    container.appendChild(fieldsDiv);
  }

  function updateSettingsUI() {
    for (const [key, val] of Object.entries(settingsModified)) {
      const el = $(`.setting-field[data-key="${key}"]`);
      if (!el) continue;
      const isModified = val !== settingsOriginal[key];
      el.classList.toggle("modified", isModified);
    }
  }

  $("#save-settings").addEventListener("click", async () => {
    const statusEl = $("#settings-status");
    statusEl.textContent = "Saving...";
    statusEl.className = "settings-status";

    try {
      const r = await fetch(`${API}/settings`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(settingsModified),
      });
      const d = await r.json();

      if (r.ok && d.status === "ok") {
        settingsOriginal = {...settingsModified};
        updateSettingsUI();
        statusEl.textContent = d.message || "Saved!";
        statusEl.className = "settings-status success";
        showToast("success", "Settings saved");
      } else {
        statusEl.textContent = d.message || "Error saving";
        statusEl.className = "settings-status error";
      }
    } catch (e) {
      statusEl.textContent = "Save failed";
      statusEl.className = "settings-status error";
    }

    setTimeout(() => { statusEl.textContent = ""; statusEl.className = "settings-status"; }, 4000);
  });

  // ----- Toast -----
  function showToast(type, message) {
    const existing = $(".toast");
    if (existing) existing.remove();

    const toast = document.createElement("div");
    toast.className = `toast ${type}`;
    toast.textContent = message;
    document.body.appendChild(toast);

    setTimeout(() => {
      toast.classList.add("fade-out");
      setTimeout(() => toast.remove(), 300);
    }, 3000);
  }

  // ----- Utils -----
  function escapeHtml(str) {
    if (!str) return "";
    return String(str).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
  }

  // ----- Polling -----
  async function tick() {
    await updateStatus();
    await pollLogs();
  }

  // Initial load
  updateStatus();
  loadEvents();
  loadTorrents();
  loadSettings();

  // Periodic
  setInterval(tick, 3000);
  setInterval(loadEvents, 15000);
  setInterval(loadTorrents, 10000);

})();
