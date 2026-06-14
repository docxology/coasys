// Weave — the visual language surface.
// Views over one Weave document, all derived from /api/weave/*:
//   * Topology : an INTERACTIVE network graph (force / waves layouts, drag,
//                zoom, pan, hover-highlight, edge + tier filters).
//   * Schema   : schema-driven forms with auto-save.
//   * Deploy   : deployment-readiness + rollout.
// Styled with the real coasys/we design tokens (--we-*), so the picture is the
// WE design language applied to the fleet's setup/deployment topology.

const SVGNS = "http://www.w3.org/2000/svg";

const weaveState = {
  loaded: false,
  graph: null,
  document: null,
  edited: null,
  targets: [],
  issues: [],
  tab: "graph",
  topo: {
    layout: "waves",
    pos: {},
    view: { x: 0, y: 0, k: 1 },
    edges: { needs: true, "deploy-needs": true, uses: true, "deploy-to": true },
    tier: "",
    built: false,
    width: 900,
    height: 470,
    drag: null,
    pan: null,
  },
};

const KNOWN_TIERS = ["core", "active", "language", "dependency-fork", "stale", "unknown"];

const wq = (sel) => document.querySelector(sel);
const svgEl = (tag, attrs) => {
  const node = document.createElementNS(SVGNS, tag);
  for (const [k, v] of Object.entries(attrs || {})) node.setAttribute(k, v);
  return node;
};
function cssVar(name, fallback) {
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v || fallback;
}
function tierColor(tier) {
  return cssVar(`--we-tier-${tier || "unknown"}`, "#56606a");
}

async function getJson(url, options) {
  const response = await fetch(url, options);
  if (!response.ok) throw new Error(`${response.status} ${await response.text()}`);
  return response.json();
}
function clone(value) {
  return JSON.parse(JSON.stringify(value));
}

// --------------------------------------------------------------------------
// Loading
// --------------------------------------------------------------------------

async function loadWeave() {
  const [docPayload, graph] = await Promise.all([
    getJson("/api/weave/document"),
    getJson("/api/weave/graph"),
  ]);
  weaveState.document = docPayload.document;
  weaveState.edited = clone(docPayload.document);
  weaveState.issues = docPayload.issues || [];
  weaveState.targets = docPayload.targets || [];
  weaveState.graph = graph;
  weaveState.loaded = true;
  weaveState.topo.built = false;
  weaveState.topo.pos = {};
  populateTierFilter();
  renderIssues(weaveState.issues);
  renderWeaveTab();
}

function renderWeaveTab() {
  const tab = weaveState.tab;
  wq("#weave-graph").classList.toggle("active", tab === "graph");
  wq("#weave-schema").classList.toggle("active", tab === "schema");
  wq("#weave-deploy").classList.toggle("active", tab === "deploy");
  document.querySelectorAll(".weave-tab").forEach((node) => {
    node.classList.toggle("active", node.dataset.weaveTab === tab);
  });
  if (tab === "graph") renderTopology();
  else if (tab === "schema") renderSchema();
  else renderDeploy();
}

function renderIssues(issues) {
  const box = wq("#weave-issues");
  if (!issues || !issues.length) {
    box.innerHTML = '<span class="weave-ok">✓ document valid — no issues</span>';
    return;
  }
  box.innerHTML = issues
    .map(
      (issue) =>
        `<div class="weave-issue ${issue.level}"><strong>${issue.level}</strong>
         <code>${issue.code}</code> ${issue.message}
         ${issue.path ? `<span class="muted">${issue.path}</span>` : ""}</div>`,
    )
    .join("");
}

// --------------------------------------------------------------------------
// Interactive topology
// --------------------------------------------------------------------------

const EDGE_STYLE = {
  needs: { color: "--we-edge-needs", w: 1.5, dash: "", marker: "arrow" },
  "deploy-needs": { color: "--we-edge-deploy", w: 1.7, dash: "5 4", marker: "arrowD" },
  uses: { color: "--we-edge-uses", w: 2.6, dash: "", marker: "arrowU" },
  "deploy-to": { color: "--we-edge-deploy-to", w: 1.7, dash: "2 4", marker: "arrowT" },
};

