// Per-page JS for build preview: resolution toggles and small UX helpers
(function(){
  document.addEventListener('DOMContentLoaded', function () {
    try{
      const root = document.getElementById('bp-perf');
      if (!root) return;
      const buttons = Array.from(root.querySelectorAll('.bp-res-toggle'));
      const panes = Array.from(root.querySelectorAll('.bp-fps-pane'));
      buttons.forEach(btn => btn.addEventListener('click', function () {
        try{
          const r = this.getAttribute('data-res');
          buttons.forEach(b=>b.classList.remove('active'));
          this.classList.add('active');
          panes.forEach(p => {
            p.style.display = (p.getAttribute('data-res-pane') === r) ? 'block' : 'none';
          });
  }catch(err){/* defensive */}
      }));
  }catch(err){/* defensive */}
  });
})();
