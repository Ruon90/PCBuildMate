(function(){
  document.addEventListener('DOMContentLoaded', function(){
    // Provide the same small behaviors that were previously inline in the template.
    // Prefer namespaced init in window.PCBM where available; fallback to minimal handlers.

    // goBackWithExit (used by preview "Back" button)
    window.goBackWithExit = function(){
      try{
        var el = document.getElementById('previewContent');
        if(el) el.classList.add('content-exit');
        try { sessionStorage.setItem('returningFromPreview', '1'); } catch(e){}
        setTimeout(function(){ history.back(); }, 310);
      }catch(e){ history.back(); }
    };

    // Resolution toggles (gaming mode). If a global init exists prefer it.
    if (!(window.PCBM && typeof window.PCBM.initUpgradePreview === 'function')){
      try{
        document.querySelectorAll('.res-toggle').forEach(btn => btn.addEventListener('click', function (){
          try{
            const r = this.getAttribute('data-res');
            document.querySelectorAll('.res-toggle').forEach(b=>b.classList.remove('active'));
            this.classList.add('active');
            document.querySelectorAll('.fps-compare-pane').forEach(p=>{
              p.style.display = (p.getAttribute('data-res-pane') === r) ? 'block' : 'none';
            });
          }catch(e){}
        }));
      }catch(e){}

      // Equalize card heights within preview rows (fallback for CSS flex inconsistencies)
      (function(){
        function equalizePreviewRows(){
          document.querySelectorAll('#previewContent .row.equalize').forEach(function(row){
            const cols = Array.from(row.querySelectorAll(':scope > [class*=\"col-\"]'));
            if(cols.length === 0) return;
            // reset explicit heights
            cols.forEach(c=>{ const card = c.querySelector('.card'); if(card){ card.style.height = ''; } });
            // compute max height of .card in this row
            let max = 0;
            cols.forEach(c=>{ const card = c.querySelector('.card'); if(card){ const h = card.getBoundingClientRect().height; if(h > max) max = h; } });
            if(max > 0){ cols.forEach(c=>{ const card = c.querySelector('.card'); if(card) card.style.height = max + 'px'; }); }
          });
        }
        // run on load and resize, debounce resize
        window.addEventListener('load', equalizePreviewRows);
        var __eqT;
        window.addEventListener('resize', function(){ clearTimeout(__eqT); __eqT = setTimeout(equalizePreviewRows, 120); });
        // also run after fonts load (if supported)
        if(document.fonts && document.fonts.ready) document.fonts.ready.then(equalizePreviewRows).catch(()=>{});
      })();
    }

    // If the global initializer exists, call it (ensures single source of truth)
    try{ if (window.PCBM && typeof window.PCBM.initUpgradePreview === 'function') window.PCBM.initUpgradePreview(); }catch(e){}

  });
})();