function nodeRadius(node) {
  return node.kind === "repo" ? 66 : 56; // half-width for edge trimming
}

function computeWaveLayout(graph, W, H) {
  const waveOf = {};
  (graph.build_waves || []).forEach((wave, i) => wave.forEach((r) => (waveOf[r] = i)));
  const maxWave = (graph.build_waves || []).length - 1;
  const rawCol = {};
  graph.nodes.forEach((n) => {
    if (n.kind === "seed") rawCol[n.id] = 0;
    else if (n.kind === "repo") rawCol[n.id] = 2 + (waveOf[n.label] ?? maxWave + 1);
    else rawCol[n.id] = 2 + maxWave + 2;
  });
  const used = [...new Set(Object.values(rawCol))].sort((a, b) => a - b);
  const colIndex = Object.fromEntries(used.map((c, i) => [c, i]));
  const columns = {};
  graph.nodes.forEach((n) => (columns[colIndex[rawCol[n.id]]] ||= []).push(n));
  const colW = Math.max(170, W / used.length);
  const pos = {};
  Object.entries(columns).forEach(([c, nodes]) => {
    const col = Number(c);
    const step = H / (nodes.length + 1);
    nodes
      .slice()
      .sort((a, b) => a.label.localeCompare(b.label))
      .forEach((n, row) => {
        pos[n.id] = { x: colW * (col + 0.5), y: step * (row + 1) };
      });
  });
  return pos;
}

function computeForceLayout(graph, W, H, seed) {
  const nodes = graph.nodes.map((n) => ({
    id: n.id,
    x: seed[n.id]?.x ?? W / 2 + (Math.random() - 0.5) * W * 0.6,
    y: seed[n.id]?.y ?? H / 2 + (Math.random() - 0.5) * H * 0.6,
  }));
  const idx = Object.fromEntries(nodes.map((n, i) => [n.id, i]));
  const links = graph.edges.filter((e) => idx[e.source] != null && idx[e.target] != null);
  const cx = W / 2;
  const cy = H / 2;
  for (let it = 0; it < 320; it++) {
    const cool = 1 - it / 380;
    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        let dx = nodes[i].x - nodes[j].x;
        let dy = nodes[i].y - nodes[j].y;
        const d2 = dx * dx + dy * dy || 0.01;
        const d = Math.sqrt(d2);
        const f = (5200 / d2) * cool;
        nodes[i].x += (dx / d) * f;
        nodes[i].y += (dy / d) * f;
        nodes[j].x -= (dx / d) * f;
        nodes[j].y -= (dy / d) * f;
      }
    }
    for (const e of links) {
      const a = nodes[idx[e.source]];
      const b = nodes[idx[e.target]];
      let dx = b.x - a.x;
      let dy = b.y - a.y;
      const d = Math.sqrt(dx * dx + dy * dy) || 0.01;
      const f = (d - 135) * 0.025 * cool;
      a.x += (dx / d) * f;
      a.y += (dy / d) * f;
      b.x -= (dx / d) * f;
      b.y -= (dy / d) * f;
    }
    for (const n of nodes) {
      n.x += (cx - n.x) * 0.005 * cool;
      n.y += (cy - n.y) * 0.005 * cool;
    }
  }
  const pos = {};
  for (const n of nodes) {
    pos[n.id] = { x: Math.max(40, Math.min(W - 40, n.x)), y: Math.max(34, Math.min(H - 34, n.y)) };
  }
  return pos;
}

