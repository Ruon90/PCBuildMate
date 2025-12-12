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
(function(){ function clearExitOnly(){ try{ const main = document.getElementById('pageMain'); if(!main) return; delete document.body.dataset.animating; main.classList.remove('page-exit'); document.body.classList.add('page-ready'); }catch(err){} }
  window.addEventListener('pageshow', clearExitOnly); window.addEventListener('popstate', clearExitOnly);
})();

// Component details fetcher
(function(){
  function titleCaseType(t){ return (t||'').replace(/_/g,' ').replace(/\b\w/g, s=>s.toUpperCase()); }
  function buildRow(label, value){ const tr = document.createElement('tr'); const th = document.createElement('th'); th.className = 'w-50'; th.textContent = label; const td = document.createElement('td'); td.textContent = value; tr.appendChild(th); tr.appendChild(td); return tr; }
  async function openDetails(type, id){ const modalEl = document.getElementById('componentDetailsModal'); const titleEl = document.getElementById('componentDetailsTitle'); const loadingEl = document.getElementById('componentDetailsLoading'); const wrapEl = document.getElementById('componentDetailsTableWrap'); const tbody = document.querySelector('#componentDetailsTable tbody'); if(!modalEl||!titleEl||!loadingEl||!wrapEl||!tbody) return; titleEl.textContent = titleCaseType(type) + ' details'; loadingEl.classList.remove('d-none'); wrapEl.classList.add('d-none'); tbody.innerHTML = ''; try{ const resp = await fetch(`/component-details/?type=${encodeURIComponent(type)}&id=${encodeURIComponent(id)}`); if(!resp.ok) throw new Error('Failed to load details'); const data = await resp.json(); titleEl.textContent = `${titleCaseType(data.type)} — ${data.title}`; data.rows.forEach(r=>{ tbody.appendChild(buildRow(r.label, r.value)); }); loadingEl.classList.add('d-none'); wrapEl.classList.remove('d-none'); }catch(err){ loadingEl.textContent = 'Unable to load details.'; } try{ const bs = window.bootstrap && window.bootstrap.Modal ? new window.bootstrap.Modal(modalEl) : null; if(bs) bs.show(); else { modalEl.classList.add('show'); modalEl.style.display='block'; } }catch{} }
  document.addEventListener('click', function(ev){ const a = ev.target.closest('.component-details'); if(!a) return; ev.preventDefault(); const type = a.getAttribute('data-type'); const id = a.getAttribute('data-id'); if(type && id){ openDetails(type, id); } });
})();

// YouTube reviews search
(function(){ function openYTModal(q){ const modalEl = document.getElementById('youtubeReviewsModal'); const titleEl = document.getElementById('youtubeReviewsTitle'); const loadingEl = document.getElementById('youtubeReviewsLoading'); const gridEl = document.getElementById('youtubeReviewsGrid'); if(!modalEl||!titleEl||!loadingEl||!gridEl) return; titleEl.textContent = `Reviews — ${q}`; loadingEl.classList.remove('d-none'); gridEl.classList.add('d-none'); gridEl.innerHTML = ''; fetch(`/youtube-reviews/?q=${encodeURIComponent(q + ' review')}`).then(r=>r.json()).then(data=>{ const vids = Array.isArray(data.videos) ? data.videos : []; vids.slice(0,6).forEach(v=>{ const col = document.createElement('div'); col.className = 'col-md-4'; col.innerHTML = `<div class="card h-100"><img class="card-img-top" src="${v.thumb || ''}" alt="thumbnail"><div class="card-body"><a href="${v.url}" target="_blank" rel="noopener" class="stretched-link">${v.title}</a></div></div>`; gridEl.appendChild(col); }); loadingEl.classList.add('d-none'); gridEl.classList.remove('d-none'); }).catch(()=>{ loadingEl.textContent = 'Unable to load videos.'; }); try{ const bs = window.bootstrap && window.bootstrap.Modal ? new window.bootstrap.Modal(modalEl) : null; if(bs) bs.show(); else { modalEl.classList.add('show'); modalEl.style.display='block'; } }catch{} }
  document.addEventListener('click', function(ev){ const btn = ev.target.closest('.component-youtube'); if(!btn) return; ev.preventDefault(); const q = btn.getAttribute('data-query'); if(q) openYTModal(q); });
})();

