const state = {
  summary: null,
  repos: [],
  runs: [],
  activeView: "overview",
};

const $ = (selector) => document.querySelector(selector);

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`${response.status} ${text}`);
  }
  return response.json();
}

function setView(view) {
  state.activeView = view;
  document.querySelectorAll(".view").forEach((node) => {
    node.classList.toggle("active", node.id === view);
  });
  document.querySelectorAll(".nav-button").forEach((node) => {
    node.classList.toggle("active", node.dataset.view === view);
  });
}

function statusPill(status) {
  const value = status || "unknown";
  return `<span class="pill ${value}">${value}</span>`;
}

function countBy(items, key) {
  return items.reduce((acc, item) => {
    const value = item[key] || "unknown";
    acc[value] = (acc[value] || 0) + 1;
    return acc;
  }, {});
}

function renderSummary() {
  const repos = state.repos;
  const summary = state.summary || {};
  const tiers = summary.tiers || countBy(repos, "tier");
  const statuses = summary.statuses || countBy(repos, "validation_status");
  const metrics = [
    ["Repositories", summary.repo_count ?? repos.length],
    ["Cloned", summary.cloned_count ?? repos.filter((repo) => repo.exists).length],
    ["Core", tiers.core || 0],
    ["Active", tiers.active || 0],
    ["Language", tiers.language || 0],
    ["Dependency forks", tiers["dependency-fork"] || 0],
    ["Stale", tiers.stale || 0],
    ["Warnings", (statuses.warn || 0) + (statuses.blocked || 0)],
    ["Failed", statuses.failed || 0],
    ["Missing", statuses.missing || 0],
    ["Dirty", summary.dirty_count ?? repos.filter((repo) => repo.dirty).length],
    ["Behind remote", summary.behind_count ?? repos.filter((repo) => Number(repo.behind) > 0).length],
    ["Detected commands", summary.command_count ?? 0],
    ["Configured", (summary.config_statuses || {}).configured || 0],
    ["Detected only", (summary.config_statuses || {}).detected || 0],
    ["Dry-run passed", (summary.dry_run_statuses || {}).dry_run_passed || 0],
    ["Deploy ready", (summary.deploy_statuses || {}).deploy_ready || 0],
    ["Deploy executed", (summary.deploy_statuses || {}).deploy_executed || 0],
    ["Deploy blocked", (summary.deploy_statuses || {}).deploy_blocked || 0],
  ];
  $("#summary").innerHTML = metrics
    .map(
      ([label, value]) => `
        <article class="metric">
          <span class="metric-value">${value}</span>
          <span class="metric-label">${label}</span>
        </article>
      `,
    )
    .join("");

  const alerts = repos
    .filter((repo) => ["failed", "blocked", "missing", "warn"].includes(repo.validation_status))
    .slice(0, 8);
  $("#alerts").innerHTML = alerts.length
    ? alerts
        .map(
          (repo) => `
            <div class="alert">
              <strong>${repo.name}</strong> ${statusPill(repo.validation_status)}
              <span class="muted">${repo.last_error || repo.description || ""}</span>
            </div>
          `,
        )
        .join("")
    : '<div class="alert">No validation alerts recorded.</div>';
}

function renderFilters() {
  const tiers = [...new Set(state.repos.map((repo) => repo.tier).filter(Boolean))].sort();
  const current = $("#tier-filter").value;
  $("#tier-filter").innerHTML = '<option value="">All tiers</option>';
  for (const tier of tiers) {
    const option = document.createElement("option");
    option.value = tier;
    option.textContent = tier;
    option.selected = tier === current;
    $("#tier-filter").appendChild(option);
  }
}

function renderRepoTable() {
  const tier = $("#tier-filter").value;
  const status = $("#status-filter").value;
  const rows = state.repos.filter((repo) => {
    if (tier && repo.tier !== tier) return false;
    if (status && repo.validation_status !== status) return false;
    return true;
  });
  $("#repo-table").innerHTML = `
    <table>
      <thead>
        <tr>
          <th>Name</th>
          <th>Tier</th>
          <th>Config</th>
          <th>Status</th>
          <th>Start</th>
          <th>Deploy</th>
          <th>Stack</th>
          <th>Branch</th>
          <th>Behind</th>
          <th>Updated</th>
        </tr>
      </thead>
      <tbody>
        ${rows
          .map(
            (repo) => `
              <tr>
                <td><button class="repo-link" data-repo="${repo.name}">${repo.name}</button></td>
                <td>${repo.tier}</td>
                <td>${statusPill(repo.config_status)}</td>
                <td>${statusPill(repo.validation_status)}</td>
                <td>${statusPill(repo.start_status)}</td>
                <td title="${repo.deploy_reason || ""}">${statusPill(repo.deploy_status)}</td>
                <td>${(repo.stacks || []).join(", ") || '<span class="muted">none</span>'}</td>
                <td>${repo.branch || repo.default_branch || ""}</td>
                <td>${repo.behind || 0}</td>
                <td>${repo.updated_at || ""}</td>
              </tr>
            `,
          )
          .join("")}
      </tbody>
    </table>
  `;
  document.querySelectorAll(".repo-link").forEach((node) => {
    node.addEventListener("click", () => showRepo(node.dataset.repo));
  });
}

