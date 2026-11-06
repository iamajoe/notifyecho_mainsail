"use strict";

// The settings page runs from Moonraker, so all calls are same-origin.
// Mainsail's custom navigation entry opens this page in the same tab.
const API = "/server/notifyecho";

const state = {
  settings: null,
  events: [],
  lastSend: null,
  milestonesText: "",
  update: null,
  updatePoll: null,
};

const els = {};

document.addEventListener("DOMContentLoaded", function () {
  els.baseUrl = document.getElementById("base-url");
  els.token = document.getElementById("token");
  els.defaultWorkflow = document.getElementById("default-workflow");
  els.advancedMode = document.getElementById("advanced-mode");
  els.eventsList = document.getElementById("events-list");
  els.save = document.getElementById("save");
  els.verifyAll = document.getElementById("verify-all");
  els.status = document.getElementById("status");
  els.lastSend = document.getElementById("last-send");
  els.back = document.getElementById("back");
  els.updateRefresh = document.getElementById("update-refresh");
  els.updateRun = document.getElementById("update-run");
  els.updateVersion = document.getElementById("update-version");
  els.updateDetail = document.getElementById("update-detail");
  els.updateStatus = document.getElementById("update-status");

  bindStaticEvents();
  void load();
});

function bindStaticEvents() {
  els.baseUrl.addEventListener("input", function () {
    state.settings.baseUrl = els.baseUrl.value.trim();
  });
  els.token.addEventListener("input", function () {
    state.settings.token = els.token.value.trim();
  });
  els.defaultWorkflow.addEventListener("input", function () {
    state.settings.defaultWorkflowId = els.defaultWorkflow.value.trim();
  });
  els.advancedMode.addEventListener("change", function () {
    state.settings.advancedMode = els.advancedMode.checked;
    renderEvents();
  });
  els.save.addEventListener("click", function () {
    void saveSettings();
  });
  els.verifyAll.addEventListener("click", function () {
    void verifyAll();
  });
  els.back.addEventListener("click", function () {
    if (window.history.length > 1) {
      window.history.back();
    } else {
      window.location.href = "/";
    }
  });
  els.updateRefresh.addEventListener("click", function () {
    void refreshUpdateStatus();
  });
  els.updateRun.addEventListener("click", function () {
    void runUpdate();
  });
}

async function load() {
  setStatus("Loading settings…", "busy");
  try {
    const data = await api("/settings");
    applyData(data);
    setStatus("");
  } catch (error) {
    setStatus(error.message, "error");
  }
  await loadUpdateStatus();
}

function applyData(data) {
  state.settings = data.settings;
  state.events = data.events || [];
  state.lastSend = data.lastSend || null;
  state.milestonesText = (state.settings.progressMilestones || []).join(", ");

  els.baseUrl.value = state.settings.baseUrl || "";
  els.token.value = state.settings.token || "";
  els.defaultWorkflow.value = state.settings.defaultWorkflowId || "";
  els.advancedMode.checked = Boolean(state.settings.advancedMode);

  renderEvents();
  renderLastSend();
}