// AI chat widget behavior (accessibility: aria-expanded + focus management)
(function(){
  const chatHeader = document.getElementById("chat-header");
  const aiAgent = document.getElementById("ai-agent");
  const chatBody = document.getElementById("chat-body");
  const chatWindow = document.getElementById("chat-window");
  const chatInput = document.getElementById("chat-input");
  const chatClose = document.getElementById("chat-close");
  const chatSend = document.getElementById("chat-send");
    if (!chatHeader || !aiAgent) return;
  let hasOpened = false;
  let prevFocus = null;
  aiAgent.classList.add('collapsed');
  // start collapsed for screen readers
  chatHeader.setAttribute('aria-expanded', 'false');

  function openChat(){
    if(aiAgent.classList.contains('open')) return;
  try{ prevFocus = document.activeElement; }catch(err){ prevFocus = null; }
          // Clear any inline collapse styles (leftover from a programmatic close)
          // so the CSS-controlled open animation can run. Then add an explicit
          // 'animate' marker so the CSS animation only runs when the user
          // triggers openChat. This prevents animations playing on page load
          // or when the browser restores DOM from bfcache.
          try{ if(chatBody){ chatBody.style.transition = ''; chatBody.style.transform = ''; chatBody.style.opacity = ''; } }catch(e){}
      aiAgent.classList.add('animate');
    // Force reflow to ensure the animate class is applied before we open
    // (helps in some browsers so animation plays reliably when requested).
    void aiAgent.offsetWidth;
    aiAgent.classList.remove('collapsed');
    aiAgent.classList.add('open');
    chatHeader.setAttribute('aria-expanded','true');
    if(chatClose) chatClose.style.display = "block";
    if(!hasOpened){
      chatWindow.innerHTML += "<p class=\"msg\"><b>AI:</b> Welcome! 👋<br>Ask me anything about PC builds and compatibility.</p>";
      hasOpened = true;
    }
    setTimeout(function(){ try{ if(chatInput) chatInput.focus(); }catch(err){} }, 220);
    // Remove the temporary animate marker after the open animation finishes
    try{
      var onAnimEnd = function(evt){
        try{ aiAgent.removeEventListener('animationend', onAnimEnd); }catch(e){}
        try{ aiAgent.classList.remove('animate'); }catch(e){}
      };
      aiAgent.addEventListener('animationend', onAnimEnd);
    }catch(err){}
  }

  function closeChat(){
    if (!aiAgent.classList.contains('open')) return;
    if (chatClose) chatClose.style.display = 'none';
    chatHeader.setAttribute('aria-expanded', 'false');

    // JS-driven two-step close to ensure precise sequencing and avoid
    // content sliding: 1) slide header down while morphing avatar; 2)
    // scale the container horizontally toward the avatar using a
    // computed transform-origin so it collapses exactly onto the avatar.
    try {
      const avatar = chatHeader.querySelector('img.chat-icon');
      // Compute header target: slide header to the bottom of chatBody
      const bodyHeight = chatBody ? chatBody.getBoundingClientRect().height : 48;
      const headerHeight = chatHeader.getBoundingClientRect().height || 40;
      // target so header moves visually to bottom edge of chat body
      const headerTargetY = Math.max(8, Math.round(bodyHeight - headerHeight / 2));

      // Prepare transitions. Hide the chat body as header moves so the
      // header visually "closes" the window. Let the avatar stay inside
      // the header (do not translate it separately) but morph its
      // border-radius so it becomes circular while sliding with header.
      chatHeader.style.transition = 'transform .22s cubic-bezier(.22,.9,.28,1)';
      if (avatar) avatar.style.transition = 'border-radius .22s ease';
      if (chatBody) {
        chatBody.style.transition = 'transform .18s ease, opacity .18s ease';
        chatBody.style.transform = 'scaleY(0)';
        chatBody.style.opacity = '0';
        chatBody.style.pointerEvents = 'none';
      }

  // apply header transform; avatar will move with header (no separate translate)
  chatHeader.style.transform = `translateY(${headerTargetY}px)`;
  // move the entire panel down with the header so the dark chat box
  // follows the header as it slides (prepares for the horizontal collapse)
  aiAgent.style.transition = 'transform .22s cubic-bezier(.22,.9,.28,1)';
  aiAgent.style.transform = `translateY(${headerTargetY}px)`;
      if (avatar) {
        avatar.style.borderRadius = '50%';
      }

      // after header transition completes, collapse the container toward avatar
      const onHeaderEnd = function (evt) {
        try { chatHeader.removeEventListener('transitionend', onHeaderEnd); } catch (e) {}

        try {
          // compute avatar center relative to aiAgent for transform-origin
          const aiRect = aiAgent.getBoundingClientRect();
          const avRect = avatar ? avatar.getBoundingClientRect() : null;
          const avatarCenterX = avRect ? Math.round(avRect.left - aiRect.left + avRect.width / 2) : Math.round(aiRect.width / 2);

          aiAgent.style.transformOrigin = `${avatarCenterX}px center`;
          aiAgent.style.transition = 'transform .36s cubic-bezier(.22,.9,.28,1)';
          // shrink horizontally toward the avatar center while preserving
          // the current translateY so the panel continues to sit where the
          // header landed on the page.
          aiAgent.style.transform = `translateY(${headerTargetY}px) scaleX(.18)`;

          const onAgentEnd = function (aevt) {
            try { aiAgent.removeEventListener('transitionend', onAgentEnd); } catch (e) {}
            // finalize classes & cleanup inline styles
            try { aiAgent.classList.remove('open'); } catch (e) {}
            try { aiAgent.classList.add('collapsed'); } catch (e) {}
            try { aiAgent.classList.remove('animate'); } catch (e) {}
            try { if (avatar) { avatar.style.transition = ''; avatar.style.borderRadius = ''; } } catch (e) {}
            try { if (chatBody) { chatBody.style.transition = ''; chatBody.style.transform = ''; chatBody.style.opacity = ''; chatBody.style.pointerEvents = ''; } } catch (e) {}
            try { chatHeader.style.transition = ''; chatHeader.style.transform = ''; } catch (e) {}
            try { aiAgent.style.transition = ''; aiAgent.style.transform = ''; aiAgent.style.transformOrigin = ''; } catch (e) {}
            try { if (prevFocus && typeof prevFocus.focus === 'function') prevFocus.focus(); } catch (err) {}
          };

          aiAgent.addEventListener('transitionend', onAgentEnd);
        } catch (e) { }
      };

      chatHeader.addEventListener('transitionend', onHeaderEnd);
    } catch (e) {}
  }

  chatHeader.addEventListener('click', function(e){ if(e.target && e.target.id === 'chat-close') return; if(aiAgent.classList.contains('open')) closeChat(); else openChat(); });

  if(chatClose){ chatClose.addEventListener('click', function(e){ e.stopPropagation(); closeChat(); }); }

  function showThinking(){ const thinking = document.createElement("p"); thinking.id = "thinking"; thinking.innerHTML = "<i>AI is thinking...</i>"; chatWindow.appendChild(thinking); chatWindow.scrollTop = chatWindow.scrollHeight; }
  function hideThinking(){ const thinking = document.getElementById("thinking"); if (thinking) thinking.remove(); }
  function sendChat(){ if(!chatInput) return; const msg = chatInput.value.trim(); if(!msg) return; chatInput.value = ""; chatWindow.innerHTML += `<p class="msg"><b>You:</b> ${msg}</p>`; showThinking(); fetch("/ai-chat/", { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({message: msg}) }).then(res => res.json()).then(data => { hideThinking(); chatWindow.innerHTML += `<p class="msg"><b>AI:</b><br>${data.reply}</p>`; if(data.videos){ chatWindow.innerHTML += "<p class=\"msg\"><b>Videos:</b></p>"; data.videos.slice(0,4).forEach(v => { chatWindow.innerHTML += `<p class="msg"><a href="${v.url}" target="_blank">${v.title}</a></p>`; }); } chatWindow.scrollTop = chatWindow.scrollHeight; }).catch(err => { hideThinking(); chatWindow.innerHTML += `<p class="msg"><b>AI:</b> Sorry, something went wrong.</p>`; }); }

  if (chatInput && chatSend) {
    chatInput.addEventListener("keypress", function(e){ if(e.key === "Enter") sendChat(); });
    chatSend.addEventListener("click", sendChat);
  }
})();