function renderTopology() {
  const graph = weaveState.graph;
  const topo = weaveState.topo;
  const wrap = wq("#weave-svg");
  topo.width = Math.max(640, wrap.clientWidth || 900);

  // Targets ribbon.
  wq("#weave-targets").innerHTML =
    `<span class="weave-targets-label">Targets →</span> ` +
    weaveState.targets
      .map((n, i) => `<span class="weave-target" data-node="repo:${n}">${i + 1}. ${n}</span>`)
      .join("");

  // Layout.
  if (!topo.built || Object.keys(topo.pos).length === 0) {
    topo.pos =
      topo.layout === "force"
        ? computeForceLayout(graph, topo.width, topo.height, topo.pos)
        : computeWaveLayout(graph, topo.width, topo.height);
  }

  // Build SVG skeleton.
  const defs = Object.entries(EDGE_STYLE)
    .map(
      ([, s]) =>
        `<marker id="${s.marker}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10 z" fill="${cssVar(s.color, "#888")}"/></marker>`,
    )
    .join("");
  wrap.innerHTML = `<svg id="weave-topo-svg" viewBox="0 0 ${topo.width} ${topo.height}" width="100%" height="${topo.height}" role="img" aria-label="Interactive fleet topology"><defs>${defs}</defs><g id="weave-vp"><g id="weave-edges"></g><g id="weave-nodes"></g></g></svg>`;

  const edgesG = wq("#weave-edges");
  graph.edges.forEach((e, i) => {
    if (!topo.edges[e.kind]) return;
    const s = EDGE_STYLE[e.kind] || EDGE_STYLE.needs;
    const path = svgEl("path", {
      class: "weave-edge",
      "data-edge": i,
      "data-source": e.source,
      "data-target": e.target,
      fill: "none",
      stroke: cssVar(s.color, "#888"),
      "stroke-width": s.w,
      "stroke-dasharray": s.dash,
      "marker-end": `url(#${s.marker})`,
    });
    edgesG.appendChild(path);
  });

  const nodesG = wq("#weave-nodes");
  graph.nodes.forEach((n) => {
    const g = svgEl("g", { class: "topo-node", "data-id": n.id, "data-kind": n.kind, "data-tier": n.tier || "" });
    const isRepo = n.kind === "repo";
    const w = isRepo ? 132 : 116;
    const h = isRepo ? 38 : 34;
    const rx = n.kind === "seed" ? 17 : n.kind === "environment" ? 4 : 9;
    let fill = cssVar("--we-seed", "#8c4a12");
    if (isRepo) fill = tierColor(n.tier);
    else if (n.kind === "environment") fill = cssVar("--we-environment", "#4a5a6a");
    if (n.target) {
      g.appendChild(svgEl("rect", { class: "topo-ring", x: -w / 2 - 3, y: -h / 2 - 3, width: w + 6, height: h + 6, rx: rx + 3, fill: "none" }));
    }
    g.appendChild(svgEl("rect", { class: "topo-box", x: -w / 2, y: -h / 2, width: w, height: h, rx, fill }));
    const label = svgEl("text", { class: "topo-label", "text-anchor": "middle", y: 4 });
    label.textContent = n.label;
    g.appendChild(label);
    if (n.deployable) g.appendChild(svgEl("circle", { class: "topo-badge", cx: w / 2 - 9, cy: -h / 2 + 9, r: 4, fill: cssVar("--we-edge-deploy", "#c0392b") }));
    if (n.has_we_app) g.appendChild(svgEl("circle", { cx: w / 2 - 20, cy: -h / 2 + 9, r: 4, fill: cssVar("--we-color-primary-100", "#bfe3d6") }));
    if (n.profiles && n.profiles.includes("setup"))
      g.appendChild(svgEl("circle", { cx: -w / 2 + 9, cy: -h / 2 + 9, r: 4, fill: cssVar("--we-color-warning-500", "#e0a000") }));
    nodesG.appendChild(g);
    g.addEventListener("pointerdown", (ev) => startNodeDrag(ev, n.id));
    g.addEventListener("click", () => showNode(n.id));
    g.addEventListener("mouseenter", () => highlightNeighbors(n.id));
    g.addEventListener("mouseleave", clearHighlight);
  });

  positionAll();
  applyView();
  attachTopoHandlers();
  applyTierFilter();
  renderLegend();
}

