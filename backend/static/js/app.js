(() => {
  const initDataGrids = () => {
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
        if (timer) {
          window.clearTimeout(timer);
          timer = null;
        }
        markLoading();
        form.requestSubmit();
      };

      if (search) {
        const submitSearch = () => {
          timer = null;
          const value = search.value.trim();
          if (value.length === 1) return;
          markLoading();
          form.requestSubmit();
        };

        search.addEventListener('input', (event) => {
          if (event.isComposing) return;
          if (timer) window.clearTimeout(timer);
          timer = window.setTimeout(submitSearch, 300);
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
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initDataGrids, {once: true});
  } else {
    initDataGrids();
  }
})();