function renderRuns() {
  $("#runs-table").innerHTML = `
    <table>
      <thead>
        <tr>
          <th>ID</th>
          <th>Repository</th>
          <th>Profile</th>
          <th>Status</th>
          <th>Exit</th>
          <th>Started</th>
        </tr>
      </thead>
      <tbody>
        ${state.runs
          .map(
            (run) => `
              <tr>
                <td>${run.id}</td>
                <td>${run.repo_name}</td>
                <td>${run.profile}</td>
                <td>${statusPill(run.status)}</td>
                <td>${run.exit_code ?? ""}</td>
                <td>${run.started_at}</td>
              </tr>
            `,
          )
          .join("")}
      </tbody>
    </table>
  `;
}

function renderTopology() {
  const groups = countBy(state.repos, "tier");
  $("#topology-groups").innerHTML = Object.keys(groups)
    .sort()
    .map((tier) => {
      const repos = state.repos.filter((repo) => repo.tier === tier);
      return `
        <article class="topology-card">
          <h2>${tier}</h2>
          <p class="muted">${repos.length} repositories</p>
          ${repos
            .slice(0, 18)
            .map((repo) => `<span class="pill">${repo.name}</span>`)
            .join(" ")}
        </article>
      `;
    })
    .join("");
}

async function showRepo(name) {
  const payload = await fetchJson(`/api/repos/${name}`);
  const repo = payload.repo;
  const hasBuild = Boolean((repo.commands?.build || []).length);
  const hasStart = Boolean((repo.playbook_profiles || []).includes("start"));
  const hasDeploy = Boolean((repo.playbook_profiles || []).includes("deploy"));
  const canValidate = Boolean((repo.commands?.validation || []).length || repo.exists);
  const playbooks = (repo.playbook_profiles || []).length
    ? repo.playbook_profiles.map((profile) => `<span class="pill configured">${profile}</span>`).join(" ")
    : '<span class="muted">none</span>';
  const missingEnv = (repo.missing_env || []).length
    ? repo.missing_env.map((envName) => `<span class="pill deploy_blocked">${envName}</span>`).join(" ")
    : '<span class="muted">none</span>';
  const commandGroups = Object.entries(repo.commands || {})
    .map(([kind, commands]) => {
      const lines = commands.map((command) => command.command.join(" ")).join("\n");
      return `<h3>${kind}</h3><pre>${lines || "none"}</pre>`;
    })
    .join("");
  $("#detail").innerHTML = `
    <div class="detail-header">
      <div>
        <h2>${repo.name}</h2>
        <div class="muted">${repo.description || repo.full_name}</div>
      </div>
      <button id="close-detail" title="Close">Close</button>
    </div>
    <p>${statusPill(repo.validation_status)} <span class="pill">${repo.tier}</span></p>
    <p><strong>Config:</strong> ${statusPill(repo.config_status)}
      <span class="muted">${repo.next_action || ""}</span></p>
    <p><strong>Start:</strong> ${statusPill(repo.start_status)}</p>
    <p><strong>Deploy:</strong> ${statusPill(repo.deploy_status)}
      <span class="muted">${repo.deploy_reason || ""}</span></p>
    <p><strong>Playbooks:</strong> ${playbooks}</p>
    <p><strong>Missing env:</strong> ${missingEnv}</p>
    <p><strong>Local:</strong> <span class="muted">${repo.local_path}</span></p>
    <p><strong>GitHub:</strong> <a href="${repo.html_url}" target="_blank" rel="noreferrer">${repo.full_name}</a></p>
    <p><strong>Branch:</strong> ${repo.branch || repo.default_branch} /
      <strong>behind:</strong> ${repo.behind || 0} /
      <strong>ahead:</strong> ${repo.ahead || 0} /
      <strong>dirty:</strong> ${repo.dirty ? "yes" : "no"}</p>
    <div class="detail-actions">
      <button data-action="sync" data-repo="${repo.name}">Sync</button>
      <button data-action="validate" data-repo="${repo.name}" ${canValidate ? "" : "disabled"}>Validate</button>
      <button data-action="build" data-repo="${repo.name}" ${hasBuild ? "" : "disabled"}>Build</button>
      <button data-action="build-dry-run" data-repo="${repo.name}" ${hasBuild ? "" : "disabled"}>Build Dry Run</button>
      <button data-action="start-dry-run" data-repo="${repo.name}" ${hasStart ? "" : "disabled"}>Start Dry Run</button>
      <button data-action="deploy-dry-run" data-repo="${repo.name}" ${hasDeploy ? "" : "disabled"}>Deploy Dry Run</button>
      <button data-action="deploy-execute" data-repo="${repo.name}" ${hasDeploy ? "" : "disabled"}>Execute Deploy</button>
      <a class="button-link" href="${repo.html_url}" target="_blank" rel="noreferrer">GitHub</a>
    </div>
    <h3>Stacks</h3>
    <p>${(repo.stacks || []).map((stack) => `<span class="pill">${stack}</span>`).join(" ") || "none"}</p>
    ${commandGroups}
  `;
  $("#detail").classList.add("active");
  $("#close-detail").addEventListener("click", () => $("#detail").classList.remove("active"));
  document.querySelectorAll("[data-action][data-repo]").forEach((node) => {
    node.addEventListener("click", () => runRepoAction(node.dataset.repo, node.dataset.action));
  });
}

