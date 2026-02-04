(function () {
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
        if (window.innerWidth <= 480) {
          row.classList.add("collapsed");
        } else {
          row.classList.remove("collapsed");
        }
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

    tbody.addEventListener("click", (event) => {
      const row = event.target.closest("tr");
      if (!row || window.innerWidth > 480) return;
      row.classList.toggle("collapsed");
    });

    if (filterToggle && filterPanel) {
      filterToggle.addEventListener("click", () => {
        filterPanel.classList.toggle("open");
      });
    }

    applyFilter();
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

    buttons.forEach((btn) => {
      btn.addEventListener("click", () => {
        document.body.classList.toggle("sidebar-collapsed");
        const collapsed = document.body.classList.contains("sidebar-collapsed");
        localStorage.setItem("sidebar", collapsed ? "collapsed" : "expanded");
      });
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll(".table-block").forEach(setupTable);
    document.querySelectorAll(".filters").forEach(setupFilters);
    setupFileInputs();
    setupThemeToggle();
    setupSidebarToggle();
  });
})();