function renderEvents() {
  els.eventsList.innerHTML = "";

  state.events.forEach(function (definition) {
    const entry = state.settings.events[definition.key] || {
      enabled: true,
      workflowId: "",
    };
    state.settings.events[definition.key] = entry;

    const row = document.createElement("div");
    row.className = "event-row";
    if (!entry.enabled) {
      row.classList.add("is-disabled");
    }

    const main = document.createElement("div");
    main.className = "event-main";

    const toggle = document.createElement("input");
    toggle.type = "checkbox";
    toggle.checked = Boolean(entry.enabled);
    toggle.setAttribute("aria-label", "Enable " + definition.label);
    toggle.addEventListener("change", function () {
      entry.enabled = toggle.checked;
      row.classList.toggle("is-disabled", !entry.enabled);
    });

    const copy = document.createElement("div");
    const title = document.createElement("div");
    title.className = "event-title";
    title.textContent = definition.label;

    const kind = document.createElement("code");
    kind.className = "event-kind";
    kind.textContent = definition.kind;

    const description = document.createElement("p");
    description.className = "event-description";
    description.textContent = definition.description + " Source: " + definition.source;

    copy.appendChild(title);
    copy.appendChild(kind);
    copy.appendChild(description);
    main.appendChild(toggle);
    main.appendChild(copy);

    const actions = document.createElement("div");
    actions.className = "event-actions";

    const verifyButton = document.createElement("button");
    verifyButton.type = "button";
    verifyButton.className = "button small";
    verifyButton.textContent = "Verify";
    verifyButton.addEventListener("click", function () {
      void verifyEvent(definition.key, status);
    });

    const testButton = document.createElement("button");
    testButton.type = "button";
    testButton.className = "button small";
    testButton.textContent = "Send test";
    testButton.addEventListener("click", function () {
      void sendTest(definition.key, status);
    });

    actions.appendChild(verifyButton);
    actions.appendChild(testButton);

    const details = document.createElement("div");
    details.className = "event-details";

    if (definition.key === "print_progress") {
      const milestonesLabel = document.createElement("label");
      milestonesLabel.textContent = "Progress milestones (%)";
      const milestonesInput = document.createElement("input");
      milestonesInput.type = "text";
      milestonesInput.id = "progress-milestones";
      milestonesInput.value = state.milestonesText;
      milestonesInput.placeholder = "25, 50, 75, 90";
      milestonesInput.addEventListener("input", function () {
        state.milestonesText = milestonesInput.value;
      });
      milestonesLabel.appendChild(milestonesInput);
      details.appendChild(milestonesLabel);
    }

    if (state.settings.advancedMode) {
      const workflowLabel = document.createElement("label");
      workflowLabel.textContent = "Workflow ID for this event";
      const workflowInput = document.createElement("input");
      workflowInput.type = "text";
      workflowInput.spellcheck = false;
      workflowInput.value = entry.workflowId || "";
      workflowInput.placeholder = state.settings.defaultWorkflowId
        ? "Default: " + state.settings.defaultWorkflowId
        : "Falls back to the default workflow ID";
      workflowInput.addEventListener("input", function () {
        entry.workflowId = workflowInput.value.trim();
      });
      workflowLabel.appendChild(workflowInput);
      details.appendChild(workflowLabel);
    }

    const status = document.createElement("span");
    status.className = "inline-status";

    row.appendChild(main);
    row.appendChild(actions);
    row.appendChild(details);
    row.appendChild(status);
    els.eventsList.appendChild(row);
  });
}

async function saveSettings() {
  const milestones = parseMilestones(state.milestonesText);
  if (milestones === null) {
    setStatus("Progress milestones must be whole numbers between 1 and 100.", "error");
    return;
  }
  state.settings.progressMilestones = milestones;

  setStatus("Saving…", "busy");
  try {
    const data = await api("/settings", {
      method: "POST",
      body: JSON.stringify({ settings: state.settings }),
    });
    applyData(data);
    setStatus("Saved.", "ok");
  } catch (error) {
    setStatus(error.message, "error");
  }
}

async function verifyEvent(eventKey, inlineStatus) {
  const workflowId = resolveWorkflow(eventKey);
  if (!workflowId) {
    setInline(inlineStatus, "Set a workflow ID first.", "error");
    return;
  }

  setInline(inlineStatus, "Verifying…", "busy");
  try {
    const result = await api("/verify", {
      method: "POST",
      body: JSON.stringify({
        baseUrl: state.settings.baseUrl,
        token: state.settings.token,
        workflowId: workflowId,
      }),
    });

    if (result.valid) {
      const name = result.name || "Workflow";
      const status = result.status ? " (" + result.status + ")" : "";
      setInline(inlineStatus, "✓ " + name + status, "ok");
    } else {
      setInline(inlineStatus, "✗ " + result.message, "error");
    }
  } catch (error) {
    setInline(inlineStatus, "✗ " + error.message, "error");
  }
}

async function sendTest(eventKey, inlineStatus) {
  const workflowId = resolveWorkflow(eventKey);
  if (!workflowId) {
    setInline(inlineStatus, "Set a workflow ID first.", "error");
    return;
  }
  if (!state.settings.token) {
    setInline(inlineStatus, "Set the bearer token first.", "error");
    return;
  }

  setInline(inlineStatus, "Sending test…", "busy");
  try {
    const result = await api("/test", {
      method: "POST",
      body: JSON.stringify({
        eventKey: eventKey,
        baseUrl: state.settings.baseUrl,
        token: state.settings.token,
        workflowId: workflowId,
      }),
    });

    if (result.ok) {
      setInline(inlineStatus, "✓ Accepted (HTTP " + result.httpStatus + ")", "ok");
    } else {
      setInline(inlineStatus, "✗ " + result.message, "error");
    }
  } catch (error) {
    setInline(inlineStatus, "✗ " + error.message, "error");
  }
}