// Ensure fixed header won't cover content: compute header height and set CSS var & body padding
(function(){
  try{
    var header = document.querySelector('header.sticky-top');
    if(!header) return;
    var setOffset = function(){
      var h = header.offsetHeight || 64;
      document.documentElement.style.setProperty('--navbar-height', h + 'px');
      var bodyPad = parseFloat(getComputedStyle(document.body).paddingTop) || 0;
      if(bodyPad < h) document.body.style.paddingTop = h + 'px';
    };
    setOffset();
    window.addEventListener('resize', setOffset);
    window.addEventListener('load', setOffset);
  }catch(err){ }
})();

// B4B-style bottleneck badges (moved here so it's loaded via base.html -> script.js)
(function(){
  window.PCBM = window.PCBM || {};
  window.PCBM.updateB4BBadges = function(root){
    root = root || document;
    try{
      var els = Array.from(root.querySelectorAll('.bottleneck-badge'));
      els.forEach(function(el){
        var pct = parseFloat(el.getAttribute('data-pct')) || 0;
        var rawType = (el.getAttribute('data-type') || 'unknown').toLowerCase();
        var type = 'UNKNOWN';
        if (/cpu/.test(rawType)) type = 'CPU';
        else if (/gpu/.test(rawType)) type = 'GPU';
        else type = (el.getAttribute('data-type') || 'unknown').toUpperCase();

        // clear previous indicator classes
        el.classList.remove('bottleneck-balanced','bottleneck-suggest');

        // Build content: keep inline text size consistent with surrounding card text
  var main = document.createElement('span'); main.className = 'bottleneck-main'; main.style.fontSize = 'inherit'; main.style.lineHeight = '1.2';
  // Add an explicit 'Bottleneck:' label inside the badge so the card
  // doesn't need a separate text node. The renderer will produce:
  // "Bottleneck: CPU 12%" inside the badge.
  var prefix = document.createElement('span'); prefix.className = 'bottleneck-label'; prefix.textContent = 'Bottleneck: ';
  var label = document.createElement('strong'); label.className = 'bottleneck-type'; label.textContent = type;
  var spacer = document.createTextNode(' ');
  var num = document.createElement('span'); num.className = 'bottleneck-pct'; num.textContent = pct.toFixed(1) + '%';
  main.appendChild(prefix);
  main.appendChild(label);
  main.appendChild(spacer);
  main.appendChild(num);

        var note = document.createElement('div'); note.className = 'bottleneck-note';

        // New threshold: if bottleneck over 12% suggest upgrade; make suggestion component-specific
        if (pct > 12){
          el.classList.add('bottleneck-suggest');
          // Use CPU/GPU specifically where possible, fallback to 'component'
          var comp = 'component';
          if (type === 'CPU') comp = 'CPU';
          else if (type === 'GPU') comp = 'GPU';
          else comp = type && type !== 'UNKNOWN' ? type : 'component';
          note.textContent = 'Consider a stronger ' + comp + ' for future upgrades.';
        } else {
          el.classList.add('bottleneck-balanced');
          note.textContent = 'Balanced';
        }

        // Replace content
        el.innerHTML = '';
        el.appendChild(main);
        el.appendChild(note);
      });
    }catch(err){}
  };
  document.addEventListener('DOMContentLoaded', function(){ try{ window.PCBM.updateB4BBadges(); }catch(err){} });
})();

