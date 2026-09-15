(() => {
  const initDataGrids = () => {
    document.querySelectorAll('form.toolbar[aria-label="Tabellenfilter"]').forEach((form) => {
      const search = form.querySelector('input[name="q"]');
      if (!search) return;

      let timer = null;
      const submitSearch = () => {
        timer = null;
        const value = search.value.trim();
        if (value.length === 1) return;
        form.requestSubmit();
      };

      search.addEventListener('input', (event) => {
        if (event.isComposing) return;
        if (timer) window.clearTimeout(timer);
        timer = window.setTimeout(submitSearch, 300);
      });

      search.addEventListener('keydown', (event) => {
        if (event.key === 'Enter' && timer) {
          window.clearTimeout(timer);
          timer = null;
        }
      });
    });
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initDataGrids, {once: true});
  } else {
    initDataGrids();
  }
})();
