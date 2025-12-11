// Centralized site JS extracted from base.html
// Assumes bootstrap, jQuery and select2 are already loaded where required

// Smooth page-exit animation on internal navigation
(function(){
  function isInternalLink(a){
    try{ const url = new URL(a.href, window.location.origin); return url.origin === window.location.origin && !a.target && !a.hasAttribute('download'); }catch{ return false; }
  }
  document.addEventListener('click', function(ev){
    const a = ev.target.closest('a'); if(!a) return; if(!isInternalLink(a)) return;
    const href = a.getAttribute('href') || ''; if(href.startsWith('#')||href.startsWith('javascript:')) return;
    ev.preventDefault(); const main = document.getElementById('pageMain'); if(document.body.dataset.animating === '1') return;
    if(main){ document.body.dataset.animating = '1'; main.classList.add('page-exit'); const navigate = () => { window.location.href = a.href; };
      let handled = false; const onEnd = () => { if(!handled){ handled = true; navigate(); } };
      main.addEventListener('animationend', onEnd, { once: true }); setTimeout(onEnd, 1000);
    } else { window.location.href = a.href; }
  });
})();

// Back/forward: clear any exit class
(function(){ function clearExitOnly(){ try{ const main = document.getElementById('pageMain'); if(!main) return; delete document.body.dataset.animating; main.classList.remove('page-exit'); document.body.classList.add('page-ready'); }catch(e){} }
  window.addEventListener('pageshow', clearExitOnly); window.addEventListener('popstate', clearExitOnly);
})();

// Component details fetcher
(function(){
  function titleCaseType(t){ return (t||'').replace(/_/g,' ').replace(/\b\w/g, s=>s.toUpperCase()); }
  function buildRow(label, value){ const tr = document.createElement('tr'); const th = document.createElement('th'); th.className = 'w-50'; th.textContent = label; const td = document.createElement('td'); td.textContent = value; tr.appendChild(th); tr.appendChild(td); return tr; }
  async function openDetails(type, id){ const modalEl = document.getElementById('componentDetailsModal'); const titleEl = document.getElementById('componentDetailsTitle'); const loadingEl = document.getElementById('componentDetailsLoading'); const wrapEl = document.getElementById('componentDetailsTableWrap'); const tbody = document.querySelector('#componentDetailsTable tbody'); if(!modalEl||!titleEl||!loadingEl||!wrapEl||!tbody) return; titleEl.textContent = titleCaseType(type) + ' details'; loadingEl.classList.remove('d-none'); wrapEl.classList.add('d-none'); tbody.innerHTML = ''; try{ const resp = await fetch(`/component-details/?type=${encodeURIComponent(type)}&id=${encodeURIComponent(id)}`); if(!resp.ok) throw new Error('Failed to load details'); const data = await resp.json(); titleEl.textContent = `${titleCaseType(data.type)} — ${data.title}`; data.rows.forEach(r=>{ tbody.appendChild(buildRow(r.label, r.value)); }); loadingEl.classList.add('d-none'); wrapEl.classList.remove('d-none'); }catch(e){ loadingEl.textContent = 'Unable to load details.'; } try{ const bs = window.bootstrap && window.bootstrap.Modal ? new window.bootstrap.Modal(modalEl) : null; if(bs) bs.show(); else { modalEl.classList.add('show'); modalEl.style.display='block'; } }catch{} }
  document.addEventListener('click', function(ev){ const a = ev.target.closest('.component-details'); if(!a) return; ev.preventDefault(); const type = a.getAttribute('data-type'); const id = a.getAttribute('data-id'); if(type && id){ openDetails(type, id); } });
})();

// YouTube reviews search
(function(){ function openYTModal(q){ const modalEl = document.getElementById('youtubeReviewsModal'); const titleEl = document.getElementById('youtubeReviewsTitle'); const loadingEl = document.getElementById('youtubeReviewsLoading'); const gridEl = document.getElementById('youtubeReviewsGrid'); if(!modalEl||!titleEl||!loadingEl||!gridEl) return; titleEl.textContent = `Reviews — ${q}`; loadingEl.classList.remove('d-none'); gridEl.classList.add('d-none'); gridEl.innerHTML = ''; fetch(`/youtube-reviews/?q=${encodeURIComponent(q + ' review')}`).then(r=>r.json()).then(data=>{ const vids = Array.isArray(data.videos) ? data.videos : []; vids.slice(0,6).forEach(v=>{ const col = document.createElement('div'); col.className = 'col-md-4'; col.innerHTML = `<div class="card h-100"><img class="card-img-top" src="${v.thumb || ''}" alt="thumbnail"><div class="card-body"><a href="${v.url}" target="_blank" rel="noopener" class="stretched-link">${v.title}</a></div></div>`; gridEl.appendChild(col); }); loadingEl.classList.add('d-none'); gridEl.classList.remove('d-none'); }).catch(()=>{ loadingEl.textContent = 'Unable to load videos.'; }); try{ const bs = window.bootstrap && window.bootstrap.Modal ? new window.bootstrap.Modal(modalEl) : null; if(bs) bs.show(); else { modalEl.classList.add('show'); modalEl.style.display='block'; } }catch{} }
  document.addEventListener('click', function(ev){ const btn = ev.target.closest('.component-youtube'); if(!btn) return; ev.preventDefault(); const q = btn.getAttribute('data-query'); if(q) openYTModal(q); });
})();

// AI chat widget behavior (accessibility: aria-expanded + focus management)
