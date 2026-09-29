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


  const initSortableHeaders = () => {
    const current = new URL(window.location.href);
    const activeSort = current.searchParams.get('sort') || '';
    const activeDir = (current.searchParams.get('dir') || 'asc').toLowerCase() === 'desc' ? 'desc' : 'asc';
    const collator = new Intl.Collator('de', {numeric: true, sensitivity: 'base'});

    const setSortAccessibility = (control, state) => {
      const header = control.closest('th');
      if (header) {
        header.setAttribute(
          'aria-sort',
          state === 'asc' ? 'ascending' : state === 'desc' ? 'descending' : 'none'
        );
      }
      control.dataset.sortState = state;
      const label = (control.dataset.sortLabel || control.textContent || '').trim();
      control.setAttribute(
        'aria-label',
        state === 'asc'
          ? `${label}, aktuell aufsteigend sortiert. Sortierreihenfolge ändern`
          : state === 'desc'
            ? `${label}, aktuell absteigend sortiert. Sortierreihenfolge ändern`
            : `${label} sortieren`
      );
      control.title = state === 'asc'
        ? 'Aufsteigend sortiert – klicken für absteigend'
        : state === 'desc'
          ? 'Absteigend sortiert – klicken für aufsteigend'
          : 'Sortieren – klicken für aufsteigend';
    };

    // Server-side DataGrid sorting. These links keep pagination/filter/query
    // semantics and only receive one common visible UI state here.
    document.querySelectorAll('.tablewrap thead th a[href]').forEach((link) => {
      let target;
      try {
        target = new URL(link.href, window.location.href);
      } catch {
        return;
      }
      const sortKey = target.searchParams.get('sort');
      if (!sortKey) return;

      // Older templates rendered arrows only after sorting. Remove those
      // glyphs so the central, always-visible control is the single source.
      link.querySelectorAll('span').forEach((span) => {
        if (/^[↑↓]$/.test((span.textContent || '').trim())) span.remove();
      });
      Array.from(link.childNodes).forEach((node) => {
        if (node.nodeType === Node.TEXT_NODE) {
          node.nodeValue = (node.nodeValue || '').replace(/\s*[↑↓]\s*$/u, '');
        }
      });

      link.classList.add('sort-control');
      link.dataset.sortMode = 'server';
      link.dataset.sortLabel = (link.textContent || '').trim();
      setSortAccessibility(link, sortKey === activeSort ? activeDir : 'none');
    });

    const normaliseSortValue = (raw) => {
      const value = String(raw || '').replace(/\s+/g, ' ').trim();
      if (!value) return {type: 'text', value: ''};

      const dateMatch = value.match(/^(\d{1,2})\.(\d{1,2})\.(\d{4})(?:\s+(\d{1,2}):(\d{2}))?/);
      if (dateMatch) {
        const [, day, month, year, hour = '0', minute = '0'] = dateMatch;
        return {
          type: 'number',
          value: Date.UTC(Number(year), Number(month) - 1, Number(day), Number(hour), Number(minute)),
        };
      }

      const numericCandidate = value
        .replace(/\.(?=\d{3}(?:\D|$))/g, '')
        .replace(',', '.')
        .replace(/[^0-9+\-.]/g, '');
      if (numericCandidate && /^[+-]?\d+(?:\.\d+)?$/.test(numericCandidate)) {
        return {type: 'number', value: Number(numericCandidate)};
      }

      return {type: 'text', value};
    };

    const compareValues = (left, right) => {
      if (left.type === 'number' && right.type === 'number') return left.value - right.value;
      return collator.compare(String(left.value), String(right.value));
    };

    const excludedHeaders = /^(aktion|aktionen|erstattung)$/i;

    // Static/detail tables do not have DataGrid query links. Give them the same
    // visible sort affordance and sort the complete in-page tbody locally.
    document.querySelectorAll('.tablewrap table').forEach((table) => {
      if (table.querySelector('thead a[data-sort-mode="server"]')) return;
      const body = table.tBodies?.[0];
      if (!body) return;

      Array.from(table.querySelectorAll('thead th')).forEach((header, index) => {
        const label = (header.textContent || '').replace(/\s+/g, ' ').trim();
        if (!label || excludedHeaders.test(label) || header.querySelector('button,select,input')) return;

        const control = document.createElement('button');
        control.type = 'button';
        control.className = 'sort-control';
        control.dataset.sortMode = 'client';
        control.dataset.sortLabel = label;
        control.textContent = label;
        header.textContent = '';
        header.append(control);
        setSortAccessibility(control, 'none');

        control.addEventListener('click', () => {
          const nextState = control.dataset.sortState === 'asc' ? 'desc' : 'asc';
          table.querySelectorAll('thead .sort-control[data-sort-mode="client"]').forEach((other) => {
            if (other !== control) setSortAccessibility(other, 'none');
          });

          const rows = Array.from(body.rows);
          const sortable = rows
            .map((row, originalIndex) => ({row, originalIndex}))
            .filter(({row}) => row.cells.length > index && !row.querySelector('td[colspan]'));

          sortable.sort((a, b) => {
            const leftCell = a.row.cells[index];
            const rightCell = b.row.cells[index];
            const left = normaliseSortValue(leftCell?.dataset.sortValue || leftCell?.textContent);
            const right = normaliseSortValue(rightCell?.dataset.sortValue || rightCell?.textContent);
            const result = compareValues(left, right);
            return (nextState === 'asc' ? result : -result) || (a.originalIndex - b.originalIndex);
          });

          sortable.forEach(({row}) => body.append(row));
          rows.filter((row) => row.querySelector('td[colspan]')).forEach((row) => body.append(row));
          setSortAccessibility(control, nextState);
        });
      });
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
    initSortableHeaders();
    initConfirmationDialogs();
    initCopyControls();
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initUi, {once: true});
  } else {
    initUi();
  }
})();
