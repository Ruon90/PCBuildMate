// Inline resolution toggle for Saved Build Preview FPS section
document.addEventListener('click', function(e){
    const btn = e.target.closest('.res-toggle-card-btn');
    if(!btn) return;
    const res = btn.getAttribute('data-res');
    if(!res) return;
    // Toggle active state within the same button group
    const group = btn.closest('.btn-group');
    if(group){
        group.querySelectorAll('.res-toggle-card-btn').forEach(b=>b.classList.remove('active'));
        btn.classList.add('active');
    }
    // Show the matching fps-block and hide others inside the nearest card body
    const cardBody = btn.closest('.card-body');
    const blocks = cardBody ? cardBody.querySelectorAll('.fps-block') : document.querySelectorAll('.fps-block');
    // Use class-based toggles so CSS controls visibility and no inline styles conflict
    blocks.forEach(el => {
        el.classList.toggle('active', el.getAttribute('data-res') === res);
    });
});
