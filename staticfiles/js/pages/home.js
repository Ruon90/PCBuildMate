// Per-page JS for calculator home (migrated from inline template)
(function(){
  const form = document.getElementById("buildForm");
  if (form) {
    form.addEventListener("submit", function(e) {
      e.preventDefault();
      const formData = new FormData(this);

      const modalEl = document.getElementById('buildProgressModal');
      const progressBar = document.getElementById('buildProgressBar');
      const progressMsg = document.getElementById('buildProgressMsg');
      try { if (modalEl && modalEl.parentNode !== document.body) { document.body.appendChild(modalEl); } } catch(e) {}
      let bsModal = null;
      if (typeof window.bootstrap !== 'undefined' && window.bootstrap.Modal) {
        try { bsModal = new window.bootstrap.Modal(modalEl, { backdrop: 'static', keyboard: false }); } catch (e) { bsModal = null; }
      }
      function manualShowModal() {
        try {
          const backdrop = document.createElement('div');
          backdrop.className = 'modal-backdrop fade show';
          backdrop.dataset.manual = '1';
          document.body.appendChild(backdrop);
          modalEl.classList.add('show');
          modalEl.style.display = 'block';
          modalEl.removeAttribute('aria-hidden');
          modalEl.setAttribute('aria-modal','true');
        } catch {}
      }
      function manualHideModal() {
        try {
          document.querySelectorAll('div.modal-backdrop[data-manual="1"]').forEach(el => el.remove());
          modalEl.classList.remove('show');
          modalEl.style.display = 'none';
          modalEl.setAttribute('aria-hidden','true');
          modalEl.removeAttribute('aria-modal');
        } catch {}
      }
      try { if (bsModal) bsModal.show(); else manualShowModal(); } catch(e) { manualShowModal(); }

      // Reset progress
      progressBar && progressBar.classList.remove('bg-danger');
      progressBar && progressBar.classList.add('bg-primary');
      progressBar && progressBar.classList.add('progress-bar-animated');
      let percent = 10;
      let anim = null;
      if (progressBar) {
        progressBar.style.width = percent + '%';
        progressBar.textContent = percent + '%';
      }
      progressMsg && (progressMsg.textContent = 'Crunching numbers and checking compatibility...');
      function startProgress(target) {
        if (anim) clearInterval(anim);
        anim = setInterval(() => {
          const step = 2;
          if (percent < target) {
            percent = Math.min(target, percent + step);
            if (progressBar) {
              progressBar.style.width = percent + '%';
              progressBar.textContent = percent + '%';
            }
          } else {
            clearInterval(anim);
            anim = null;
          }
        }, 140);
      }
      startProgress(80);

      // Use the form action (set in template) instead of embedding Django URL in the static file
      const targetUrl = (this && this.action) ? this.action : window.location.href;
      fetch(targetUrl, {
        method: "POST",
        body: formData
      })
      .then(res => res.json())
      .then(data => {
        const progressArea = document.getElementById("progressArea");
        if (progressArea) progressArea.innerHTML = "";

        let candidatesCount = (typeof data.candidates_count === 'number') ? data.candidates_count : null;
        if (data.progress) {
          let stepPercent = Math.floor(90 / data.progress.length);
          let currentPercent = 10;
          const ul = document.createElement("ul");

          data.progress.forEach(msg => {
            const lower = (msg || '').toLowerCase();
            const isSummary = lower.startsWith('selected best build') || lower.startsWith('picked best build');
            if (candidatesCount === null && typeof msg === 'string') {
              const m = msg.match(/out of\s+(\d+)\s+candidates/i);
              if (m && m[1]) candidatesCount = parseInt(m[1], 10);
            }
            if (!isSummary) {
              const li = document.createElement("li");
              li.textContent = msg;
              ul.appendChild(li);
            }

            currentPercent += stepPercent;
            percent = Math.min(95, currentPercent);
            if (progressBar) {
              progressBar.style.width = percent + "%";
              progressBar.textContent = percent + "%";
            }
          });
          progressArea && progressArea.appendChild(ul);
        }

        if (data.redirect) {
          // Show summary in modal then redirect
          if (progressArea) progressArea.innerHTML = "";
          let summaryText = (data.summary && typeof data.summary === 'string') ? data.summary : null;
          if (!summaryText && candidatesCount !== null) summaryText = `Picked best build of ${candidatesCount} candidates`;
          if (progressMsg) progressMsg.textContent = summaryText || "Picked best build";
          if (percent < 90) startProgress(90);
          setTimeout(() => {
            if (anim) { clearInterval(anim); anim = null; }
            percent = 100;
            if (progressBar) {
              progressBar.style.width = '100%';
              progressBar.textContent = '100%';
            }
            try { if (bsModal) bsModal.hide(); } catch(e) {} finally { manualHideModal(); }
            window.location.href = data.redirect;
          }, 800);
        } else if (data.error) {
          progressBar && progressBar.classList.remove("progress-bar-animated");
          progressBar && progressBar.classList.add("bg-danger");
          if (progressBar) progressBar.textContent = "Error";
          if (progressArea) progressArea.innerHTML = "<div class='alert alert-danger'>" + data.error + "</div>";
          setTimeout(() => { try { if (bsModal) bsModal.hide(); } catch(e) {} finally { manualHideModal(); } }, 1200);
        }
      })
      .catch(() => {
        // network or parse error
        if (progressBar) {
          progressBar.classList.remove('progress-bar-animated');
          progressBar.classList.add('bg-danger');
          progressBar.textContent = 'Error';
        }
      });
    });
  }

  // Filters toggle logic
  const filters = document.getElementById("advancedFilters");
  const toggleBtn = document.getElementById("toggleFilters");
  const cardEl = document.querySelector('.card');
  if (toggleBtn && filters) {
    toggleBtn.addEventListener("click", function() {
      try { new bootstrap.Collapse(filters, { toggle: true }); } catch(e) { }
    });

    filters.addEventListener && filters.addEventListener("show.bs.collapse", () => {
      toggleBtn.textContent = "Hide advanced filters";
      cardEl && cardEl.classList.add('expanding');
    });
    filters.addEventListener && filters.addEventListener("shown.bs.collapse", () => {
      try { toggleBtn.scrollIntoView({ behavior: 'smooth', block: 'nearest' }); } catch(e) {}
      cardEl && cardEl.classList.remove('expanding');
    });
    filters.addEventListener && filters.addEventListener("hide.bs.collapse", () => {
      toggleBtn.textContent = "Show advanced filters";
      cardEl && cardEl.classList.add('expanding');
    });
    filters.addEventListener && filters.addEventListener("hidden.bs.collapse", () => {
      cardEl && cardEl.classList.remove('expanding');
    });
  }

})();
