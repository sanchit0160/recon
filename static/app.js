(function () {
  window.__appReady = true;
  window.__appErrors = [];
  function guard(fn, label) {
    try {
      fn();
    } catch (err) {
      window.__appErrors.push(`${label}: ${err}`);
      console.error("App JS error in " + label, err);
    }
  }
  function setupTable(block) {
    const table = block.querySelector("table");
    if (!table) return;

    const tbody = table.querySelector("tbody");
    const rows = Array.from(table.querySelectorAll("tbody tr"));
    if (!rows.length) return;

    const searchInput = block.querySelector(".table-search");
    const pageSizeSelect = block.querySelector(".table-page-size");
    const prevBtn = block.querySelector(".pager.prev");
    const nextBtn = block.querySelector(".pager.next");
    const pageInfo = block.querySelector(".page-info");
    const tabs = Array.from(block.querySelectorAll(".tab"));
    const headers = Array.from(table.querySelectorAll("thead th.sortable"));
    const filterPanel = block.querySelector(".filter-panel");
    const filterToggle = block.querySelector("[data-open-filters]");

    let statusFilter = block.dataset.defaultFilter || "all";
    let filtered = rows.slice();
    let pageSize = parseInt(pageSizeSelect?.value || "10", 10);
    let page = 1;
    let sortIndex = -1;
    let sortDir = "asc";

    function parseValue(value) {
      const trimmed = value.trim();
      if (/^\d+\.\d+\.\d+\.\d+$/.test(trimmed)) {
        return trimmed
          .split(".")
          .map((part) => part.padStart(3, "0"))
          .join(".");
      }
      if (/^\d+(\.\d+)?$/.test(trimmed)) {
        return Number(trimmed);
      }
      return trimmed.toLowerCase();
    }

    function applyFilter() {
      const query = (searchInput?.value || "").trim().toLowerCase();
      filtered = rows.filter((row) => {
        if (statusFilter !== "all" && row.dataset.status !== statusFilter) {
          return false;
        }
        if (!query) return true;
        return row.textContent.toLowerCase().includes(query);
      });
      page = 1;
      render();
    }

    function sortRows() {
      if (sortIndex < 0) return;
      const getCellText = (row) => {
        const cell = row.children[sortIndex];
        return cell ? cell.textContent : "";
      };
      filtered.sort((a, b) => {
        const aVal = parseValue(getCellText(a));
        const bVal = parseValue(getCellText(b));
        if (typeof aVal === "number" && typeof bVal === "number") {
          return sortDir === "asc" ? aVal - bVal : bVal - aVal;
        }
        if (aVal < bVal) return sortDir === "asc" ? -1 : 1;
        if (aVal > bVal) return sortDir === "asc" ? 1 : -1;
        return 0;
      });
    }

    function render() {
      sortRows();
      const total = filtered.length;
      const totalPages = Math.max(1, Math.ceil(total / pageSize));
      page = Math.min(page, totalPages);

      const start = (page - 1) * pageSize;
      const end = start + pageSize;

      rows.forEach((row) => (row.style.display = "none"));
      filtered.slice(start, end).forEach((row) => {
        row.style.display = "table-row";
        tbody.appendChild(row);
      });

      if (pageInfo) {
        pageInfo.textContent = `Page ${page} of ${totalPages} · ${total} rows`;
      }

      if (prevBtn) prevBtn.disabled = page <= 1;
      if (nextBtn) nextBtn.disabled = page >= totalPages;
    }

    if (searchInput) {
      searchInput.addEventListener("input", applyFilter);
    }

    if (pageSizeSelect) {
      pageSizeSelect.addEventListener("change", () => {
        pageSize = parseInt(pageSizeSelect.value, 10) || 10;
        page = 1;
        render();
      });
    }

    if (prevBtn) {
      prevBtn.addEventListener("click", () => {
        page = Math.max(1, page - 1);
        render();
      });
    }

    if (nextBtn) {
      nextBtn.addEventListener("click", () => {
        page = page + 1;
        render();
      });
    }

    tabs.forEach((tab) => {
      tab.addEventListener("click", () => {
        tabs.forEach((t) => t.classList.remove("active"));
        tab.classList.add("active");
        statusFilter = tab.dataset.filter || "all";
        applyFilter();
      });
    });

    headers.forEach((header, index) => {
      header.addEventListener("click", () => {
        if (sortIndex === index) {
          sortDir = sortDir === "asc" ? "desc" : "asc";
        } else {
          sortIndex = index;
          sortDir = "asc";
        }
        render();
      });
    });

    function setupCardToggles() {}

    if (filterToggle && filterPanel) {
      filterToggle.addEventListener("click", () => {
        filterPanel.classList.toggle("open");
      });
    }

    function setupViewToggle() {}

    applyFilter();
    setupViewToggle();
    setupCardToggles();
  }

  function setupFilters(form) {
    const regionSelect = form.querySelector('select[name="region"]');
    const deptSelect = form.querySelector('select[name="department"]');
    if (!regionSelect || !deptSelect) return;

    let deptMap = {};
    if (form.dataset.deptMap) {
      try {
        deptMap = JSON.parse(form.dataset.deptMap);
      } catch (err) {
        deptMap = {};
      }
    }

    function updateDepartments(region) {
      const options = deptMap[region || ""] || [];
      const current = deptSelect.value;

      const fragment = document.createDocumentFragment();
      const allOption = document.createElement("option");
      allOption.value = "";
      allOption.textContent = "All";
      fragment.appendChild(allOption);

      options.forEach((dept) => {
        const opt = document.createElement("option");
        opt.value = dept;
        opt.textContent = dept;
        fragment.appendChild(opt);
      });

      deptSelect.innerHTML = "";
      deptSelect.appendChild(fragment);

      if (current && options.includes(current)) {
        deptSelect.value = current;
      }
    }

    updateDepartments(regionSelect.value);

    regionSelect.addEventListener("change", () => {
      updateDepartments(regionSelect.value);
    });
  }

  function setupFileInputs() {
    document.querySelectorAll(".file-upload").forEach((wrapper) => {
      const input = wrapper.querySelector('input[type="file"]');
      const label = wrapper.querySelector(".file-label");
      if (!input || !label) return;

      input.addEventListener("change", () => {
        const name = input.files && input.files.length ? input.files[0].name : "Choose file";
        label.textContent = name;
      });
    });
  }

  function setupThemeToggle() {
    const buttons = Array.from(document.querySelectorAll("[data-theme-toggle]"));
    if (!buttons.length) return;

    const stored = localStorage.getItem("theme") || "dark";
    if (stored === "light") {
      document.body.classList.add("theme-light");
    }

    function updateLabels() {
      const isLight = document.body.classList.contains("theme-light");
      buttons.forEach((btn) => {
        btn.textContent = isLight ? "Dark mode" : "Light mode";
      });
    }

    updateLabels();

    buttons.forEach((btn) => {
      btn.addEventListener("click", () => {
        document.body.classList.toggle("theme-light");
        const isLight = document.body.classList.contains("theme-light");
        localStorage.setItem("theme", isLight ? "light" : "dark");
        updateLabels();
      });
    });
  }

  function setupSidebarToggle() {
    const buttons = Array.from(document.querySelectorAll("[data-sidebar-toggle]"));
    if (!buttons.length) return;

    const stored = localStorage.getItem("sidebar") || "expanded";
    if (stored === "collapsed") {
      document.body.classList.add("sidebar-collapsed");
    }

    let overlay = null;
    const sidebar = document.querySelector(".sidebar");
    function openOverlay() {
      if (overlay) return;
      overlay = document.createElement("div");
      overlay.className = "sidebar-overlay";
      overlay.addEventListener("click", () => {
        document.body.classList.remove("sidebar-open");
        overlay.remove();
        overlay = null;
      });
      document.body.appendChild(overlay);
    }

    function closeOverlay() {
      if (overlay) {
        overlay.remove();
        overlay = null;
      }
    }

    buttons.forEach((btn) => {
      btn.addEventListener("click", (event) => {
        event.stopPropagation();
        if (window.innerWidth <= 720) {
          document.body.classList.toggle("sidebar-open");
          const isOpen = document.body.classList.contains("sidebar-open");
          btn.setAttribute("aria-expanded", String(isOpen));
          if (isOpen) {
            openOverlay();
          } else {
            closeOverlay();
          }
        } else {
          document.body.classList.toggle("sidebar-collapsed");
          const collapsed = document.body.classList.contains("sidebar-collapsed");
          localStorage.setItem("sidebar", collapsed ? "collapsed" : "expanded");
          btn.setAttribute("aria-expanded", String(!collapsed));
        }
      });
    });

    document.querySelectorAll(".nav-link").forEach((link) => {
      link.addEventListener("click", () => {
        if (window.innerWidth <= 720) {
          document.body.classList.remove("sidebar-open");
          closeOverlay();
        }
      });
    });

    document.addEventListener("click", (event) => {
      const target = event.target;
      const isToggle = target.closest("[data-sidebar-toggle]");
      if (isToggle) return;
      if (!sidebar) return;
      const clickedInside = sidebar.contains(target);
      if (!clickedInside) {
        if (window.innerWidth <= 720) {
          if (document.body.classList.contains("sidebar-open")) {
            document.body.classList.remove("sidebar-open");
            closeOverlay();
          }
        } else if (document.body.classList.contains("sidebar-collapsed") === false) {
          document.body.classList.add("sidebar-collapsed");
          localStorage.setItem("sidebar", "collapsed");
        }
      }
    });

    window.addEventListener("resize", () => {
      if (window.innerWidth > 720) {
        document.body.classList.remove("sidebar-open");
        closeOverlay();
      }
    });
  }


  function setupPasswordToggles() {
    document.querySelectorAll('[data-toggle-password]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const input = btn.parentElement?.querySelector('input');
        if (!input) return;
        const isHidden = input.type === 'password';
        input.type = isHidden ? 'text' : 'password';
        btn.textContent = isHidden ? 'Hide' : 'Show';
      });
    });
  }

  function setupSubmissionForm() {
    const form = document.querySelector(".submission-form");
    if (!form) return;

    const fields = ["itam_id", "hostname", "ip_address", "environment", "region", "justification", "exception_reason"];
    const draftKey = "submission_draft";
    const exceptionToggle = form.querySelector("#is_exception");
    const exceptionPanel = form.querySelector(".exception-panel");

    const saved = localStorage.getItem(draftKey);
    if (saved) {
      try {
        const data = JSON.parse(saved);
        fields.forEach((name) => {
          const input = form.querySelector(`[name="${name}"]`);
        if (input && data[name]) {
          input.value = data[name];
        }
      });
      } catch (err) {}
    }

    form.addEventListener("input", () => {
      const data = {};
      fields.forEach((name) => {
        const input = form.querySelector(`[name="${name}"]`);
        if (input) {
          data[name] = input.value;
        }
      });
      localStorage.setItem(draftKey, JSON.stringify(data));
    });

    form.addEventListener("submit", () => {
      localStorage.removeItem(draftKey);
    });

    const itamIdInput = form.querySelector('[name="itam_id"]');
    const hostnameInput = form.querySelector('[name="hostname"]');
    const ipInput = form.querySelector('[name="ip_address"]');
    const envInput = form.querySelector('[name="environment"]');
    const regionInput = form.querySelector('[name="region"]');
    const matchCard = document.querySelector(".match-card");
    const validationBox = document.createElement("div");
    validationBox.className = "validation";
    form.prepend(validationBox);

    async function lookup() {
      const itamId = itamIdInput?.value || "";
      const hostname = hostnameInput?.value || "";
      const ipAddress = ipInput?.value || "";
      if (!itamId && !hostname && !ipAddress) return;
      const params = new URLSearchParams();
      if (itamId) params.append("itam_id", itamId);
      if (hostname) params.append("hostname", hostname);
      if (ipAddress) params.append("ip_address", ipAddress);
      try {
        const res = await fetch(`/api/itam_lookup?${params.toString()}`);
        if (!res.ok) return;
        const data = await res.json();
        if (itamIdInput && data.itam_id && !itamIdInput.value) itamIdInput.value = data.itam_id;
        if (hostnameInput && data.hostname && !hostnameInput.value) hostnameInput.value = data.hostname;
        if (ipInput && data.ip_address && !ipInput.value) ipInput.value = data.ip_address;
        if (envInput && data.environment && !envInput.value) envInput.value = data.environment;
        if (regionInput && data.region && !regionInput.value) regionInput.value = data.region;
        if (matchCard && (data.environment || data.region)) {
          matchCard.innerHTML = `<strong>ITAM Match</strong><p class="subtle">Environment: ${data.environment || "-"} · Region: ${data.region || "-"}</p>`;
        }
      } catch (err) {}
    }

    if (itamIdInput) itamIdInput.addEventListener("input", lookup);
    if (hostnameInput) hostnameInput.addEventListener("blur", lookup);
    if (ipInput) ipInput.addEventListener("blur", lookup);

    function lockFields(locked) {
      if (hostnameInput) hostnameInput.readOnly = locked;
      if (ipInput) ipInput.readOnly = locked;
      if (envInput) envInput.readOnly = locked;
      if (regionInput) regionInput.readOnly = locked;
    }

    if (itamIdInput) {
      itamIdInput.addEventListener("input", () => {
        const hasValue = !!itamIdInput.value.trim();
        lockFields(hasValue);
      });
    }

    const clearBtn = document.createElement("button");
    clearBtn.type = "button";
    clearBtn.className = "ghost";
    clearBtn.textContent = "Clear auto-fill";
    clearBtn.addEventListener("click", () => {
      if (itamIdInput) itamIdInput.value = "";
      if (hostnameInput) hostnameInput.value = "";
      if (ipInput) ipInput.value = "";
      if (envInput) envInput.value = "";
      if (regionInput) regionInput.value = "";
      lockFields(false);
      if (matchCard) {
        matchCard.innerHTML = `<strong>ITAM Match</strong><p class="subtle">Fill hostname or IP to auto‑fill environment/region.</p>`;
      }
    });
    if (matchCard && !matchCard.querySelector(".ghost")) {
      matchCard.appendChild(clearBtn);
    }

    function updateExceptionPanel() {
      if (!exceptionPanel || !exceptionToggle) return;
      exceptionPanel.classList.toggle("hidden", !exceptionToggle.checked);
    }

    if (exceptionToggle) {
      exceptionToggle.addEventListener("change", updateExceptionPanel);
      updateExceptionPanel();
    }

    function validate() {
      const issues = [];
      const host = hostnameInput?.value || "";
      const ip = ipInput?.value || "";
      if (host && !/^[A-Za-z0-9][A-Za-z0-9.-]{0,251}[A-Za-z0-9]$/.test(host)) {
        issues.push("Hostname looks invalid.");
      }
      if (ip && !/^\d{1,3}(?:\.\d{1,3}){3}(?:\/\d{1,2})?$/.test(ip)) {
        issues.push("IP address looks invalid.");
      }
      validationBox.textContent = issues.join(" ");
    }

    if (hostnameInput) hostnameInput.addEventListener("input", validate);
    if (ipInput) ipInput.addEventListener("input", validate);

    form.addEventListener("submit", (e) => {
      if (!confirm("Submit this server for integration?")) {
        e.preventDefault();
      }
    });
  }

  function setupCompactTabs() {
    document.querySelectorAll("[data-tab-group]").forEach((group) => {
      const buttons = Array.from(group.querySelectorAll("[data-tab-target]"));
      const panels = Array.from(group.querySelectorAll("[data-tab-panel]"));
      if (!buttons.length || !panels.length) return;

      function activate(target) {
        buttons.forEach((btn) => btn.classList.toggle("active", btn.dataset.tabTarget === target));
        panels.forEach((panel) => panel.classList.toggle("active", panel.dataset.tabPanel === target));
      }

      buttons.forEach((btn) => {
        btn.addEventListener("click", () => {
          activate(btn.dataset.tabTarget);
        });
      });
    });
  }

  function init() {
    document.querySelectorAll(".table-block").forEach((block) => guard(() => setupTable(block), "setupTable"));
    document.querySelectorAll(".filters").forEach((form) => guard(() => setupFilters(form), "setupFilters"));
    guard(setupFileInputs, "setupFileInputs");
    guard(setupThemeToggle, "setupThemeToggle");
    guard(setupSidebarToggle, "setupSidebarToggle");
    guard(setupSubmissionForm, "setupSubmissionForm");
    guard(setupPasswordToggles, "setupPasswordToggles");
    guard(setupCompactTabs, "setupCompactTabs");
    window.__appInit = true;
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
