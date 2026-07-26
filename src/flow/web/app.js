const state = { current: null, workflow: null };
const $ = (selector) => document.querySelector(selector);

async function request(url, options) {
  const response = await fetch(url, options);
  const body = await response.json();
  if (!response.ok) throw new Error(body.detail ? JSON.stringify(body.detail) : "Request failed");
  return body;
}

function setStatus(message, kind = "") {
  $("#status").textContent = message;
  $("#status").className = `status ${kind}`;
}

async function loadList() {
  const workflows = await request("/api/workflows");
  const list = $("#workflow-list");
  list.innerHTML = "";
  workflows.forEach((workflow) => {
    const button = document.createElement("button");
    button.className = `workflow-item ${workflow.name === state.current ? "active" : ""}`;
    button.innerHTML = `<span>${workflow.name}</span><small>${workflow.valid ? `${workflow.steps} steps` : "Invalid"}</small>`;
    button.onclick = () => loadWorkflow(workflow.name);
    list.appendChild(button);
  });
}

async function loadWorkflow(name) {
  state.current = name;
  state.workflow = await request(`/api/workflows/${name}`);
  $("#workflow-name").textContent = state.workflow.name;
  $("#workflow-description").textContent = state.workflow.description || "No description";
  $("#definition").value = JSON.stringify(state.workflow, null, 2);
  renderGraph();
  loadList();
}

function dependencies(step) {
  const text = JSON.stringify(step);
  const refs = [...text.matchAll(/\$\{steps\.([A-Za-z][A-Za-z0-9_-]*)\.output/g)].map((m) => m[1]);
  return [...new Set([...(step.needs || []), ...refs])];
}

function renderGraph() {
  const graph = $("#graph");
  graph.innerHTML = "";
  graph.classList.remove("empty");
  const levels = [];
  const placed = new Map();
  state.workflow.steps.forEach((step) => {
    const deps = dependencies(step);
    const level = deps.length ? Math.max(...deps.map((id) => placed.get(id) ?? 0)) + 1 : 0;
    placed.set(step.id, level);
    (levels[level] ||= []).push(step);
  });
  levels.forEach((steps, index) => {
    if (index) {
      const arrow = document.createElement("div");
      arrow.className = "arrow";
      arrow.textContent = "→";
      graph.appendChild(arrow);
    }
    const column = document.createElement("div");
    column.className = "node-column";
    steps.forEach((step) => {
      const node = $("#node-template").content.cloneNode(true);
      node.querySelector(".node").dataset.type = step.type;
      node.querySelector(".node-type").textContent = step.type;
      node.querySelector("strong").textContent = step.id;
      node.querySelector("small").textContent = step.uses || `${step.concurrency} concurrent`;
      column.appendChild(node);
    });
    graph.appendChild(column);
  });
}

$("#validate").onclick = async () => {
  try {
    const workflow = JSON.parse($("#definition").value);
    const result = await request("/api/validate", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(workflow),
    });
    if (!result.valid) throw new Error(JSON.stringify(result.errors));
    state.workflow = result.workflow;
    renderGraph();
    setStatus("Valid workflow", "success");
  } catch (error) { setStatus(error.message, "error"); }
};

$("#save").onclick = async () => {
  try {
    const workflow = JSON.parse($("#definition").value);
    state.workflow = await request(`/api/workflows/${workflow.name}`, {
      method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(workflow),
    });
    state.current = workflow.name;
    renderGraph();
    await loadList();
    setStatus("Saved", "success");
  } catch (error) { setStatus(error.message, "error"); }
};

$("#run").onclick = async () => {
  if (!state.current) return setStatus("Select a workflow", "error");
  setStatus("Running…");
  try {
    const result = await request(`/api/workflows/${state.current}/execute`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ inputs: {} }),
    });
    $("#result").textContent = JSON.stringify(result, null, 2);
    document.querySelector('[data-tab="result"]').click();
    setStatus(result.status, result.status === "completed" ? "success" : "error");
  } catch (error) { setStatus(error.message, "error"); }
};

$("#new").onclick = () => {
  state.current = null;
  state.workflow = { name: "new-workflow", description: "", version: "1", inputs: {}, steps: [], outputs: {} };
  $("#workflow-name").textContent = "New workflow";
  $("#workflow-description").textContent = "Edit the JSON definition, then save.";
  $("#definition").value = JSON.stringify(state.workflow, null, 2);
  renderGraph();
};

document.querySelectorAll(".tab").forEach((button) => {
  button.onclick = () => {
    document.querySelectorAll(".tab").forEach((tab) => tab.classList.toggle("active", tab === button));
    $("#definition").hidden = button.dataset.tab !== "definition";
    $("#result").hidden = button.dataset.tab !== "result";
  };
});

loadList().catch((error) => setStatus(error.message, "error"));

