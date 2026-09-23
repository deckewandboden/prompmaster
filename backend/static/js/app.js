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


  const initCopyControls = () => {
    document.querySelectorAll('[data-copy-target]').forEach((button) => {
      if (button.dataset.copyBound === '1') return;
      button.dataset.copyBound = '1';
      button.addEventListener('click', async () => {
        const target = document.querySelector(button.dataset.copyTarget || '');
        if (!target) return;
        const value = (target.value || target.textContent || '').trim();
        if (!value) return;
        const original = button.textContent;
        try {
          await navigator.clipboard.writeText(value);
          button.textContent = 'Kopiert ✓';
        } catch {
          const range = document.createRange();
          range.selectNodeContents(target);
          const selection = window.getSelection();
          selection.removeAllRanges();
          selection.addRange(range);
          document.execCommand('copy');
          selection.removeAllRanges();
          button.textContent = 'Kopiert ✓';
        }
        window.setTimeout(() => { button.textContent = original; }, 1200);
      });
    });
  };

  const initConfirmationDialogs = () => {
    document.querySelectorAll('form[onsubmit]').forEach((form) => {
      const inline = form.getAttribute('onsubmit') || '';
      const match = inline.match(/confirm\((['"])(.*?)\1\)/);
      if (!match) return;
      form.dataset.confirm = match[2];
      form.removeAttribute('onsubmit');
    });

    const forms = [...document.querySelectorAll('form[data-confirm]')];
    if (!forms.length) return;

    const backdrop = document.createElement('div');
    backdrop.className = 'pm-confirm-backdrop';
    backdrop.hidden = true;
    backdrop.innerHTML = `
      <div class="pm-confirm-dialog" role="alertdialog" aria-modal="true" aria-labelledby="pmConfirmTitle" aria-describedby="pmConfirmText">
        <div class="pm-confirm-head">
          <div class="pm-confirm-kicker">Sicherheitsabfrage</div>
          <h2 id="pmConfirmTitle">Aktion bestätigen</h2>
        </div>
        <div class="pm-confirm-body" id="pmConfirmText"></div>
        <div class="pm-confirm-actions">
          <button type="button" class="btn secondary" data-confirm-cancel>Abbrechen</button>
          <button type="button" class="btn danger" data-confirm-ok>Bestätigen</button>
        </div>
      </div>
    `;
    document.body.append(backdrop);

    const textNode = backdrop.querySelector('#pmConfirmText');
    const cancel = backdrop.querySelector('[data-confirm-cancel]');
    const confirm = backdrop.querySelector('[data-confirm-ok]');
    let pendingForm = null;
    let pendingSubmitter = null;
    let previousFocus = null;

    const close = () => {
      backdrop.hidden = true;
      document.body.style.removeProperty('overflow');
      pendingForm = null;
      pendingSubmitter = null;
      if (previousFocus && previousFocus.isConnected) previousFocus.focus();
    };

    const open = (form, submitter) => {
      pendingForm = form;
      pendingSubmitter = submitter || null;
      previousFocus = document.activeElement;
      textNode.textContent = form.dataset.confirm || 'Möchten Sie diese Aktion wirklich ausführen?';
      const destructive = submitter?.classList.contains('danger');
      confirm.classList.toggle('danger', destructive);
      confirm.classList.toggle('primary', !destructive);
      confirm.textContent = destructive ? 'Verbindlich bestätigen' : 'Bestätigen';
      backdrop.hidden = false;
      document.body.style.overflow = 'hidden';
      cancel.focus();
    };

    forms.forEach((form) => {
      form.addEventListener('submit', (event) => {
        if (form.dataset.confirmApproved === '1') {
          delete form.dataset.confirmApproved;
          return;
        }
        event.preventDefault();
        open(form, event.submitter);
      });
    });

    cancel.addEventListener('click', close);
    confirm.addEventListener('click', () => {
      if (!pendingForm) return close();
      const form = pendingForm;
      const submitter = pendingSubmitter;
      backdrop.hidden = true;
      document.body.style.removeProperty('overflow');
      form.dataset.confirmApproved = '1';
      pendingForm = null;
      pendingSubmitter = null;
      if (submitter) form.requestSubmit(submitter);
      else form.requestSubmit();
    });
    backdrop.addEventListener('click', (event) => {
      if (event.target === backdrop) close();
    });
    document.addEventListener('keydown', (event) => {
      if (!backdrop.hidden && event.key === 'Escape') {
        event.preventDefault();
        close();
      }
    });
  };

  const initUi = () => {
    initDataGrids();
    initConfirmationDialogs();
    initCopyControls();
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initUi, {once: true});
  } else {
    initUi();
  }
})();