function positionAll() {
  const pos = weaveState.topo.pos;
  document.querySelectorAll("#weave-nodes .topo-node").forEach((g) => {
    const p = pos[g.dataset.id];
    if (p) g.setAttribute("transform", `translate(${p.x} ${p.y})`);
  });
  updateEdges();
}

function updateEdges() {
  const pos = weaveState.topo.pos;
  document.querySelectorAll("#weave-edges .weave-edge").forEach((path) => {
    const a = pos[path.dataset.source];
    const b = pos[path.dataset.target];
    if (!a || !b) return;
    const dx = b.x - a.x;
    const dy = b.y - a.y;
    const d = Math.hypot(dx, dy) || 1;
    const tx = b.x - (dx / d) * 30; // trim to node border for arrowhead
    const ty = b.y - (dy / d) * 30;
    const mx = (a.x + tx) / 2 + dy * 0.08;
    const my = (a.y + ty) / 2 - dx * 0.08;
    path.setAttribute("d", `M ${a.x} ${a.y} Q ${mx} ${my} ${tx} ${ty}`);
  });
}

function applyView() {
  const { x, y, k } = weaveState.topo.view;
  const vp = wq("#weave-vp");
  if (vp) vp.setAttribute("transform", `translate(${x} ${y}) scale(${k})`);
}

function attachTopoHandlers() {
  const svg = wq("#weave-topo-svg");
  if (!svg || svg.dataset.wired) return;
  svg.dataset.wired = "1";
  svg.addEventListener("pointerdown", (e) => {
    if (e.target.closest(".topo-node")) return; // node drag handles itself
    weaveState.topo.pan = { x: e.clientX, y: e.clientY, vx: weaveState.topo.view.x, vy: weaveState.topo.view.y };
  });
  window.addEventListener("pointermove", onTopoMove);
  window.addEventListener("pointerup", () => {
    weaveState.topo.drag = null;
    weaveState.topo.pan = null;
  });
  svg.addEventListener("wheel", (e) => {
    e.preventDefault();
    const view = weaveState.topo.view;
    const rect = svg.getBoundingClientRect();
    const scaleX = weaveState.topo.width / rect.width;
    const px = (e.clientX - rect.left) * scaleX;
    const py = (e.clientY - rect.top) * scaleX;
    const factor = e.deltaY < 0 ? 1.12 : 1 / 1.12;
    const nk = Math.max(0.3, Math.min(3, view.k * factor));
    view.x = px - ((px - view.x) * nk) / view.k;
    view.y = py - ((py - view.y) * nk) / view.k;
    view.k = nk;
    applyView();
  }, { passive: false });
}

function startNodeDrag(ev, id) {
  ev.stopPropagation();
  weaveState.topo.drag = { id, moved: false };
}

function onTopoMove(e) {
  const topo = weaveState.topo;
  const svg = wq("#weave-topo-svg");
  if (!svg) return;
  const rect = svg.getBoundingClientRect();
  const scale = topo.width / rect.width;
  if (topo.drag) {
    const p = topo.pos[topo.drag.id];
    if (!p) return;
    p.x += (e.movementX * scale) / topo.view.k;
    p.y += (e.movementY * scale) / topo.view.k;
    const g = document.querySelector(`.topo-node[data-id="${cssEscape(topo.drag.id)}"]`);
    if (g) g.setAttribute("transform", `translate(${p.x} ${p.y})`);
    updateEdges();
  } else if (topo.pan) {
    topo.view.x = topo.pan.vx + (e.clientX - topo.pan.x) * scale;
    topo.view.y = topo.pan.vy + (e.clientY - topo.pan.y) * scale;
    applyView();
  }
}

function cssEscape(s) {
  return s.replace(/[^a-zA-Z0-9_-]/g, "\\$&");
}

function neighborsOf(id) {
  const set = new Set([id]);
  weaveState.graph.edges.forEach((e) => {
    if (e.source === id) set.add(e.target);
    if (e.target === id) set.add(e.source);
  });
  return set;
}