async function verifyAll() {
  const workflows = [];
  state.events.forEach(function (definition) {
    const entry = state.settings.events[definition.key];
    if (!entry || !entry.enabled) {
      return;
    }
    const workflowId = resolveWorkflow(definition.key);
    if (workflowId && workflows.indexOf(workflowId) === -1) {
      workflows.push(workflowId);
    }
  });

  if (workflows.length === 0) {
    setStatus("No enabled event has a workflow ID.", "error");
    return;
  }

  setStatus("Verifying " + workflows.length + " workflow(s)…", "busy");
  let valid = 0;
  const failures = [];

  for (const workflowId of workflows) {
    try {
      const result = await api("/verify", {
        method: "POST",
        body: JSON.stringify({
          baseUrl: state.settings.baseUrl,
          token: state.settings.token,
          workflowId: workflowId,
        }),
      });
      if (result.valid) {
        valid += 1;
      } else {
        failures.push(workflowId + ": " + result.message);
      }
    } catch (error) {
      failures.push(workflowId + ": " + error.message);
    }
  }

  if (failures.length === 0) {
    setStatus("All " + valid + " workflow(s) verified.", "ok");
  } else {
    setStatus("Verified " + valid + " of " + workflows.length + ". " + failures.join(" · "), "error");
  }
}

function resolveWorkflow(eventKey) {
  if (state.settings.advancedMode) {
    const entry = state.settings.events[eventKey];
    if (entry && entry.workflowId && entry.workflowId.trim()) {
      return entry.workflowId.trim();
    }
  }
  return (state.settings.defaultWorkflowId || "").trim();
}

async function loadUpdateStatus() {
  try {
    const data = await api("/update");
    state.update = data;
    renderUpdate();
  } catch (error) {
    setUpdateStatus("Could not read update status: " + error.message, "error");
  }
}

async function refreshUpdateStatus() {
  els.updateRefresh.disabled = true;
  setUpdateStatus("Checking for updates…", "busy");
  try {
    const result = await api("/update", {
      method: "POST",
      body: JSON.stringify({ action: "refresh" }),
    });
    state.update = result.status || state.update;
    renderUpdate();
    if (state.update && state.update.updatable) {
      setUpdateStatus("An update is available.", "ok");
    } else if (state.update && state.update.available) {
      setUpdateStatus("NotifyEcho is up to date.", "ok");
    } else {
      setUpdateStatus((state.update && state.update.message) || "", "error");
    }
  } catch (error) {
    setUpdateStatus("Could not check for updates: " + error.message, "error");
  } finally {
    els.updateRefresh.disabled = false;
  }
}

async function runUpdate() {
  if (
    !state.update ||
    !state.update.updatable ||
    state.update.updateAllowed === false
  ) {
    return;
  }

  els.updateRun.disabled = true;
  setUpdateStatus("Starting update…", "busy");
  try {
    const result = await api("/update", {
      method: "POST",
      body: JSON.stringify({ action: "update" }),
    });
    state.update = result.status || state.update;
    renderUpdate();
    setUpdateStatus(
      "Updating. Moonraker restarts when the update finishes, so this page may briefly disconnect.",
      "busy"
    );
    startUpdatePolling();
  } catch (error) {
    setUpdateStatus("Could not start the update: " + error.message, "error");
    renderUpdate();
  }
}

function startUpdatePolling() {
  stopUpdatePolling();
  let attempts = 0;
  state.updatePoll = window.setInterval(async function () {
    attempts += 1;
    try {
      const data = await api("/update");
      state.update = data;
      renderUpdate();
      if (data.lastUpdate && data.lastUpdate.ok === false) {
        stopUpdatePolling();
        setUpdateStatus("Update failed: " + data.lastUpdate.message, "error");
      } else if (data.available && !data.busy && !data.updatable) {
        stopUpdatePolling();
        setUpdateStatus("Update complete.", "ok");
      } else {
        setUpdateStatus(
          "Updating… Moonraker will restart when the update finishes.",
          "busy"
        );
      }
    } catch (error) {
      setUpdateStatus("Waiting for Moonraker to restart…", "busy");
    }

    if (attempts >= 240) {
      stopUpdatePolling();
      setUpdateStatus(
        "Could not confirm the update finished. Reload the page to check.",
        "error"
      );
    }
  }, 5000);
}

