// Per-page JS migrated from calculator/templates/calculator/upgrade_calculator.html

// Fallback robust handler to ensure Find upgrades always works even if
// other handlers fail to attach (bfcache, jQuery not initialised, etc.)
(function(){
  try {
    if (window.jQuery) {
      var $ = window.jQuery;
      $(document).ready(function(){
        $('#findUpgradesBtn').off('click._pcbm').on('click._pcbm', function(ev){
          ev.preventDefault();
          var form = $(this).closest('form')[0];
          if (!form) return;
          try {
            if (typeof form.checkValidity === 'function' && !form.checkValidity()) {
              if (typeof form.reportValidity === 'function') form.reportValidity();
              $(form).addClass('was-validated');
              // show Select2 invalid visuals for searchable selects so users see feedback
              try { if (window.pcbmEnsureSelect2InvalidVisuals) window.pcbmEnsureSelect2InvalidVisuals(form); } catch(err){}
              var firstInvalid = form.querySelector(':invalid'); if (firstInvalid && firstInvalid.focus) firstInvalid.focus();
              return;
            }
          } catch(err) {}
          // show modal fallback
          try {
            var modalEl = document.getElementById('upgradeProgressModal');
            if (modalEl) {
              if (window.bootstrap && window.bootstrap.Modal) {
                try { new window.bootstrap.Modal(modalEl, { backdrop: 'static', keyboard: false }).show(); } catch(err) { modalEl.classList.add('show'); modalEl.style.display='block'; }
              } else { modalEl.classList.add('show'); modalEl.style.display='block'; }
            }
          } catch(err) {}
          // Submit the form with best-effort fallbacks
          try { if (typeof form.requestSubmit === 'function') { form.requestSubmit(); return; } } catch(err) {}
          try { form.dispatchEvent(new Event('submit', { cancelable: true })); return; } catch(err) {}
          try { form.submit(); } catch(err) {}
        });
      });
    }
  } catch(err) {}
})();


