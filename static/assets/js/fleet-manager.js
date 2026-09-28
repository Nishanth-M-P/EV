// GridWise AI - Fleet Manager & Table Orchestrator

const FleetManager = (function() {
  let activeFilter = 'all';
  let searchTerm = '';
  let sortBy = 'id';
  let currentPage = 1;
  const rowsPerPage = 10;

  function showToast(message, icon = 'check_circle') {
    const toast = document.getElementById('toast-notification');
    const toastMsg = document.getElementById('toast-message');
    const toastIcon = document.getElementById('toast-icon');
    if (!toast) return;

    toastMsg.textContent = message;
    if (toastIcon) toastIcon.textContent = icon;
    toast.classList.remove('translate-y-12', 'opacity-0', 'pointer-events-none');
    toast.classList.add('translate-y-0', 'opacity-100');

    setTimeout(() => {
      toast.classList.remove('translate-y-0', 'opacity-100');
      toast.classList.add('translate-y-12', 'opacity-0', 'pointer-events-none');
    }, 3500);
  }

  function toggleDrawer(open) {
    const drawerOverlay = document.getElementById('config-drawer-overlay');
    const drawerPanel = document.getElementById('config-drawer-panel');
    if (!drawerOverlay || !drawerPanel) return;

    if (open) {
      drawerOverlay.classList.remove('pointer-events-none', 'opacity-0');
      drawerOverlay.classList.add('opacity-100');
      drawerPanel.classList.remove('translate-x-full');
    } else {
      drawerOverlay.classList.add('pointer-events-none', 'opacity-0');
      drawerOverlay.classList.remove('opacity-100');
      drawerPanel.classList.add('translate-x-full');
    }
  }

  function renderTable(tableBodyId = 'fleet-table-body', isFullView = true) {
    const tbody = document.getElementById(tableBodyId);
    if (!tbody) return;

    let fleet = SimEngine.getFleet();

    // Filtering
    fleet = fleet.filter(ev => {
      const matchesFilter = (activeFilter === 'all') || (ev.status === activeFilter);
      const sTerm = searchTerm.toLowerCase();
      const matchesSearch = !sTerm || 
        ev.id.toLowerCase().includes(sTerm) || 
        ev.model.toLowerCase().includes(sTerm) ||
        ev.bus.toLowerCase().includes(sTerm);
      return matchesFilter && matchesSearch;
    });

    // Sorting
    fleet.sort((a, b) => {
      if (sortBy === 'id') return a.id.localeCompare(b.id);
      if (sortBy === 'soc') return b.soc - a.soc;
      if (sortBy === 'power') return b.power - a.power;
      if (sortBy === 'departure') return a.depTime.localeCompare(b.depTime);
      if (sortBy === 'capacity') return b.pack - a.pack;
      return 0;
    });

    // Pagination for full fleet view
    const totalCount = fleet.length;
    const totalPages = Math.ceil(totalCount / rowsPerPage) || 1;
    if (currentPage > totalPages) currentPage = totalPages;
    if (currentPage < 1) currentPage = 1;

    const displayRows = isFullView ? fleet.slice((currentPage - 1) * rowsPerPage, currentPage * rowsPerPage) : fleet.slice(0, 6);

    let html = '';
    displayRows.forEach(ev => {
      let statusBadge = '';
      let powerColor = 'text-outline';
      let socColor = 'bg-primary';

      if (ev.status === 'charging') {
        statusBadge = `
          <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-label-caps uppercase bg-primary/10 text-primary font-semibold">
            <span class="material-symbols-outlined text-[13px]">arrow_downward</span> Charging
          </span>`;
        powerColor = 'text-primary';
        socColor = 'bg-primary';
      } else if (ev.status === 'discharging') {
        statusBadge = `
          <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-label-caps uppercase bg-secondary/10 text-secondary font-semibold">
            <span class="material-symbols-outlined text-[13px]">arrow_upward</span> Discharging (V2G)
          </span>`;
        powerColor = 'text-secondary';
        socColor = 'bg-secondary';
      } else if (ev.status === 'idle') {
        statusBadge = `
          <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-label-caps uppercase bg-surface-container text-outline font-semibold">
            <span class="material-symbols-outlined text-[13px]">pause</span> Standby / Idle
          </span>`;
        socColor = 'bg-surface-bright';
      } else if (ev.status === 'completed') {
        statusBadge = `
          <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-label-caps uppercase bg-tertiary/10 text-tertiary font-semibold">
            <span class="material-symbols-outlined text-[13px]">check_circle</span> Ready / Complete
          </span>`;
        socColor = 'bg-tertiary';
      } else {
        statusBadge = `
          <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-label-caps uppercase bg-surface-container text-outline">
            <span class="material-symbols-outlined text-[13px]">directions_car</span> Away
          </span>`;
        socColor = 'bg-outline';
      }

      const powerFormatted = (ev.power > 0) ? `+${ev.power.toFixed(2)} kW` : (ev.power < 0) ? `${ev.power.toFixed(2)} kW` : `0.00 kW`;

      html += `
        <tr class="ev-row hover:bg-surface-container-high/40 transition-colors group">
          <td class="py-2.5 px-space-md font-telemetry-md text-telemetry-md font-semibold ${ev.status === 'discharging' ? 'text-secondary' : 'text-primary'}">
            <div class="flex items-center gap-space-xs">
              <span class="w-1.5 h-1.5 rounded-full ${ev.status === 'discharging' ? 'bg-secondary' : 'bg-primary'}"></span>
              <span>${ev.id}</span>
            </div>
          </td>
          <td class="py-2.5 px-space-md">
            <div class="flex flex-col">
              <span class="text-on-surface font-medium">${ev.model}</span>
              <span class="font-telemetry-sm text-telemetry-sm text-outline">${ev.pack} kWh Pack • <span class="text-secondary">${ev.bus}</span></span>
            </div>
          </td>
          <td class="py-2.5 px-space-md min-w-[140px]">
            <div class="flex items-center justify-between font-telemetry-sm text-telemetry-sm mb-1">
              <span class="text-on-surface font-semibold">${ev.soc}%</span>
              <span class="text-outline">Target ${ev.targetSoc}%</span>
            </div>
            <div class="w-full bg-surface-container-high rounded-full h-1.5 overflow-hidden">
              <div class="${socColor} h-full rounded-full" style="width: ${Math.min(100, ev.soc)}%"></div>
            </div>
          </td>
          <td class="py-2.5 px-space-md">
            ${statusBadge}
          </td>
          <td class="py-2.5 px-space-md text-right font-telemetry-md text-telemetry-md ${powerColor} font-medium">
            ${powerFormatted}
          </td>
          <td class="py-2.5 px-space-md font-telemetry-sm text-telemetry-sm text-on-surface-variant">
            <div class="flex items-center gap-1">
              <span>${ev.arrTime}</span>
              <span class="text-outline">→</span>
              <span class="text-on-surface font-medium">${ev.depTime}</span>
            </div>
          </td>
          <td class="py-2.5 px-space-md text-center font-telemetry-sm text-telemetry-sm">
            <span class="px-2 py-0.5 rounded bg-surface-container font-medium ${ev.soc >= ev.targetSoc ? 'text-primary' : 'text-on-surface'}">${ev.targetSoc}% ${ev.soc >= ev.targetSoc ? '✓' : ''}</span>
          </td>
          <td class="py-2.5 px-space-md text-right font-telemetry-sm text-telemetry-sm text-on-surface">
            ${ev.energyExchanged} kWh
          </td>
          <td class="py-2.5 px-space-md text-right font-telemetry-sm text-telemetry-sm ${ev.power < 0 ? 'text-primary font-semibold' : 'text-tertiary font-medium'}">
            ${ev.financial}
          </td>
          <td class="py-2.5 px-space-md text-center">
            <div class="flex items-center justify-center gap-1">
              <button class="p-1 rounded hover:bg-surface-container text-on-surface-variant hover:text-primary transition-colors" title="Inspect Node Inflow" onclick="FleetManager.inspectEV('${ev.id}')">
                <span class="material-symbols-outlined text-[16px]">visibility</span>
              </button>
              <button class="p-1 rounded hover:bg-surface-container text-on-surface-variant hover:text-secondary transition-colors" title="Manual Control Override" onclick="FleetManager.overrideEV('${ev.id}')">
                <span class="material-symbols-outlined text-[16px]">tune</span>
              </button>
              <button class="p-1 rounded hover:bg-surface-container text-on-surface-variant hover:text-error transition-colors" title="Emergency Disconnect" onclick="FleetManager.disconnectEV('${ev.id}')">
                <span class="material-symbols-outlined text-[16px]">power_off</span>
              </button>
            </div>
          </td>
        </tr>
      `;
    });

    tbody.innerHTML = html;

    // Update pagination controls
    const pageDisplay = document.getElementById('pagination-display');
    if (pageDisplay) {
      pageDisplay.textContent = `Page ${currentPage} / ${totalPages}`;
    }
    const prevBtn = document.getElementById('prev-page-btn');
    const nextBtn = document.getElementById('next-page-btn');
    if (prevBtn) prevBtn.disabled = (currentPage <= 1);
    if (nextBtn) nextBtn.disabled = (currentPage >= totalPages);

    const countDisplay = document.getElementById('fleet-count-display');
    if (countDisplay) {
      countDisplay.textContent = `Showing ${displayRows.length} of ${totalCount} Node Connections`;
    }
  }

  function initListeners() {
    // Drawer buttons
    const openDrawerBtn = document.getElementById('open-config-btn');
    const closeDrawerBtn = document.getElementById('close-config-btn');
    const drawerOverlay = document.getElementById('config-drawer-overlay');
    const evForm = document.getElementById('ev-config-form');
    const resetDefaultsBtn = document.getElementById('reset-defaults-btn');
    const reqSocSlider = document.getElementById('cfg-req-soc');
    const reqSocVal = document.getElementById('cfg-req-soc-val');
    const batchImportBtn = document.getElementById('batch-import-btn');
    const searchInput = document.getElementById('ev-search-input');
    const sortSelect = document.getElementById('sort-select');

    if (openDrawerBtn) openDrawerBtn.onclick = () => toggleDrawer(true);
    if (closeDrawerBtn) closeDrawerBtn.onclick = () => toggleDrawer(false);
    if (drawerOverlay) {
      drawerOverlay.onclick = (e) => {
        if (e.target === drawerOverlay) toggleDrawer(false);
      };
    }

    if (reqSocSlider && reqSocVal) {
      reqSocSlider.oninput = (e) => {
        reqSocVal.textContent = e.target.value + '%';
      };
    }

    if (resetDefaultsBtn && evForm) {
      resetDefaultsBtn.onclick = () => {
        evForm.reset();
        if (reqSocVal) reqSocVal.textContent = '85%';
        showToast('Form parameters restored to environment baseline.');
      };
    }

    if (batchImportBtn) {
      batchImportBtn.onclick = () => {
        showToast('CSV Batch Ingestion: 16 EV profiles validated & scheduled.');
      };
    }

    if (searchInput) {
      searchInput.oninput = (e) => {
        searchTerm = e.target.value.trim();
        renderTable();
      };
    }

    if (sortSelect) {
      sortSelect.onchange = (e) => {
        sortBy = e.target.value;
        renderTable();
        showToast(`Sorted table by ${sortSelect.options[sortSelect.selectedIndex].text}`);
      };
    }

    // Filter buttons
    const filterBtns = document.querySelectorAll('.filter-chip');
    filterBtns.forEach(btn => {
      btn.onclick = () => {
        filterBtns.forEach(b => {
          b.classList.remove('bg-primary', 'text-on-primary', 'font-semibold');
          b.classList.add('bg-surface-container-high', 'text-on-surface-variant');
        });
        btn.classList.add('bg-primary', 'text-on-primary', 'font-semibold');
        btn.classList.remove('bg-surface-container-high', 'text-on-surface-variant');
        activeFilter = btn.getAttribute('data-filter') || 'all';
        currentPage = 1;
        renderTable();
      };
    });

    // Pagination buttons
    const prevBtn = document.getElementById('prev-page-btn');
    const nextBtn = document.getElementById('next-page-btn');
    if (prevBtn) {
      prevBtn.onclick = () => {
        if (currentPage > 1) {
          currentPage--;
          renderTable();
        }
      };
    }
    if (nextBtn) {
      nextBtn.onclick = () => {
        currentPage++;
        renderTable();
      };
    }

    // Form submit
    if (evForm) {
      evForm.onsubmit = (e) => {
        e.preventDefault();
        const evId = document.getElementById('cfg-ev-id')?.value || 'EV-051';
        const modelDesc = document.getElementById('cfg-model-desc')?.value || 'Commercial Utility';
        const capacity = parseFloat(document.getElementById('cfg-capacity')?.value || 65.0);
        const initialSoc = parseFloat(document.getElementById('cfg-initial-soc')?.value || 48.0);
        const arrTime = document.getElementById('cfg-arr-time')?.value || '09:15';
        const depTime = document.getElementById('cfg-dep-time')?.value || '18:30';
        const reqSoc = parseFloat(document.getElementById('cfg-req-soc')?.value || 85.0);
        const maxCharge = parseFloat(document.getElementById('cfg-max-charge')?.value || 11.0);
        const maxDischarge = parseFloat(document.getElementById('cfg-max-discharge')?.value || 10.0);

        const newEV = {
          id: evId,
          model: modelDesc,
          pack: capacity,
          chem: "LFP",
          bus: "BUS-14",
          cluster: "Sub-Station A Hub",
          soc: initialSoc,
          targetSoc: reqSoc,
          status: "charging",
          power: maxCharge,
          maxCharge: maxCharge,
          maxDischarge: maxDischarge,
          arrTime: arrTime,
          depTime: depTime,
          energyExchanged: 0.0,
          financial: "₹0.00"
        };

        SimEngine.addEv(newEV);
        toggleDrawer(false);
        renderTable();
        showToast(`${evId} successfully registered to Substation Bus 14.`);
      };
    }
  }

  function inspectEV(id) {
    const ev = SimEngine.getFleet().find(e => e.id === id);
    if (!ev) return;
    showToast(`Inspecting ${id}: SOC ${ev.soc}%, Bus ${ev.bus}, Power ${ev.power} kW`, 'visibility');
  }

  function overrideEV(id) {
    const ev = SimEngine.getFleet().find(e => e.id === id);
    if (!ev) return;
    // Toggle between charging and discharging
    const newPower = (ev.power > 0) ? -5.0 : 7.2;
    const newStatus = (newPower > 0) ? 'charging' : 'discharging';
    SimEngine.updateEv(id, { power: newPower, status: newStatus });
    renderTable();
    showToast(`Manual Override: ${id} set to ${newStatus.toUpperCase()} (${newPower} kW)`, 'tune');
  }

  function disconnectEV(id) {
    SimEngine.updateEv(id, { power: 0.0, status: 'idle' });
    renderTable();
    showToast(`Emergency Interlock: ${id} safely disconnected. Power flow zeroed.`, 'power_off');
  }

  return {
    renderTable,
    initListeners,
    toggleDrawer,
    showToast,
    inspectEV,
    overrideEV,
    disconnectEV
  };
})();

