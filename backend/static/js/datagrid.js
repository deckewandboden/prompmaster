document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('form[data-datagrid]').forEach((form) => {
    const search = form.querySelector('[data-grid-search]');
    const status = form.querySelector('[data-grid-status]');
    let timer = null;

    const markLoading = () => {
      form.setAttribute('aria-busy', 'true');
      if (status) {
        status.hidden = false;
        status.textContent = 'Daten werden geladen …';
      }
    };

    const submitNow = () => {
      if (timer) window.clearTimeout(timer);
      markLoading();
      form.requestSubmit();
    };

    if (search) {
      search.addEventListener('input', () => {
        if (timer) window.clearTimeout(timer);
        timer = window.setTimeout(submitNow, 300);
      });
      search.addEventListener('keydown', (event) => {
        if (event.key === 'Enter') {
          event.preventDefault();
          submitNow();
        }
      });
    }

    form.querySelectorAll('select[data-grid-auto-submit]').forEach((field) => {
      field.addEventListener('change', submitNow);
    });
    form.addEventListener('submit', markLoading);
  });
});
