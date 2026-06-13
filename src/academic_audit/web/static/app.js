document.addEventListener("DOMContentLoaded", function () {
  var tabContent = document.getElementById("tab-content");
  var tabsNav = document.getElementById("tabs-nav");

  if (!tabContent) return;

  // ── Tab Navigation ──

  tabsNav.addEventListener("click", function (e) {
    var btn = e.target.closest(".tab-btn");
    if (!btn) return;

    var tabName = btn.getAttribute("data-tab");
    if (!tabName) return;

    document.querySelectorAll(".tab-btn").forEach(function (b) {
      b.classList.remove("active");
    });
    btn.classList.add("active");

    tabContent.classList.add("loading");
    fetch("/tabs/" + tabName)
      .then(function (r) {
        if (!r.ok) throw new Error("Error " + r.status);
        return r.text();
      })
      .then(function (html) {
        tabContent.innerHTML = html;
        tabContent.classList.remove("loading");
        initTabHandlers(tabName);
      })
      .catch(function (err) {
        tabContent.innerHTML =
          '<div class="empty-state">Error al cargar la pestaña: ' +
          err.message +
          "</div>";
        tabContent.classList.remove("loading");
      });
  });

  // ── Initial load ──

  initTabHandlers("pipeline");

  // ── Footer: Delete DB ──

  var deleteBtn = document.getElementById("btn-delete-db");
  if (deleteBtn) {
    deleteBtn.addEventListener("click", function () {
      var cb = document.getElementById("chk-delete-db");
      var statusEl = document.getElementById("db-status");
      var formData = new FormData();
      formData.append("delete_on_close", cb ? cb.checked : false);

      fetch("/api/db/delete", { method: "POST" })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          if (statusEl) statusEl.textContent = data.message;
          if (cb && cb.checked) {
            statusEl.textContent += " | Opción 'Borrar al cerrar' activa.";
          }
        });
    });
  }
});

// ── Tab-specific initializers ──

function initTabHandlers(tabName) {
  switch (tabName) {
    case "pipeline":
      initPipelineTab();
      break;
    case "study_plan":
      initStudyPlanTab();
      break;
    case "parameters":
      initParametersTab();
      break;
    case "eligibility":
      initEligibilityTab();
      break;
  }
}

// ── Pipeline Tab ──

function initPipelineTab() {
  bindPipelineBtn("btn-convert", "/api/pipeline/convert", [
    "pdf_dir",
    "md_dir",
    "workers",
  ]);
  bindPipelineBtn("btn-extract", "/api/pipeline/extract", [
    "md_dir",
    "pdf_dir",
  ]);
  bindPipelineBtn("btn-pipeline", "/api/pipeline/run", [
    "pdf_dir",
    "md_dir",
    "insc_dir",
    "insc_md_dir",
    "report_dir",
    "workers",
  ]);
  bindPipelineBtn("btn-reports", "/api/pipeline/reports", ["report_dir"]);
}

function bindPipelineBtn(btnId, url, fieldNames) {
  var btn = document.getElementById(btnId);
  if (!btn) return;

  btn.addEventListener("click", function () {
    var formData = new FormData();
    fieldNames.forEach(function (name) {
      var el = document.getElementById(name);
      if (el) formData.append(name, el.value);
    });

    var logEl = document.getElementById("log-output");
    if (logEl) {
      logEl.textContent = "";
      logEl.scrollTop = 0;
    }

    btn.disabled = true;
    btn.textContent = "⏳ Procesando...";

    fetch(url, { method: "POST", body: formData })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.task_id) {
          connectLogStream(data.task_id, btn);
        } else {
          if (logEl) logEl.textContent = "Error: " + JSON.stringify(data);
          btn.disabled = false;
          btn.textContent = btn.getAttribute("data-orig") || btn.textContent.replace("⏳ Procesando...", "");
        }
      })
      .catch(function (err) {
        if (logEl) logEl.textContent = "Error de conexión: " + err.message;
        btn.disabled = false;
        btn.textContent = btn.getAttribute("data-orig") || "Error";
      });
  });

  btn.setAttribute("data-orig", btn.textContent);
}