// Extra scripts: select2 init, return-from-preview handling, per-card toggles + delegated handlers
(function(){
  (function($){
    // Initialize Select2 as early as possible on DOM ready to ensure placeholders are set before any visual transitions
    $(document).ready(function(){
      try{ if($.fn.select2){ $('.searchable').filter(function(){ return !$(this).data('select2'); }).select2({ width: '100%', placeholder: 'Start typing to search', allowClear: true }); } }catch(err){}
        
        // Clear invalid visuals when users interact with inputs/selects after an invalid state
        try{
          $(document).on('change input', '.needs-validation :input', function(e){
            try{
              var el = e.target;
              // native invalid class
              if (el.classList && el.classList.contains('is-invalid')) el.classList.remove('is-invalid');
              // for Select2-enhanced selects, remove the is-invalid class from container and hide feedback
              if (el.tagName && el.tagName.toLowerCase() === 'select' && $(el).hasClass('searchable')){
                try{
                  var s2 = $(el).data('select2');
                  var container = s2 && s2.$container ? s2.$container[0] : null;
                  if (!container) {
                    if (el.nextElementSibling && el.nextElementSibling.classList && el.nextElementSibling.classList.contains('select2-container')) container = el.nextElementSibling;
                    else if (el.parentNode) container = el.parentNode.querySelector('.select2-container');
                  }
                  if (container && container.classList) container.classList.remove('is-invalid');
                  let fb = el.parentNode ? el.parentNode.querySelector('.invalid-feedback') : null;
                  if (fb && fb.classList) fb.classList.remove('d-block');
                }catch(err){}
              }
              // If the whole form is now valid, remove was-validated so bootstrap visuals reset
              var form = $(el).closest('form')[0];
              if (form && typeof form.checkValidity === 'function' && form.checkValidity()){
                $(form).removeClass('was-validated');
              }
            }catch(err){}
          });
        }catch(err){}
      // If returning from preview, fade-in the proposals section to match exit.
      (function(){
        function handleReturnFromPreview(){
          try {
            if (sessionStorage.getItem('returningFromPreview') === '1') {
              var el = document.getElementById('proposalsSection');
              if (el) {
                el.classList.add('content-enter');
                sessionStorage.removeItem('returningFromPreview');
                setTimeout(function(){ el.classList.remove('content-enter'); }, 240);
              }
            }
          } catch (err) {}
        }
        handleReturnFromPreview();
        window.addEventListener('pageshow', function(e){ handleReturnFromPreview(); });
      })();

      // Per-card resolution toggles: switch FPS blocks only inside the same card
      $(document).on('click', '.res-toggle-card-btn', function(){
        var res = $(this).data('res');
        var $card = $(this).closest('.card');
        $card.find('.res-toggle-card-btn').removeClass('active');
        $(this).addClass('active');
        $card.find('.fps-block').each(function(){
          var isTarget = $(this).data('res') === res;
          $(this).toggleClass('active', isTarget);
        });
      });
    });
  })(window.jQuery);

  // Intercept the upgrade form submit and show a modal with a progress bar.
  (function(){
    const modalEl = document.getElementById('upgradeProgressModal');
    const progressBar = document.getElementById('upgradeProgressBar');
    const progressMsg = document.getElementById('upgradeProgressMsg');
    try { if (modalEl && modalEl.parentNode !== document.body) { document.body.appendChild(modalEl); } } catch(err) {}
    if (!modalEl) return;

    // Helper: ensure Select2-enhanced selects show invalid visuals when native select is invalid.
    window.pcbmEnsureSelect2InvalidVisuals = function(form) {
      if (!form) return;
      try {
        var searchable = Array.from(form.querySelectorAll('select.searchable'));
        searchable.forEach(function(sel){
          try {
            var invalid = typeof sel.checkValidity === 'function' ? !sel.checkValidity() : false;
            var container = null;
            if (window.jQuery) {
              try {
                var $sel = window.jQuery(sel);
                var s2 = $sel.data && $sel.data('select2');
                if (s2 && s2.$container) container = s2.$container[0];
              } catch(err){}
            }
            if (!container) {
              if (sel.nextElementSibling && sel.nextElementSibling.classList && sel.nextElementSibling.classList.contains('select2-container')) container = sel.nextElementSibling;
              else if (sel.parentNode) container = sel.parentNode.querySelector('.select2-container');
            }
            if (invalid) {
              if (container && container.classList) container.classList.add('is-invalid');
              let fb = sel.parentNode ? sel.parentNode.querySelector('.invalid-feedback') : null;
              if (fb && fb.classList) fb.classList.add('d-block');
            } else {
              if (container && container.classList) container.classList.remove('is-invalid');
              let fb = sel.parentNode ? sel.parentNode.querySelector('.invalid-feedback') : null;
              if (fb && fb.classList) fb.classList.remove('d-block');
            }
          } catch(err){}
        });
        Array.from(form.querySelectorAll('select')).forEach(function(sel){
          if (!sel.classList.contains('searchable')) {
            try { if (typeof sel.checkValidity === 'function' && !sel.checkValidity()) sel.classList.add('is-invalid'); else sel.classList.remove('is-invalid'); } catch(err){}
          }
        });
      } catch(err){}
    };

    function patchInnerHTML(target, newHTML) {
      if (!target) return;
      const temp = document.createElement('div');
      temp.innerHTML = (newHTML || '').trim();
      const newChildren = Array.from(temp.childNodes);
      const oldChildren = Array.from(target.childNodes);
      for (let i = oldChildren.length - 1; i >= 0; i--) {
        const oldNode = oldChildren[i];
        const newNode = newChildren[i];
        if (!newNode) { target.removeChild(oldNode); continue; }
        if (oldNode.outerHTML !== newNode.outerHTML) { target.removeChild(oldNode); }
      }
      newChildren.forEach((newNode, i) => {
        const oldNode = target.childNodes[i];
        if (!oldNode) { target.appendChild(newNode.cloneNode(true)); return; }
        if (oldNode.outerHTML !== newNode.outerHTML) { target.replaceChild(newNode.cloneNode(true), oldNode); }
      });
    }

    let bsModal = null;
    if (typeof window.bootstrap !== 'undefined' && window.bootstrap.Modal) {
      try { bsModal = new window.bootstrap.Modal(modalEl, { backdrop: 'static', keyboard: false }); } catch (err) { bsModal = null; }
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
        modalEl.setAttribute('aria-modal', 'true');
        try { document.body.classList.add('modal-open'); } catch(err){}
      } catch (err) {}
    }

    function manualHideModal() {
      try {
        document.querySelectorAll('div.modal-backdrop').forEach(el => el.remove());
        if (modalEl) {
          modalEl.classList.remove('show');
          modalEl.style.display = 'none';
          modalEl.setAttribute('aria-hidden', 'true');
          modalEl.removeAttribute('aria-modal');
        }
        try { document.body.classList.remove('modal-open'); } catch(err){}
      } catch (err) {}
    }

    // delegated click handler for the Find upgrades button
    document.addEventListener('click', function(ev){
      const btn = ev.target.closest && ev.target.closest('#findUpgradesBtn');
      if (!btn) return;
      ev.preventDefault();
      const form = btn.closest('form');
      if (form && typeof form.checkValidity === 'function') {
        const valid = form.checkValidity();
        if (!valid) {
          if (typeof form.reportValidity === 'function') form.reportValidity();
          form.classList.add('was-validated');
          try { if (window.pcbmEnsureSelect2InvalidVisuals) window.pcbmEnsureSelect2InvalidVisuals(form); } catch(err){}
          const firstInvalid = form.querySelector(':invalid');
          if (firstInvalid && typeof firstInvalid.focus === 'function') firstInvalid.focus();
          return;
        }
      }
      try { if (bsModal) bsModal.show(); else manualShowModal(); } catch(err) { manualShowModal(); }
      progressBar.classList.remove('bg-danger');
      progressBar.classList.add('bg-primary');
      progressBar.classList.add('progress-bar-animated');
      progressBar.style.width = '5%';
      progressBar.textContent = '5%';
      progressMsg.textContent = 'Please wait while we evaluate upgrade options...';
      if (form && typeof form.requestSubmit === 'function') { form.requestSubmit(); } else if (form) { form.dispatchEvent(new Event('submit', { cancelable: true })); }
    });

    // delegated submit handler
    document.addEventListener('submit', function(e){
      const form = e.target;
      if (!form || !form.querySelector) return;
      if (!form.querySelector('#findUpgradesBtn')) return;
      if (typeof form.checkValidity === 'function' && !form.checkValidity()) {
        e.preventDefault();
        if (typeof form.reportValidity === 'function') form.reportValidity();
        form.classList.add('was-validated');
        try { if (window.pcbmEnsureSelect2InvalidVisuals) window.pcbmEnsureSelect2InvalidVisuals(form); } catch(err){}
        const firstInvalid = form.querySelector(':invalid');
        if (firstInvalid && typeof firstInvalid.focus === 'function') firstInvalid.focus();
        return;
      }
      e.preventDefault();
      try { if (bsModal) bsModal.show(); else manualShowModal(); } catch (err) { manualShowModal(); }
      let percent = 10; let anim = null;
      progressBar.style.width = percent + '%'; progressBar.textContent = percent + '%';
      function startProgress(target) { if (anim) clearInterval(anim); anim = setInterval(() => { const step = 2; if (percent < target) { percent = Math.min(target, percent + step); progressBar.style.width = percent + '%'; progressBar.textContent = percent + '%'; } else { clearInterval(anim); anim = null; } }, 140); }
      startProgress(80);
      const data = new FormData(form);
      fetch(window.location.href, { method: 'POST', body: data }).then(r => r.text()).then(text => {
        if (anim) { clearInterval(anim); anim = null; }
        try {
          const parser = new DOMParser(); const doc = parser.parseFromString(text, 'text/html');
          const proposalElems = doc.querySelectorAll('.col-md-6.mb-3'); const count = proposalElems ? proposalElems.length : 0;
          if (percent < 90) { startProgress(90); setTimeout(()=>{ if (anim){ clearInterval(anim); anim = null; } percent = 100; progressBar.style.width = '100%'; progressBar.textContent = '100%'; }, 700); } else { percent = 100; progressBar.style.width = '100%'; progressBar.textContent = '100%'; }
          if (count === 0) {
            progressBar.classList.remove('progress-bar-animated'); progressBar.classList.remove('bg-primary'); progressBar.classList.add('bg-danger'); progressMsg.textContent = 'No upgrades found for the selected budget and build.';
            setTimeout(()=>{
              const newRoot = doc.getElementById('upgradeCalculatorRoot') || doc.querySelector('div.card');
              const curRoot = document.getElementById('upgradeCalculatorRoot') || document.querySelector('div.card');
              if (newRoot && curRoot) {
                patchInnerHTML(curRoot, newRoot.innerHTML);
                try { if (window.PCBM && typeof window.PCBM.updateB4BBadges === 'function') window.PCBM.updateB4BBadges(document.getElementById('upgradeCalculatorRoot') || document); } catch(err){}
                try { if (window.jQuery && window.jQuery.fn && window.jQuery.fn.selectpicker){ var $ = window.jQuery; $('.selectpicker').each(function(){ var $el = $(this); if (!$el.data('selectpicker')) { $el.selectpicker(); } else { $el.selectpicker('refresh'); } }); $('.selectpicker').each(function(){ var $el = $(this); var hasRendered = !!$el.parent().find('.bootstrap-select').length; if(!hasRendered){ $el.removeClass('bs-select-hidden').css({display:'block'}); } }); } } catch(err){}
                try { document.querySelectorAll('.res-toggle-card-btn').forEach(btn => { btn.removeEventListener('click', window._resToggleHandler || function(){}); }); window._resToggleHandler = function(ev){ var b = ev.currentTarget; var res = b.getAttribute('data-res'); var card = b.closest('.card'); if (!card) return; card.querySelectorAll('.res-toggle-card-btn').forEach(x => x.classList.remove('active')); b.classList.add('active'); card.querySelectorAll('.fps-block').forEach(function(el){ el.classList.toggle('active', el.getAttribute('data-res') === res); }); }; document.querySelectorAll('.res-toggle-card-btn').forEach(btn => btn.addEventListener('click', window._resToggleHandler)); } catch(err){}
                try { const alertEl = document.getElementById('noUpgradesAlert'); if (alertEl){ alertEl.classList.remove('d-none'); alertEl.removeAttribute('aria-hidden'); } }catch(err){}
              } else { window.location.reload(); }
              try{ if (bsModal) bsModal.hide(); } catch(err){} finally { manualHideModal(); }
            }, 1200);
          } else {
            progressMsg.textContent = `Found ${count} upgrade path${count === 1 ? '' : 's'}`;
            setTimeout(()=>{
              try{
                const newDocProposals = doc.getElementById('proposalsSection'); const curProposals = document.getElementById('proposalsSection'); const newDocCurrent = doc.getElementById('currentBuildSummary'); const curCurrent = document.getElementById('currentBuildSummary');
                if (newDocProposals && curProposals){ patchInnerHTML(curProposals, newDocProposals.innerHTML); if (newDocCurrent && curCurrent) patchInnerHTML(curCurrent, newDocCurrent.innerHTML); try { if (window.PCBM && typeof window.PCBM.updateB4BBadges === 'function') window.PCBM.updateB4BBadges(document.getElementById('proposalsSection') || document); } catch(err){} const alertEl = document.getElementById('noUpgradesAlert'); if (alertEl){ alertEl.classList.add('d-none'); alertEl.setAttribute('aria-hidden','true'); }
                  try{ if (window.jQuery && window.jQuery.fn && window.jQuery.fn.selectpicker){ var $ = window.jQuery; $('.selectpicker').each(function(){ var $el = $(this); if (!$el.data('selectpicker')) { $el.selectpicker(); } else { $el.selectpicker('refresh'); } }); $('.selectpicker').each(function(){ var $el = $(this); var hasRendered = !!$el.parent().find('.bootstrap-select').length; if(!hasRendered){ $el.removeClass('bs-select-hidden').css({display:'block'}); } }); } }catch(err){}
                  try{ if (!window._resToggleHandler){ window._resToggleHandler = function(ev){ var b = ev.currentTarget; var res = b.getAttribute('data-res'); var card = b.closest('.card'); if (!card) return; card.querySelectorAll('.res-toggle-card-btn').forEach(x => x.classList.remove('active')); b.classList.add('active'); card.querySelectorAll('.fps-block').forEach(function(el){ el.classList.toggle('active', el.getAttribute('data-res') === res); }); }; } document.querySelectorAll('.res-toggle-card-btn').forEach(btn => btn.addEventListener('click', window._resToggleHandler)); }catch(err){}
                } else { const newRoot = doc.getElementById('upgradeCalculatorRoot') || doc.querySelector('div.card'); const curRoot = document.getElementById('upgradeCalculatorRoot') || document.querySelector('div.card'); if (newRoot && curRoot){ patchInnerHTML(curRoot, newRoot.innerHTML); } else { window.location.reload(); } }
              } finally { try{ if (bsModal) bsModal.hide(); } catch(err){} finally { manualHideModal(); } }
            }, 700);
          }
        } catch(err){ try{ if (bsModal) bsModal.hide(); } catch(err){} finally { manualHideModal(); } window.location.reload(); }
      }).catch(err => { clearInterval(anim); progressBar.classList.remove('progress-bar-animated'); progressBar.classList.add('bg-danger'); progressBar.style.width = '100%'; progressMsg.textContent = 'Error finding upgrades'; setTimeout(()=>{ try{ if (bsModal) bsModal.hide(); } catch(err){} finally { manualHideModal(); } }, 1200); });
    });
  })();

})();
