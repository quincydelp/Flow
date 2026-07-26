const state = { current: null, workflow: null, selectedStep: null };
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
  if (!state.current && workflows.length) await loadWorkflow(workflows[0].name);
}

async function loadWorkflow(name) {
  state.current = name;
  state.selectedStep = null;
  state.workflow = await request(`/api/workflows/${name}`);
  $("#workflow-name").textContent = state.workflow.name;
  $("#workflow-description").textContent = state.workflow.description || "No description";
  $("#definition").value = JSON.stringify(state.workflow, null, 2);
  renderGraph();
  renderInspector();
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
      const card = node.querySelector(".node");
      card.dataset.type = step.type;
      card.dataset.stepId = step.id;
      card.tabIndex = 0;
      card.setAttribute("role", "button");
      card.setAttribute("aria-label", `Inspect ${step.id}`);
      card.classList.toggle("selected", step.id === state.selectedStep);
      card.onclick = () => selectStep(step);
      card.onkeydown = (event) => {
        if (event.key === "Enter" || event.key === " ") selectStep(step);
      };
      node.querySelector(".node-type").textContent = step.type;
      node.querySelector("strong").textContent = step.id;
      node.querySelector("small").textContent = step.uses || `${step.concurrency} concurrent`;
      column.appendChild(node);
    });
    graph.appendChild(column);
  });
}

function selectStep(step) {
  state.selectedStep = step.id;
  renderGraph();
  renderInspector(step);
}

function addInspectorRow(container, label, value) {
  const row = document.createElement("div");
  row.className = "inspector-row";
  const key = document.createElement("dt");
  key.textContent = label;
  const content = document.createElement("dd");
  content.textContent = typeof value === "string" ? value : JSON.stringify(value, null, 2);
  row.append(key, content);
  container.appendChild(row);
}

function renderInspector(step = null) {
  const inspector = $("#inspector");
  inspector.innerHTML = "";
  if (!state.workflow) {
    inspector.innerHTML = '<div class="inspector-empty">Select a workflow.</div>';
    return;
  }
  const selected = step || state.workflow.steps.find((item) => item.id === state.selectedStep);
  if (!selected) {
    const eyebrow = document.createElement("div");
    eyebrow.className = "inspector-eyebrow";
    eyebrow.textContent = "Workflow definition";
    const heading = document.createElement("h2");
    heading.textContent = state.workflow.name;
    const summary = document.createElement("p");
    summary.textContent = `${state.workflow.steps.length} nodes · version ${state.workflow.version}`;
    const hint = document.createElement("div");
    hint.className = "inspector-empty";
    hint.textContent = "Select a node in the DAG to inspect its inputs, references, and operation.";
    inspector.append(eyebrow, heading, summary, hint);
    return;
  }

  const eyebrow = document.createElement("div");
  eyebrow.className = "inspector-eyebrow";
  eyebrow.textContent = `${selected.type} node`;
  const heading = document.createElement("h2");
  heading.textContent = selected.id;
  const definition = document.createElement("dl");
  definition.className = "inspector-definition";
  if (selected.description) addInspectorRow(definition, "Purpose", selected.description);
  if (selected.uses) addInspectorRow(definition, "Operation", selected.uses);
  if (selected.action) addInspectorRow(definition, "Action", selected.action);
  if (selected.needs?.length) addInspectorRow(definition, "Depends on", selected.needs);
  if (selected.over) addInspectorRow(definition, "Fan out over", selected.over);
  if (selected.concurrency) addInspectorRow(definition, "Concurrency", selected.concurrency);
  if (selected.with && Object.keys(selected.with).length) {
    addInspectorRow(definition, "Inputs", selected.with);
  }
  if (selected.prompt) addInspectorRow(definition, "Prompt", selected.prompt);
  if (selected.step) addInspectorRow(definition, "Mapped node", selected.step);
  if (selected.persist?.length) addInspectorRow(definition, "Persist", selected.persist);
  inspector.append(eyebrow, heading, definition);
}

$("#validate").onclick = async () => {
  try {
    const workflow = JSON.parse($("#definition").value);
    const result = await request("/api/validate", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(workflow),
    });
    if (!result.valid) throw new Error(JSON.stringify(result.errors));
    state.workflow = result.workflow;
    state.selectedStep = null;
    renderGraph();
    renderInspector();
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
    state.selectedStep = null;
    renderGraph();
    renderInspector();
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
  state.selectedStep = null;
  state.workflow = { name: "new-workflow", description: "", version: "1", inputs: {}, steps: [], outputs: {} };
  $("#workflow-name").textContent = "New workflow";
  $("#workflow-description").textContent = "Define nodes and relationships, then validate the DAG.";
  $("#definition").value = JSON.stringify(state.workflow, null, 2);
  renderGraph();
  renderInspector();
  document.querySelector('[data-tab="source"]').click();
};

document.querySelectorAll(".tab").forEach((button) => {
  button.onclick = () => {
    document.querySelectorAll(".tab").forEach((tab) => tab.classList.toggle("active", tab === button));
    $("#definition").hidden = button.dataset.tab !== "source";
    $("#result").hidden = button.dataset.tab !== "result";
  };
});

loadList().catch((error) => setStatus(error.message, "error"));