function stopUpdatePolling() {
  if (state.updatePoll !== null) {
    window.clearInterval(state.updatePoll);
    state.updatePoll = null;
  }
}

function renderUpdate() {
  const update = state.update;
  if (!update) {
    return;
  }

  if (!update.available) {
    els.updateVersion.textContent = "";
    els.updateDetail.textContent = update.message || "Updates are not available.";
    els.updateRun.disabled = true;
    return;
  }

  els.updateVersion.textContent = update.version ? "· " + update.version : "";
  els.updateDetail.textContent = updateDetail(update);
  els.updateRun.disabled =
    Boolean(update.busy) ||
    !update.updatable ||
    update.updateAllowed === false;
  els.updateRun.textContent = update.busy ? "Updating…" : "Update";

  if (!update.valid && update.warnings && update.warnings.length) {
    setUpdateStatus(update.warnings.join(" · "), "error");
  }
}

function updateDetail(update) {
  const parts = [];
  if (update.updateAllowed === false) {
    parts.push(
      "Installed from a branch or commit. Reinstall from a release tag to enable updates."
    );
    if (update.channel) {
      parts.push("Channel: " + update.channel + ".");
    }
    return parts.join(" ");
  }

  if (!update.valid) {
    parts.push("This install cannot be updated automatically.");
  } else if (update.updatable) {
    if (update.version && update.remoteVersion) {
      parts.push(update.version + " → " + update.remoteVersion);
    } else {
      parts.push("An update is available.");
    }
    if (update.commitsBehind) {
      parts.push(
        update.commitsBehind +
          " new commit" +
          (update.commitsBehind === 1 ? "" : "s")
      );
    }
  } else {
    parts.push("Up to date.");
  }

  if (update.channel) {
    parts.push("Channel: " + update.channel + ".");
  }
  return parts.join(" ");
}

function setUpdateStatus(message, kind) {
  els.updateStatus.textContent = message || "";
  els.updateStatus.className = "hint update-status" + (kind ? " is-" + kind : "");
}

function parseMilestones(text) {
  const trimmed = String(text || "").trim();
  if (!trimmed) {
    return [];
  }

  const result = [];
  const parts = trimmed.split(",");
  for (let index = 0; index < parts.length; index += 1) {
    const part = parts[index].trim();
    if (!/^[0-9]+$/.test(part)) {
      return null;
    }
    const number = Number(part);
    if (number < 1 || number > 100) {
      return null;
    }
    if (result.indexOf(number) === -1) {
      result.push(number);
    }
  }
  result.sort(function (left, right) {
    return left - right;
  });
  return result;
}

function renderLastSend() {
  if (!state.lastSend) {
    els.lastSend.textContent = "No events have been sent yet.";
    return;
  }
  const outcome = state.lastSend.ok ? "accepted" : "failed";
  els.lastSend.textContent =
    "Last send: " +
    state.lastSend.kind +
    " — " +
    outcome +
    " (HTTP " +
    state.lastSend.httpStatus +
    ") at " +
    state.lastSend.at +
    (state.lastSend.ok ? "" : " · " + state.lastSend.message);
}

function setStatus(message, kind) {
  els.status.textContent = message || "";
  els.status.className = "status" + (kind ? " is-" + kind : "");
}

function setInline(element, message, kind) {
  element.textContent = message || "";
  element.className = "inline-status" + (kind ? " is-" + kind : "");
}

async function api(path, options) {
  const requestOptions = Object.assign(
    {
      headers: { "Content-Type": "application/json" },
    },
    options || {}
  );

  const response = await fetch(API + path, requestOptions);
  const data = await response.json().catch(function () {
    return {};
  });

  if (!response.ok) {
    const error = data.error;
    const message =
      (error && error.message) ||
      (typeof error === "string" ? error : "") ||
      "Request failed (HTTP " + response.status + ")";
    throw new Error(message);
  }

  return data.result;
}