async function runRepoAction(repo, action) {
  if (
    action === "deploy-execute" &&
    !window.confirm(`Execute the deploy profile for ${repo}? This may publish or release artifacts.`)
  ) {
    return;
  }
  setNotice(`${action} started for ${repo}`);
  let endpoint =
    action === "sync"
      ? `/api/repos/${repo}/sync`
      : action === "validate"
        ? `/api/repos/${repo}/validate`
        : `/api/repos/${repo}/run/${action}`;
  if (action === "build-dry-run") endpoint = `/api/repos/${repo}/run/build?dry_run=true`;
  if (action === "start-dry-run") endpoint = `/api/repos/${repo}/run/start?dry_run=true`;
  if (action === "deploy-dry-run") endpoint = `/api/repos/${repo}/run/deploy?dry_run=true`;
  if (action === "deploy-execute") endpoint = `/api/repos/${repo}/run/deploy?execute=true`;
  try {
    await fetchJson(endpoint, { method: "POST" });
    await load();
    await showRepo(repo);
    setNotice(`${action} finished for ${repo}`);
  } catch (error) {
    setNotice(`${action} failed for ${repo}: ${error.message}`);
  }
}

async function operateFleet({ clone, validate, deploy = false }) {
  const label = clone ? "fleet sync and validation" : "local operation";
  setNotice(`${label} started`);
  const params = new URLSearchParams({
    clone: String(clone),
    validate: String(validate),
    deploy: String(deploy),
    execute_configured: "true",
  });
  try {
    const result = await fetchJson(`/api/operate?${params.toString()}`, { method: "POST" });
    await load();
    setNotice(
      `${label} finished: ${result.repo_count} repos, ${result.validated_count} validated, ${result.deployed_count} deployed`,
    );
  } catch (error) {
    setNotice(`${label} failed: ${error.message}`);
  }
}

function setNotice(message) {
  const notice = $("#notice");
  notice.textContent = message;
  notice.hidden = false;
}

function renderAll() {
  renderSummary();
  renderFilters();
  renderRepoTable();
  renderRuns();
  renderTopology();
}

async function load() {
  const [summaryPayload, repoPayload, runPayload] = await Promise.all([
    fetchJson("/api/summary"),
    fetchJson("/api/repos"),
    fetchJson("/api/runs"),
  ]);
  state.summary = summaryPayload;
  state.repos = repoPayload.repos;
  state.runs = runPayload.runs;
  renderAll();
}

document.querySelectorAll(".nav-button").forEach((node) => {
  node.addEventListener("click", () => setView(node.dataset.view));
});
$("#refresh").addEventListener("click", load);
$("#operate-local").addEventListener("click", () => operateFleet({ clone: false, validate: false }));
$("#operate-fleet").addEventListener("click", () => operateFleet({ clone: true, validate: true }));
$("#tier-filter").addEventListener("change", renderRepoTable);
$("#status-filter").addEventListener("change", renderRepoTable);

setView("overview");
load().catch((error) => {
  $("#alerts").innerHTML = `<div class="alert">${error.message}</div>`;
});
