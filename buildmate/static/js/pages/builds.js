document.addEventListener('DOMContentLoaded', function () {
  // Ensure each delete modal is attached directly to <body> to avoid stacking-context issues
  try {
    const modals = document.querySelectorAll('[id^="deleteModal"]');
    modals.forEach(m => {
      if (m.parentNode !== document.body) {
        document.body.appendChild(m);
      }
    });
  } catch (e) {
    // swallow errors; non-critical
  }
});