function highlightNeighbors(id) {
  const near = neighborsOf(id);
  const svg = wq("#weave-topo-svg");
  svg.classList.add("topo-dimming");
  document.querySelectorAll("#weave-nodes .topo-node").forEach((g) => {
    g.classList.toggle("hot", near.has(g.dataset.id));
  });
  document.querySelectorAll("#weave-edges .weave-edge").forEach((p) => {
    p.classList.toggle("hot", p.dataset.source === id || p.dataset.target === id);
  });
}
function clearHighlight() {
  const svg = wq("#weave-topo-svg");
  if (svg) svg.classList.remove("topo-dimming");
  document.querySelectorAll(".topo-node.hot, .weave-edge.hot").forEach((n) => n.classList.remove("hot"));
}

function applyTierFilter() {
  const tier = weaveState.topo.tier;
  document.querySelectorAll("#weave-nodes .topo-node").forEach((g) => {
    const repo = g.dataset.kind === "repo";
    g.classList.toggle("tier-dim", !!tier && repo && g.dataset.tier !== tier);
  });
}

function renderLegend() {
  wq("#weave-legend").innerHTML = `
    <span class="weave-leg"><i class="sw" style="background:var(--we-tier-core)"></i>core</span>
    <span class="weave-leg"><i class="sw" style="background:var(--we-tier-active)"></i>active</span>
    <span class="weave-leg"><i class="sw" style="background:var(--we-tier-language)"></i>language</span>
    <span class="weave-leg"><i class="sw" style="background:var(--we-seed)"></i>seed</span>
    <span class="weave-leg"><i class="sw" style="background:var(--we-environment)"></i>environment</span>
    <span class="weave-leg"><i class="ring"></i>target</span>
    <span class="weave-leg"><i class="dot" style="background:var(--we-color-warning-500)"></i>has setup</span>
    <span class="weave-leg"><i class="dot" style="background:var(--we-edge-deploy)"></i>deployable</span>
    <span class="weave-leg muted">drag nodes · scroll to zoom · drag bg to pan · hover to focus</span>`;
}

function showNode(nodeId) {
  if (weaveState.topo.drag) return;
  const node = weaveState.graph.nodes.find((n) => n.id === nodeId);
  if (!node) return;
  const panel = wq("#weave-node");
  if (node.kind === "seed") {
    panel.innerHTML = `<h3>${node.label} <span class="pill">seed</span></h3>
      <p class="muted">${node.project} · ${node.app_count} app(s)</p>
      <button class="weave-seed-view" data-seed="${node.label}">View we-seed.json</button>`;
  } else if (node.kind === "environment") {
    panel.innerHTML = `<h3>${node.label} <span class="pill">environment</span></h3>
      <p>${node.protected ? "🔒 protected" : "unprotected"}</p>
      <p class="muted">requires: ${(node.requires_env || []).join(", ") || "none"}</p>`;
  } else {
    const repo = weaveState.document.repos[node.label] || {};
    panel.innerHTML = `<h3>${node.label} <span class="pill" style="background:${tierColor(node.tier)};color:#fff">${node.tier || "?"}</span></h3>
      <p class="muted">${repo.description || ""}</p>
      <p><strong>Priority:</strong> ${node.priority} ${node.target ? "· ⭐ target" : ""}</p>
      <p><strong>Stack:</strong> ${(node.stack || []).join(", ") || "—"}</p>
      <p><strong>Lifecycle:</strong> ${(node.profiles || []).map((p) => `<span class="pill configured">${p}</span>`).join(" ") || "—"}</p>
      <p><strong>Needs:</strong> ${(repo.needs || []).join(", ") || "—"}</p>
      ${node.has_we_app ? `<p><strong>WE app:</strong> ${repo.we.app.id} → <code>${repo.we.app.route}</code></p>` : ""}
      ${node.deployable ? `<p>🚀 deployable</p>` : ""}`;
  }
  panel.classList.add("active");
  document.querySelectorAll(".weave-seed-view").forEach((b) =>
    b.addEventListener("click", () => window.open(`/api/weave/seed/${b.dataset.seed}`, "_blank")),
  );
}