// UI guard: prevent anonymous users from attempting to save builds client-side.
// Templates can opt-in by adding `data-user-authenticated="1"` on the <body>
// element when the request.user is authenticated. If that dataset is missing
// we conservatively assume the user is not authenticated and show a prompt
// when a `.save-build-btn` is clicked.
(function(){
  try{
    var body = document && document.body;
    var authed = body && body.dataset && body.dataset.userAuthenticated === '1';

    document.addEventListener('click', function(ev){
      var btn = ev.target.closest && ev.target.closest('.save-build-btn');
      if(!btn) return;
      // Allow actual form submits or links for authenticated users
      if(authed) return;

      ev.preventDefault();
      // Friendly prompt: link to the login page and preserve next
      var loginUrl = '/accounts/login/?next=' + encodeURIComponent(window.location.pathname + window.location.search);

      // Small transient banner in the top-center
      var prompt = document.createElement('div');
      prompt.setAttribute('role','alert');
      prompt.style.position = 'fixed';
      prompt.style.left = '50%';
      prompt.style.top = '14%';
      prompt.style.transform = 'translateX(-50%)';
      prompt.style.background = 'linear-gradient(180deg,#fff,#f7f9fc)';
      prompt.style.border = '1px solid rgba(0,0,0,0.08)';
      prompt.style.padding = '12px 16px';
      prompt.style.zIndex = 99999;
      prompt.style.borderRadius = '8px';
      prompt.style.boxShadow = '0 6px 24px rgba(12,20,40,0.12)';
      prompt.innerHTML = 'You must be signed in to save builds. <a href="' + loginUrl + '">Sign in</a>';
      document.body.appendChild(prompt);
      setTimeout(function(){ try{ prompt.remove(); }catch(e){} }, 5000);
    });
  }catch(e){}
})();