function connectLogStream(taskId, btn) {
  var logEl = document.getElementById("log-output");
  var source = new EventSource("/api/tasks/" + taskId + "/stream");

  source.onmessage = function (event) {
    if (logEl) {
      logEl.textContent += event.data + "\n";
      logEl.scrollTop = logEl.scrollHeight;
    }
  };

  source.addEventListener("done", function (event) {
    source.close();
    if (logEl) logEl.textContent += "\n── " + (event.data || "completado") + " ──\n";
    if (btn) {
      btn.disabled = false;
      btn.textContent = btn.getAttribute("data-orig") || "OK";
    }
  });

  source.addEventListener("error", function () {
    source.close();
    if (btn) {
      btn.disabled = false;
      btn.textContent = btn.getAttribute("data-orig") || "OK";
    }
  });
}

// ── Study Plan Tab ──

function initStudyPlanTab() {
  var importBtn = document.getElementById("btn-import-plan");
  var refreshBtn = document.getElementById("btn-refresh-programs");
  var fileInput = document.getElementById("xls-file");
  var programSelect = document.getElementById("program-select");

  if (importBtn && fileInput) {
    importBtn.addEventListener("click", function () {
      if (!fileInput.files.length) {
        showStudyPlanMsg("Selecciona un archivo .xls");
        return;
      }

      var formData = new FormData();
      formData.append("file", fileInput.files[0]);

      importBtn.disabled = true;
      importBtn.textContent = "⏳ Importando...";

      fetch("/api/study-plan/import", {
        method: "POST",
        body: formData,
      })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          showStudyPlanMsg(data.message || "OK");
          updateProgramDropdown(data.programs || []);
          importBtn.disabled = false;
          importBtn.textContent = "Importar plan";
        })
        .catch(function (err) {
          showStudyPlanMsg("Error: " + err.message);
          importBtn.disabled = false;
          importBtn.textContent = "Importar plan";
        });
    });
  }

  if (refreshBtn) {
    refreshBtn.addEventListener("click", function () {
      refreshBtn.disabled = true;
      fetch("/api/study-plan/programs")
        .then(function (r) { return r.json(); })
        .then(function (data) {
          updateProgramDropdown(data.programs || []);
          refreshBtn.disabled = false;
        })
        .catch(function () { refreshBtn.disabled = false; });
    });
  }

  if (programSelect) {
    programSelect.addEventListener("change", function () {
      loadStudyPlanTables(programSelect.value);
    });
  }
}

function showStudyPlanMsg(msg) {
  var el = document.getElementById("log-study-plan");
  if (el) el.textContent = msg;
}

function updateProgramDropdown(programs) {
  var sel = document.getElementById("program-select");
  if (!sel) return;

  sel.innerHTML = "";
  if (!programs.length) {
    sel.innerHTML = '<option value="">-- Sin programas --</option>';
    clearStudyPlanTables();
    return;
  }

  programs.forEach(function (p) {
    var opt = document.createElement("option");
    opt.value = p;
    opt.textContent = p;
    sel.appendChild(opt);
  });

  loadStudyPlanTables(programs[0]);
}

function loadStudyPlanTables(program) {
  if (!program) {
    clearStudyPlanTables();
    return;
  }

  var subjectsEl = document.getElementById("subjects-table-wrap");
  var prereqEl = document.getElementById("prereq-table-wrap");

  if (subjectsEl) {
    subjectsEl.innerHTML = '<div class="loading" style="padding:1rem">Cargando...</div>';
    fetch("/api/study-plan/subjects/" + encodeURIComponent(program))
      .then(function (r) { return r.text(); })
      .then(function (html) { subjectsEl.innerHTML = html; });
  }

  if (prereqEl) {
    prereqEl.innerHTML = '<div class="loading" style="padding:1rem">Cargando...</div>';
    fetch("/api/study-plan/prerequisites/" + encodeURIComponent(program))
      .then(function (r) { return r.text(); })
      .then(function (html) { prereqEl.innerHTML = html; });
  }
}

function clearStudyPlanTables() {
  var subjectsEl = document.getElementById("subjects-table-wrap");
  var prereqEl = document.getElementById("prereq-table-wrap");
  if (subjectsEl) subjectsEl.innerHTML = '<div class="empty-state">Selecciona un programa</div>';
  if (prereqEl) prereqEl.innerHTML = '<div class="empty-state">Selecciona un programa</div>';
}

// ── Parameters Tab ──

