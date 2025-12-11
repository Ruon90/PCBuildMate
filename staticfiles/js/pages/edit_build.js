// Per-page JS for edit_build (migrated from inline template)
(function(){
  document.addEventListener("DOMContentLoaded", () => {
    // Toggle view buttons
    const basicBtn = document.getElementById("basicBtn");
    const advancedBtn = document.getElementById("advancedBtn");
    const basicView = document.getElementById("basicView");
    const advancedView = document.getElementById("advancedView");
    const modeField = document.getElementById("mode");

    if (basicBtn && advancedBtn && basicView && advancedView && modeField) {
      basicBtn.addEventListener("click", () => {
        basicView.classList.remove("d-none");
        advancedView.classList.add("d-none");
        modeField.value = "basic";
        basicBtn.classList.add("btn-primary");
        basicBtn.classList.remove("btn-outline-secondary");
        advancedBtn.classList.add("btn-outline-secondary");
        advancedBtn.classList.remove("btn-primary");
      });

      advancedBtn.addEventListener("click", () => {
        basicView.classList.add("d-none");
        advancedView.classList.remove("d-none");
        modeField.value = "advanced";
        advancedBtn.classList.add("btn-primary");
        advancedBtn.classList.remove("btn-outline-secondary");
        basicBtn.classList.add("btn-outline-secondary");
        basicBtn.classList.remove("btn-primary");
        // When showing advanced view, re-run validation so the included advanced partial
        // displays the same tooltips/invalid outlines as the preview editor.
        if (typeof window.runAllValidation === 'function') window.runAllValidation();
      });
    }

    // Compatibility/filters logic
    const cpuSelect = document.getElementById("cpu");
    const gpuSelect = document.getElementById("gpu");
    const ramSelect = document.getElementById("ram");
    const moboSelect = document.getElementById("motherboard");
    const caseSelect = document.getElementById("case");
    const psuSelect = document.getElementById("psu");
    const coolerSelect = document.getElementById("cooler");
    const storageSelect = document.getElementById("storage");

    if (!cpuSelect || !gpuSelect || !ramSelect || !moboSelect) {
      // Required selects not present; nothing to do.
      return;
    }

    const cpuClear = document.getElementById("cpuClear");
    const gpuClear = document.getElementById("gpuClear");
    const ramClear = document.getElementById("ramClear");
    const storageClear = document.getElementById("storageClear");
    const psuClear = document.getElementById("psuClear");
    const coolerClear = document.getElementById("coolerClear");
    const moboSocketClear = document.getElementById("moboSocketClear");
    const caseFormClear = document.getElementById("caseFormClear");

    function normalizeDDR(s){ return s ? s.toString().trim().toUpperCase() : ""; }
    function normalizeFF(s){
      if (!s) return "";
      const v = s.toLowerCase().replace(/\s|-/g,"");
      if (v.includes("miniitx")) return "mini-itx";
      if (v.includes("microatx")) return "microatx";
      if (v.includes("atx")) return "atx";
      if (v.includes("tower")) return "tower";
      return v;
    }
    function normalizeIface(s){
      if (!s) return "";
      const v = s.toLowerCase();
      if (v.includes("pcie") || v.includes("nvme")) {
        if (v.includes("gen5")) return "pcie gen5";
        if (v.includes("gen4")) return "pcie gen4";
        return "pcie gen3";
      }
      if (v.includes("sata")) return "sata";
      return v;
    }

    function showTooltip(id,msg){ const el=document.getElementById(id); if(el){ el.textContent=msg; el.classList.remove('d-none'); } }
    function hideTooltip(id){ const el=document.getElementById(id); if(el){ el.classList.add('d-none'); el.textContent = ""; } }
    function markInvalid(sel){ if(sel){ sel.classList.add("is-invalid"); sel.setAttribute("aria-invalid","true"); } }
    function clearInvalid(sel){ if(sel){ sel.classList.remove("is-invalid"); sel.removeAttribute("aria-invalid"); } }

    function setCpuMoboInvalid(invalid, moboMsg, cpuMsg){
      if(invalid){
        if (moboMsg) showTooltip("moboMessage", moboMsg);
        if (cpuMsg) showTooltip("cpuMessage", cpuMsg);
        markInvalid(moboSelect);
        markInvalid(cpuSelect);
      } else {
        clearInvalid(moboSelect);
        clearInvalid(cpuSelect);
        hideTooltip("moboMessage");
        hideTooltip("cpuMessage");
      }
    }

    function ensureSelection(select){
      if(!select) return;
      const sel = select.selectedOptions[0];
      if (!sel || sel.hidden) {
        const firstVisible = [...select.options].find(o => !o.hidden);
        if (firstVisible) firstVisible.selected = true;
      }
    }

    function activate(groupId, btn){
      document.querySelectorAll(`#${groupId} button`).forEach(b=>{
        b.classList.remove("btn-primary");
        b.classList.add("btn-outline-primary");
      });
      btn.classList.remove("btn-outline-primary");
      btn.classList.add("btn-primary");
    }

    function filterMobosByCpu(showTip=false){
      const cpuSocket = cpuSelect.selectedOptions[0]?.dataset.socket || "";
      const moboSocket = moboSelect.selectedOptions[0]?.dataset.socket || "";
      const incompatible = !!(cpuSocket && moboSocket && cpuSocket !== moboSocket);
      if (incompatible) {
        setCpuMoboInvalid(true, `CPU socket mismatch. Select a ${cpuSocket} motherboard.`, `Selected CPU socket ${cpuSocket} is not supported by the current motherboard.`);
      } else {
        setCpuMoboInvalid(false);
      }
    }

    function filterMobosByRam(showTip=false){
      const ramDDR = normalizeDDR(ramSelect.selectedOptions[0]?.dataset.ddr);
      const moboDDR = normalizeDDR(moboSelect.selectedOptions[0]?.dataset.ddr);
      const incompatible = !!(ramDDR && moboDDR && ramDDR !== moboDDR);
      if (incompatible) {
        showTooltip("ramMessage", `Selected RAM (${ramDDR}) may not be supported by motherboard.`);
        showTooltip("moboMessage", `Motherboard may not support selected RAM (${ramDDR}).`);
        markInvalid(moboSelect);
        markInvalid(ramSelect);
      } else {
        clearInvalid(moboSelect);
        clearInvalid(ramSelect);
        hideTooltip("ramMessage");
        hideTooltip("moboMessage");
      }
    }

    function filterRamByMobo(showTip=false){
      const moboDDR = normalizeDDR(moboSelect.selectedOptions[0]?.dataset.ddr);
      const ramDDR = normalizeDDR(ramSelect.selectedOptions[0]?.dataset.ddr);
      const incompatible = !!(moboDDR && ramDDR && moboDDR !== ramDDR);
      if (incompatible) {
        showTooltip("moboMessage", `Use ${moboDDR} RAM for this motherboard.`);
        showTooltip("ramMessage", `Selected RAM is not compatible with the motherboard. Use ${moboDDR} RAM.`);
        markInvalid(ramSelect);
        markInvalid(moboSelect);
      } else {
        clearInvalid(ramSelect);
        clearInvalid(moboSelect);
        hideTooltip("moboMessage");
        hideTooltip("ramMessage");
      }
    }

    function filterCases(showTip=false) {
      const moboFF = normalizeFF(moboSelect.selectedOptions[0]?.dataset.formfactor || "");
      const caseFF = normalizeFF(caseSelect.selectedOptions[0]?.dataset.formfactor || "");
      let ok = true;
      if (moboFF && caseFF) {
        if (moboFF.includes("mini") || moboFF.includes("itx")) {
          ok = true;
        } else if (moboFF.includes("micro")) {
          ok = !(caseFF.includes("mini") || caseFF.includes("itx"));
        } else if (moboFF.includes("atx") || moboFF.includes("tower")) {
          ok = !(caseFF.includes("mini") || caseFF.includes("micro") || caseFF.includes("itx"));
        } else {
          ok = caseFF === moboFF || caseFF.includes(moboFF);
        }
      }
      if (!ok) {
        showTooltip("caseMessage", `This case does not fit ${moboFF?.toUpperCase()} motherboards. Please select a compatible case.`);
        markInvalid(caseSelect);
      } else {
        clearInvalid(caseSelect);
        hideTooltip("caseMessage");
      }
    }

    function filterStorage(showTip=false){
      const moboNvme = (moboSelect.selectedOptions[0]?.dataset.nvme || "false").toLowerCase();
      const iface = normalizeIface(storageSelect.selectedOptions[0]?.dataset.interface);
      const needsNvme = iface && iface.startsWith("pcie");
      if (needsNvme && moboNvme !== "true") {
        showTooltip("storageMessage", `Motherboard does not support NVMe/PCIe. Choose SATA or change motherboard.`);
        markInvalid(storageSelect);
      } else {
        clearInvalid(storageSelect);
        hideTooltip("storageMessage");
      }
    }

    function filterPSUs(showTip=false){
      const cpuTDP = parseInt(cpuSelect.selectedOptions[0]?.dataset.tdp || "0",10);
      const gpuTDP = parseInt(gpuSelect.selectedOptions[0]?.dataset.tdp || "0",10);
      const required = Math.round((cpuTDP + gpuTDP) * 1.3);
      const selectedW = parseInt(psuSelect.selectedOptions[0]?.dataset.wattage || "0",10);
      if (selectedW && selectedW < required) {
        showTooltip("psuMessage", `PSU insufficient. Select ≥ ${required}W.`);
        markInvalid(psuSelect);
      } else {
        clearInvalid(psuSelect);
        hideTooltip("psuMessage");
      }
    }

    function filterCoolers(showTip=false){
      const cpuTDP = parseInt(cpuSelect.selectedOptions[0]?.dataset.tdp || "0",10);
      const th = parseInt(coolerSelect.selectedOptions[0]?.dataset.throughput || "0",10);
      if (th && th < cpuTDP) {
        showTooltip("coolerMessage", `Cooler insufficient for CPU TDP (${cpuTDP}W).`);
        markInvalid(coolerSelect);
      } else {
        clearInvalid(coolerSelect);
        hideTooltip("coolerMessage");
      }
    }

    function clearFilter(groupId, select){
      document.querySelectorAll(`#${groupId} button`).forEach(b=>{
        b.classList.remove("btn-primary"); b.classList.add("btn-outline-primary");
      });
      [...select.options].forEach(opt => { opt.hidden = false; });
      ensureSelection(select);
    }

    document.querySelectorAll("#cpuBrandFilters button[data-brand]").forEach(btn=>{
      btn.addEventListener("click", ()=>{
        const brand = btn.dataset.brand;
        [...cpuSelect.options].forEach(opt => { opt.hidden = (opt.dataset.brand !== brand); });
        activate("cpuBrandFilters", btn);
        ensureSelection(cpuSelect);
        filterMobosByCpu(true);
      });
    });
    cpuClear?.addEventListener("click", ()=> { clearFilter("cpuBrandFilters", cpuSelect); filterMobosByCpu(true); });

    document.querySelectorAll("#gpuBrandFilters button[data-brand]").forEach(btn=>{
      btn.addEventListener("click", ()=>{
        const brand = btn.dataset.brand;
        [...gpuSelect.options].forEach(opt => { opt.hidden = (opt.dataset.brand !== brand); });
        activate("gpuBrandFilters", btn);
        ensureSelection(gpuSelect);
        filterPSUs(true);
      });
    });
    gpuClear?.addEventListener("click", ()=> clearFilter("gpuBrandFilters", gpuSelect));

    document.querySelectorAll("#ramDDRFilters button[data-ddr]").forEach(btn=>{
      btn.addEventListener("click", ()=>{
        const ddr = btn.dataset.ddr;
        [...ramSelect.options].forEach(opt => { opt.hidden = normalizeDDR(opt.dataset.ddr) !== ddr; });
        activate("ramDDRFilters", btn);
        ensureSelection(ramSelect);
        filterMobosByRam(true);
        filterRamByMobo(true);
      });
    });
    ramClear?.addEventListener("click", ()=> clearFilter("ramDDRFilters", ramSelect));

    document.querySelectorAll("#storageFilters button[data-iface]").forEach(btn=>{
      btn.addEventListener("click", ()=>{
        const iface = btn.dataset.iface.toLowerCase();
        [...storageSelect.options].forEach(opt => {
          const norm = normalizeIface(opt.dataset.interface);
          opt.hidden = !norm.includes(iface);
        });
        activate("storageFilters", btn);
        ensureSelection(storageSelect);
        filterStorage(true);
      });
    });
    storageClear?.addEventListener("click", ()=> clearFilter("storageFilters", storageSelect));

    document.querySelectorAll("#psuFilters button[data-wattage]").forEach(btn=>{
      btn.addEventListener("click", ()=>{
        const minW = parseInt(btn.dataset.wattage,10);
        [...psuSelect.options].forEach(opt => {
          const w = parseInt(opt.dataset.wattage || "0",10);
          opt.hidden = w < minW;
        });
        activate("psuFilters", btn);
        ensureSelection(psuSelect);
        filterPSUs(true);
      });
    });
    psuClear?.addEventListener("click", ()=> clearFilter("psuFilters", psuSelect));

    document.querySelectorAll("#moboSocketFilters button[data-socket]").forEach(btn=>{
      btn.addEventListener("click", ()=>{
        const socket = btn.dataset.socket;
        [...moboSelect.options].forEach(opt => { opt.hidden = (opt.dataset.socket !== socket); });
        activate("moboSocketFilters", btn);
        ensureSelection(moboSelect);
        filterRamByMobo(true);
        filterCases(true);
        filterStorage(true);
        filterMobosByCpu(true);
      });
    });
    moboSocketClear?.addEventListener("click", ()=> { clearFilter("moboSocketFilters", moboSelect); filterMobosByCpu(true); });

    document.querySelectorAll("#caseFormFilters button[data-formfactor]").forEach(btn=>{
      btn.addEventListener("click", ()=>{
        const ff = normalizeFF(btn.dataset.formfactor || "");
        [...caseSelect.options].forEach(opt => {
          const caseFF = normalizeFF(opt.dataset.formfactor || "");
          if (!caseFF) { opt.hidden = true; return; }
          if (ff.includes("micro")) {
            opt.hidden = !caseFF.includes("micro");
          } else if (ff.includes("mini") || ff.includes("itx")) {
            opt.hidden = !(caseFF.includes("itx") || caseFF.includes("mini"));
          } else if (ff.includes("atx") || ff.includes("tower")) {
            opt.hidden = !((caseFF.includes("atx") || caseFF.includes("tower")) && !caseFF.includes("micro") && !caseFF.includes("mini"));
          } else {
            opt.hidden = !caseFF.includes(ff);
          }
        });
        activate("caseFormFilters", btn);
        ensureSelection(caseSelect);
        filterCases(true);
      });
    });
    caseFormClear?.addEventListener("click", ()=> clearFilter("caseFormFilters", caseSelect));

    document.querySelectorAll("#coolerFilters button[data-throughput]").forEach(btn=>{
      btn.addEventListener("click", ()=>{
        const minT = parseInt(btn.dataset.throughput,10);
        [...coolerSelect.options].forEach(opt => {
          const th = parseInt(opt.dataset.throughput || "0",10);
          opt.hidden = th < minT;
        });
        activate("coolerFilters", btn);
        ensureSelection(coolerSelect);
        filterCoolers(true);
      });
    });
    coolerClear?.addEventListener("click", ()=> clearFilter("coolerFilters", coolerSelect));

    // Initial pass: run filters but only show tooltips if current selection is invalid
    function runAllValidation(){
      filterMobosByCpu(true);
      filterMobosByRam(true);
      filterRamByMobo(true);
      filterCases(true);
      filterStorage(true);
      filterPSUs(true);
      filterCoolers(true);
    }

    // Expose to window so other handlers (e.g., toggles) can call it
    window.runAllValidation = runAllValidation;

    // Initial pass
    runAllValidation();

    // Change events to re-check compatibility and tooltips
    cpuSelect.addEventListener("change", ()=>{ filterMobosByCpu(true); filterPSUs(true); filterCoolers(true); });
    gpuSelect.addEventListener("change", ()=>{ filterPSUs(true); });
    ramSelect.addEventListener("change", ()=>{ filterMobosByRam(true); filterRamByMobo(true); });
    moboSelect.addEventListener("change", ()=>{ filterRamByMobo(true); filterCases(true); filterStorage(true); filterMobosByCpu(true); });

  });

})();