function populateTierFilter() {
  const sel = wq("#weave-tier-filter");
  if (!sel) return;
  const present = [...new Set(Object.values(weaveState.document.repos || {}).map((r) => r.tier).filter(Boolean))];
  sel.innerHTML = '<option value="">all tiers</option>' + present.map((t) => `<option value="${t}">${t}</option>`).join("");
}

function relayout() {
  const topo = weaveState.topo;
  topo.pos =
    topo.layout === "force"
      ? computeForceLayout(weaveState.graph, topo.width, topo.height, {})
      : computeWaveLayout(weaveState.graph, topo.width, topo.height);
  positionAll();
}

// --------------------------------------------------------------------------
// Schema view (form-driven editor)
// --------------------------------------------------------------------------

function csv(list) {
  return (list || []).join(", ");
}
function parseCsv(value) {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

let saveTimer = null;

function setSaveStatus(text, kind) {
  const node = wq("#weave-edit-status");
  node.textContent = text;
  node.className = "weave-save-status " + (kind || "");
}

function markEdited() {
  setSaveStatus("● unsaved", "dirty");
  if (wq("#weave-autosave").checked) {
    clearTimeout(saveTimer);
    saveTimer = setTimeout(saveDocument, 700);
  }
}

async function saveDocument() {
  clearTimeout(saveTimer);
  setSaveStatus("saving…", "saving");
  let result;
  try {
    result = await getJson("/api/weave/document", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(weaveState.edited),
    });
  } catch (error) {
    setSaveStatus("save failed: " + error.message, "error");
    return;
  }
  if (result.parse_error) {
    setSaveStatus("parse error", "error");
    renderIssues([{ level: "error", code: "parse", message: result.parse_error, path: "" }]);
    return;
  }
  renderIssues(result.issues);
  if (result.saved) {
    weaveState.document = clone(weaveState.edited);
    weaveState.issues = result.issues;
    const time = new Date().toLocaleTimeString();
    setSaveStatus(`saved ✓ ${time}`, "saved");
    try {
      weaveState.graph = await getJson("/api/weave/graph");
      const docPayload = await getJson("/api/weave/document");
      weaveState.targets = docPayload.targets || [];
      weaveState.topo.built = false;
      weaveState.topo.pos = {};
    } catch (_) {
      /* non-fatal */
    }
  } else {
    setSaveStatus("not saved — fix errors", "error");
  }
}

function renderSchema() {
  const doc = weaveState.edited;
  const seeds = Object.entries(doc.seeds || {});
  wq("#weave-seeds").innerHTML = seeds.length
    ? `<h2>Seeds</h2>` +
      seeds
        .map(
          ([name, seed]) => `
        <div class="weave-seed-card">
          <strong>${name}</strong>
          <span class="muted">${seed.project?.name || ""} · ${(seed.apps || []).length} app(s)</span>
          <button class="weave-seed-view" data-seed="${name}">we-seed.json</button>
        </div>`,
        )
        .join("")
    : "";

  const repos = Object.entries(doc.repos || {});
  wq("#weave-forms").innerHTML =
    `<h2>Repositories (${repos.length})</h2>` +
    repos
      .map(([name, repo]) => {
        const tierOptions = KNOWN_TIERS.map(
          (t) => `<option value="${t}" ${repo.tier === t ? "selected" : ""}>${t}</option>`,
        ).join("");
        const profiles = Object.entries(repo.playbooks || {})
          .map(
            ([profile, pb]) =>
              `<details><summary>${profile}</summary><pre>${(pb.run || []).join("\n") || "—"}</pre>
               ${pb.check ? `<pre class="muted">check: ${(pb.check || []).join("; ")}</pre>` : ""}</details>`,
          )
          .join("");
        const weApp = repo.we?.app
          ? `<label>WE route<input data-repo="${name}" data-field="we-route" value="${repo.we.app.route || ""}"></label>`
          : "";
        return `
          <div class="weave-card" style="border-left:4px solid ${tierColor(repo.tier)}">
            <div class="weave-card-head"><strong>${name}</strong>
              <label class="weave-inline"><input type="checkbox" data-repo="${name}" data-field="target" ${repo.target ? "checked" : ""}/> target</label>
            </div>
            <div class="weave-fields">
              <label>tier<select data-repo="${name}" data-field="tier">${tierOptions}</select></label>
              <label>priority<input type="number" data-repo="${name}" data-field="priority" value="${repo.priority || 0}"></label>
              <label>needs<input data-repo="${name}" data-field="needs" value="${csv(repo.needs)}"></label>
              <label>stack<input data-repo="${name}" data-field="stack" value="${csv(repo.stack)}"></label>
              ${weApp}
            </div>
            <div class="weave-profiles">${profiles || '<span class="muted">no playbooks</span>'}</div>
          </div>`;
      })
      .join("");

  document.querySelectorAll("[data-repo][data-field]").forEach((input) => {
    const event = input.type === "checkbox" || input.tagName === "SELECT" ? "change" : "input";
    input.addEventListener(event, () => applyEdit(input));
  });
  document.querySelectorAll(".weave-seed-view").forEach((b) =>
    b.addEventListener("click", () => window.open(`/api/weave/seed/${b.dataset.seed}`, "_blank")),
  );
}