function initParametersTab() {
  var setBtn = document.getElementById("btn-param-set");
  var delBtn = document.getElementById("btn-param-delete");
  var refreshBtn = document.getElementById("btn-param-refresh");

  if (setBtn) {
    setBtn.addEventListener("click", function () {
      var key = document.getElementById("param-key");
      var val = document.getElementById("param-value");
      var desc = document.getElementById("param-desc");
      if (!key || !key.value.trim()) {
        showParamMsg("La clave no puede estar vacía");
        return;
      }

      var formData = new FormData();
      formData.append("key", key.value);
      formData.append("value", val ? val.value : "");
      formData.append("description", desc ? desc.value : "");

      fetch("/api/parameters/set", {
        method: "POST",
        body: formData,
      })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          showParamMsg(data.message || "OK");
          if (data.html) updateParamTable(data.html);
        });
    });
  }

  if (delBtn) {
    delBtn.addEventListener("click", function () {
      var key = document.getElementById("param-key");
      if (!key || !key.value.trim()) {
        showParamMsg("Indica la clave a eliminar");
        return;
      }

      var formData = new FormData();
      formData.append("key", key.value);

      fetch("/api/parameters/delete", {
        method: "POST",
        body: formData,
      })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          showParamMsg(data.message || "OK");
          if (data.html) updateParamTable(data.html);
        });
    });
  }

  if (refreshBtn) {
    refreshBtn.addEventListener("click", function () {
      refreshParamsTable();
    });
  }
}

function showParamMsg(msg) {
  var el = document.getElementById("log-params");
  if (el) el.textContent = msg;
}

function updateParamTable(html) {
  var wrap = document.getElementById("param-table-wrap");
  if (wrap) wrap.innerHTML = html;
}

function refreshParamsTable() {
  var wrap = document.getElementById("param-table-wrap");
  if (!wrap) return;
  wrap.innerHTML = '<div class="loading" style="padding:1rem">Cargando...</div>';
  fetch("/api/parameters")
    .then(function (r) { return r.text(); })
    .then(function (html) { wrap.innerHTML = html; });
}

// ── Eligibility Tab ──

function initEligibilityTab() {
  var evalBtn = document.getElementById("btn-evaluate");
  if (!evalBtn) return;

  evalBtn.addEventListener("click", function () {
    var identity = document.getElementById("identity-input");
    var period = document.getElementById("period-input");

    var formData = new FormData();
    formData.append("identity", identity ? identity.value : "");
    formData.append("period", period ? period.value : "");

    evalBtn.disabled = true;
    evalBtn.textContent = "⏳ Evaluando...";

    fetch("/api/eligibility/evaluate", {
      method: "POST",
      body: formData,
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        var veredictEl = document.getElementById("veredict");
        var infoEl = document.getElementById("student-info");
        var coursesWrap = document.getElementById("courses-table-wrap");
        var art118El = document.getElementById("art118-output");
        var prereqEl = document.getElementById("prereq-output");

        if (veredictEl) veredictEl.innerHTML = renderMarkdown(data.veredict || "");
        if (infoEl) infoEl.innerHTML = renderMarkdown(data.student_info || "");
        if (art118El) art118El.innerHTML = renderMarkdown(data.art118 || "");
        if (prereqEl) prereqEl.innerHTML = renderMarkdown(data.prereq || "");

        if (coursesWrap && data.courses) {
          coursesWrap.innerHTML = buildCoursesTable(data.courses);
        }

        evalBtn.disabled = false;
        evalBtn.textContent = "Evaluar estudiante";
      })
      .catch(function (err) {
        var veredictEl = document.getElementById("veredict");
        if (veredictEl) veredictEl.textContent = "Error: " + err.message;
        evalBtn.disabled = false;
        evalBtn.textContent = "Evaluar estudiante";
      });
  });
}

function renderMarkdown(text) {
  if (!text) return "";
  var html = text
    .replace(/### (.+)/g, "<h3>$1</h3>")
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/_([^_]+)_/g, "<em>$1</em>")
    .replace(/\n/g, "<br>");
  return html;
}

function buildCoursesTable(courses) {
  if (!courses || !courses.length) {
    return '<div class="empty-state">Sin materias registradas</div>';
  }

  var headers = ["Periodo", "Semestre", "Código", "Nombre", "Nota", "Créd.", "Obs."];
  var html = '<div class="table-wrap"><table class="data-table"><thead><tr>';
  headers.forEach(function (h) { html += "<th>" + h + "</th>"; });
  html += "</tr></thead><tbody>";

  courses.forEach(function (row) {
    html += "<tr>";
    row.forEach(function (cell) {
      html += "<td>" + (cell != null ? cell : "") + "</td>";
    });
    html += "</tr>";
  });

  html += "</tbody></table></div>";
  return html;
}