function applyEdit(input) {
  const repo = weaveState.edited.repos[input.dataset.repo];
  if (!repo) return;
  const field = input.dataset.field;
  if (field === "target") repo.target = input.checked;
  else if (field === "priority") repo.priority = Number(input.value) || 0;
  else if (field === "tier") repo.tier = input.value;
  else if (field === "needs") repo.needs = parseCsv(input.value);
  else if (field === "stack") repo.stack = parseCsv(input.value);
  else if (field === "we-route" && repo.we?.app) repo.we.app.route = input.value;
  markEdited();
}

async function validateEdits() {
  const result = await getJson("/api/weave/validate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(weaveState.edited),
  });
  if (result.parse_error) {
    renderIssues([{ level: "error", code: "parse", message: result.parse_error, path: "" }]);
  } else {
    renderIssues(result.issues);
  }
  setSaveStatus(result.ok ? "valid ✓" : "has errors", result.ok ? "saved" : "error");
}

function downloadJson() {
  const blob = new Blob([JSON.stringify(weaveState.edited, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "coasys.weave.json";
  link.click();
  URL.revokeObjectURL(url);
}

// --------------------------------------------------------------------------
// Deploy view (deployment-readiness)
// --------------------------------------------------------------------------

const STATE_PILL = {
  ready: "passed",
  "needs-approval": "warn",
  blocked: "failed",
  "not-deployable": "unknown",
};

function populateDeployEnvs() {
  const select = wq("#weave-deploy-env");
  const envs = Object.keys(weaveState.document.environments || {});
  select.innerHTML =
    '<option value="">all</option>' +
    envs.map((name) => `<option value="${name}">${name}</option>`).join("");
}

async function renderDeploy() {
  if (wq("#weave-deploy-env").options.length <= 1) populateDeployEnvs();
  const env = wq("#weave-deploy-env").value;
  const report = await getJson(`/api/weave/deploy-check${env ? `?environment=${env}` : ""}`);
  const counts = report.counts || {};
  wq("#weave-deploy-summary").innerHTML =
    `<span class="weave-count passed">${counts.ready || 0} ready</span> · ` +
    `<span class="weave-count warn">${counts["needs-approval"] || 0} needs approval</span> · ` +
    `<span class="weave-count failed">${counts.blocked || 0} blocked</span> · ` +
    `${report.ready_to_roll ? "✓ ready to roll" : "✗ not ready"}`;

  wq("#weave-rollout").innerHTML = (report.rollout || []).length
    ? `<h3>Rollout order</h3>` +
      report.rollout
        .map(
          (wave) =>
            `<div class="weave-wave"><span class="weave-wave-label">wave ${wave.wave}</span>` +
            wave.repos
              .map((r) => `<span class="pill ${STATE_PILL[r.state] || "unknown"}">${r.repo}</span>`)
              .join(" ") +
            `</div>`,
        )
        .join("")
    : '<p class="muted">No deployable repositories for this filter.</p>';

  const rows = (report.statuses || [])
    .map(
      (status) => `
      <tr>
        <td>${status.repo}</td>
        <td><span class="pill ${STATE_PILL[status.state] || "unknown"}">${status.state}</span></td>
        <td>${status.environment || "—"} ${status.protected ? "🔒" : ""}</td>
        <td>${status.has_dry_run_gate ? "✓" : "✗"}</td>
        <td>${status.wave ?? "—"}</td>
        <td class="muted">${(status.reasons || []).join("; ") || "—"}</td>
      </tr>`,
    )
    .join("");
  wq("#weave-deploy-table").innerHTML = rows
    ? `<table class="weave-table">
        <thead><tr><th>repo</th><th>state</th><th>environment</th><th>gate</th><th>wave</th><th>reasons</th></tr></thead>
        <tbody>${rows}</tbody></table>`
    : '<p class="muted">No deployable repositories.</p>';
}

// --------------------------------------------------------------------------
// Theme
// --------------------------------------------------------------------------

function applyTheme(theme) {
  document.documentElement.dataset.weTheme = theme;
  try {
    localStorage.setItem("weTheme", theme);
  } catch (_) {
    /* ignore */
  }
  // Recolour the topology (markers/edges read CSS vars at build time).
  if (weaveState.loaded && weaveState.tab === "graph") {
    weaveState.topo.built = false;
    renderTopology();
  }
}

function initTheme() {
  let theme = "light";
  try {
    theme = localStorage.getItem("weTheme") || "light";
  } catch (_) {
    /* ignore */
  }
  const sel = wq("#we-theme-select");
  if (sel) sel.value = theme;
  document.documentElement.dataset.weTheme = theme;
}

// --------------------------------------------------------------------------
// Wiring
// --------------------------------------------------------------------------

document.querySelectorAll(".nav-button").forEach((node) => {
  node.addEventListener("click", () => {
    if (node.dataset.view === "weave" && !weaveState.loaded) {
      loadWeave().catch((error) => {
        wq("#weave-issues").innerHTML = `<div class="weave-issue error">${error.message}</div>`;
      });
    }
  });
});
document.querySelectorAll(".weave-tab").forEach((node) => {
  node.addEventListener("click", () => {
    weaveState.tab = node.dataset.weaveTab;
    renderWeaveTab();
  });
});
document.querySelectorAll(".weave-seg-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".weave-seg-btn").forEach((b) => b.classList.toggle("active", b === btn));
    weaveState.topo.layout = btn.dataset.layout;
    weaveState.topo.view = { x: 0, y: 0, k: 1 };
    relayout();
    applyView();
  });
});
document.querySelectorAll(".edge-filter").forEach((cb) => {
  cb.addEventListener("change", () => {
    weaveState.topo.edges[cb.dataset.edge] = cb.checked;
    weaveState.topo.built = false;
    renderTopology();
  });
});
wq("#weave-tier-filter").addEventListener("change", (e) => {
  weaveState.topo.tier = e.target.value;
  applyTierFilter();
});
wq("#weave-topo-reset").addEventListener("click", () => {
  weaveState.topo.view = { x: 0, y: 0, k: 1 };
  relayout();
  applyView();
});
wq("#weave-refresh").addEventListener("click", () => loadWeave());
wq("#weave-validate").addEventListener("click", () => validateEdits());
wq("#weave-download").addEventListener("click", () => downloadJson());
wq("#weave-save").addEventListener("click", () => saveDocument());
wq("#weave-deploy-env").addEventListener("change", () => renderDeploy());
wq("#we-theme-select").addEventListener("change", (e) => applyTheme(e.target.value));

initTheme();
