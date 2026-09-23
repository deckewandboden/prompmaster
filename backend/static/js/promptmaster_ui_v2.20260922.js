/* PromptMaster V2 presentation shell.
 * Additive only: moves the existing Golden-Master/runtime DOM without
 * replacing product state, prompt composition, entitlements or event handlers.
 */
(() => {
  'use strict';

  const $ = (selector, root=document) => root.querySelector(selector);
  const $$ = (selector, root=document) => [...root.querySelectorAll(selector)];
  const free = Boolean($('#freeApps'));
  const edition = free ? 'free' : 'pro';

  const oldMain = $('main.max');
  const licenseSection = $('#licensePanel') || $('input[name="mslicense"]')?.closest('.panel');
  const appSection = free ? $('#freeApps')?.closest('.section') : $('#applicationSection');
  const taskSection = $('#taskSection');
  const contextSection = free ? $('#contextSection') : $('#inputSection');
  const audienceSection = $('#audienceSection');
  const focusSection = $('#focusSection');
  const outputSection = $('#outputSection');
  const promptSection = $('section.prompt');
  const actions = $('#resetBtn')?.closest('.actions');
  const footer = $('footer.legal-footer');
  const heroCard = $('.hero-card');

  const required = {
    oldMain, licenseSection, appSection, taskSection, contextSection,
    audienceSection, focusSection, outputSection, promptSection, actions, footer, heroCard
  };
  const missing = Object.entries(required).filter(([,node]) => !node).map(([name]) => name);
  if (missing.length) {
    console.error('PromptMaster V2 shell not activated; required DOM missing:', missing);
    return;
  }

  document.body.classList.add('pmv2', 'pmv2-' + edition);

  const ensureProCatalogSearch = () => {
    if (free) return null;
    const catalog = $('#catalog');
    const appBody = catalog?.closest('.section-body');
    if (!catalog || !appBody) return null;

    let tools = $('.pmv2-app-tools', appBody);
    if (!tools) {
      tools = document.createElement('div');
      tools.className = 'pmv2-app-tools';
      tools.innerHTML = '<input type="search" class="pmv2-app-search" id="pmv2AppSearch" placeholder="Copilot-Bereich suchen …" autocomplete="off"><span class="pmv2-app-count">34 Apps</span>';
      appBody.insertBefore(tools, catalog);
    }

    const search = $('#pmv2AppSearch', tools);
    if (search && search.dataset.pmv2Bound !== '1') {
      search.dataset.pmv2Bound = '1';
      search.addEventListener('input', () => {
        const query = search.value.trim().toLocaleLowerCase('de');
        Array.from(catalog.querySelectorAll('.catalog-block')).forEach(block => {
          let visible = 0;
          Array.from(block.querySelectorAll('.app-card')).forEach(card => {
            const match = !query || (card.textContent || '').toLocaleLowerCase('de').includes(query);
            card.classList.toggle('pmv2-search-hidden', !match);
            if (match) visible += 1;
          });
          block.classList.toggle('pmv2-search-hidden', visible === 0);
        });
      });
    }
    return search;
  };

  ensureProCatalogSearch();

  const utilityLinks = Array.from(document.querySelectorAll('.utility a')).map(a => ({
    href: a.getAttribute('href') || '',
    label: (a.textContent || '').trim()
  }));
  const workspaceLink = utilityLinks.find(item =>
    item.href.startsWith('/portal/') || item.href.startsWith('/ns-admin/')
  );
  const logoutLink = utilityLinks.find(item => item.href.includes('/auth/logout'));
  const topProCard = $('#topProCard');

  const header = document.createElement('header');
  header.className = 'pmv2-header';
  header.innerHTML = `
    <div class="pmv2-brand">
      <img src="/static/brand/promptmaster-logo-reference.png" alt="PromptMaster">
      <span class="pmv2-edition pmv2-edition-${edition}">${edition.toUpperCase()}</span>
    </div>
    <div class="pmv2-header-spacer"></div>
    <span class="pmv2-ms-label">Für Microsoft Copilot</span>
    <div class="pmv2-header-actions"></div>
  `;
  const headerActions = $('.pmv2-header-actions', header);

  if (free) {
    const cta = document.createElement('button');
    cta.type = 'button';
    cta.className = 'pmv2-header-cta';
    cta.textContent = 'PromptMaster Pro entdecken →';
    cta.addEventListener('click', () => {
      if (topProCard) topProCard.click();
      else $('#generalProModal')?.classList.add('open');
    });
    headerActions.append(cta);
  } else {
    if (workspaceLink) {
      const cta = document.createElement('a');
      cta.className = 'pmv2-header-cta';
      cta.href = workspaceLink.href;
      cta.textContent = workspaceLink.label + ' öffnen →';
      headerActions.append(cta);
    }
    if (logoutLink) {
      const logout = document.createElement('a');
      logout.className = 'pmv2-logout';
      logout.href = logoutLink.href;
      logout.textContent = 'Abmelden';
      headerActions.append(logout);
    }
  }

  const hero = document.createElement('section');
  hero.className = 'pmv2-hero';
  const headline = free
    ? 'Sag Copilot genauer, was du brauchst.'
    : 'Mehr aus Microsoft Copilot. Mit System.';
  const subline = free
    ? 'PromptMaster macht aus deinem Anliegen Schritt für Schritt einen klaren, direkt einsetzbaren Prompt – kostenlos im Browser.'
    : '34 Copilot-Bereiche, präzise Aufgabenführung und professionelle Ausgabeformate – für Prompts, die im Arbeitsalltag sofort weiterhelfen.';
  const flowNames = ['Copilot-Stufe','Anwendung','Aufgabe','Kontext','Zielgruppe','Schwerpunkt','Ausgabe'];
  hero.innerHTML = `
    <div class="pmv2-hero-inner">
      <div class="pmv2-hero-copy">
        <div class="pmv2-eyebrow">FÜR MICROSOFT COPILOT</div>
        <h1>${headline}</h1>
        <p>${subline}</p>
      </div>
      <div class="pmv2-flow-panel">
        <div class="pmv2-flow-row">
          ${flowNames.map((name,index) => `
            <button type="button" class="pmv2-flow-step" data-pmv2-step="${index+1}">
              <b>${index+1}</b><span>${name}</span>
            </button>`).join('')}
        </div>
        <div class="pmv2-progress-host"></div>
      </div>
    </div>
  `;
  $('.pmv2-progress-host', hero).append(heroCard);

  const workspace = document.createElement('main');
  workspace.className = 'pmv2-workspace';
  workspace.innerHTML = '<div class="pmv2-config-scroll" id="pmv2ConfigScroll"></div><aside class="pmv2-prompt-panel"></aside>';
  const left = $('#pmv2ConfigScroll', workspace);
  const right = $('.pmv2-prompt-panel', workspace);

  const sections = [licenseSection, appSection, taskSection, contextSection, audienceSection, focusSection, outputSection];
  sections.forEach((section,index) => {
    section.classList.add('pmv2-section', 'pmv2-step-' + (index+1));
    section.dataset.pmv2Step = String(index+1);
    left.append(section);
  });

  promptSection.classList.add('pmv2-prompt');
  const promptHeading = $('h2', promptSection);
  if (promptHeading) promptHeading.textContent = 'Dein fertiger Prompt';
  right.append(promptSection);
  right.append(actions);
  const existingRating = $('#pmRatingWrap');
  if (existingRating) right.append(existingRating);

  const review = document.createElement('section');
  review.className = 'section pmv2-section pmv2-review';
  review.id = 'pmv2Review';
  review.innerHTML = `
    <div class="section-head">
      <div class="step pmv2-check-icon">✓</div>
      <div><h2>Prompt-Check</h2><p>Die wichtigsten Einstellungen auf einen Blick.</p></div>
    </div>
    <div class="section-body">
      <div class="pmv2-review-grid">
        <div class="pmv2-review-card"><div class="pmv2-review-label">Anwendung <button type="button" data-pmv2-edit="2">Bearbeiten</button></div><div class="pmv2-review-value" data-pmv2-review="app">Noch nicht gewählt</div></div>
        <div class="pmv2-review-card"><div class="pmv2-review-label">Aufgabe <button type="button" data-pmv2-edit="3">Bearbeiten</button></div><div class="pmv2-review-value" data-pmv2-review="task">Noch nicht gewählt</div></div>
        <div class="pmv2-review-card"><div class="pmv2-review-label">Zielgruppe <button type="button" data-pmv2-edit="5">Bearbeiten</button></div><div class="pmv2-review-value" data-pmv2-review="audience">Noch nicht gewählt</div></div>
        <div class="pmv2-review-card"><div class="pmv2-review-label">Ausgabe <button type="button" data-pmv2-edit="7">Bearbeiten</button></div><div class="pmv2-review-value" data-pmv2-review="output">Noch nicht vollständig</div></div>
      </div>
      <div class="pmv2-review-note">Prüfe die Kerneinstellungen. Den vollständigen, tatsächlich erzeugten Prompt siehst du rechts und kannst ihn direkt kopieren.</div>
    </div>
  `;
  left.append(review);
  left.append(footer);

  const addNextButton = (section, text, target) => {
    const body = $('.section-body', section);
    if (!body || $('[data-pmv2-next]', body)) return;
    const wrap = document.createElement('div');
    wrap.className = 'pmv2-next-row';
    wrap.innerHTML = `<button type="button" class="pmv2-next" data-pmv2-next="${target}">${text}</button>`;
    body.append(wrap);
  };
  addNextButton(contextSection, 'Weiter zur Zielgruppe →', 5);
  addNextButton(focusSection, 'Weiter zur Ausgabe →', 7);
  addNextButton(outputSection, 'Zum Prompt-Check →', 'review');

  if (free) {
    const ensureFreeProToggle = () => {
      const proApps = $('#proApps');
      if (!proApps) return null;

      const sectionBody = proApps.closest('.section-body');
      if (!sectionBody) return null;

      let block = $('.pmv2-free-pro-block', sectionBody);
      if (!block) {
        const proHead = [...sectionBody.querySelectorAll(':scope > .catalog-head')]
          .find(node => /Pro/i.test(node.textContent || ''));

        block = document.createElement('div');
        block.className = 'pmv2-free-pro-block';
        sectionBody.insertBefore(block, proHead || proApps);
        if (proHead) block.append(proHead);
        block.append(proApps);
        block.hidden = true;
      } else if (!block.contains(proApps)) {
        block.append(proApps);
      }

      let toggle = $('.pmv2-pro-toggle', sectionBody);
      if (!toggle) {
        toggle = document.createElement('button');
        toggle.type = 'button';
        toggle.className = 'pmv2-pro-toggle';
        sectionBody.insertBefore(toggle, block);
      } else if (toggle.nextElementSibling !== block) {
        sectionBody.insertBefore(toggle, block);
      }

      const syncToggleLabel = () => {
        toggle.textContent = block.hidden
          ? '28 weitere Pro-Bereiche anzeigen ▾'
          : '28 weitere Pro-Bereiche ausblenden ▴';
        toggle.setAttribute('aria-expanded', String(!block.hidden));
      };
      syncToggleLabel();

      if (toggle.dataset.pmv2Bound !== '1') {
        toggle.dataset.pmv2Bound = '1';
        toggle.addEventListener('click', () => {
          block.hidden = !block.hidden;
          syncToggleLabel();
        });
      }
      return toggle;
    };

    ensureFreeProToggle();
    window.addEventListener('pm-free-catalog-ready', ensureFreeProToggle);

    const proModalTitle = $('#proModalTitle');
    const proModalSubtitle = $('#proModalSubtitle');
    if (proModalTitle && proModalSubtitle) {
      const modalObserver = new MutationObserver(() => {
        const title = proModalTitle.textContent.trim();
        if (title.startsWith('CopilotPromptMaster Pro für ')) {
          const app = title.replace('CopilotPromptMaster Pro für ','');
          proModalTitle.textContent = app + ' mit PromptMaster Pro nutzen';
          proModalSubtitle.textContent = 'Nutze den erweiterten Copilot-Katalog und passe Prompts noch genauer an deinen Arbeitsbereich an.';
        }
      });
      modalObserver.observe(proModalTitle,{childList:true,subtree:true,characterData:true});
    }
  } else {
    ensureProCatalogSearch();

    const note = $('.legal-footer-note span', footer);
    if (note) {
      note.textContent = 'Die Prompt-Konfiguration wird serverseitig verarbeitet, um den Prompt zu erzeugen. Eingaben und erzeugte Prompts werden dabei nicht als Promptinhalt gespeichert.';
    }
  }

  document.body.insertBefore(header, document.body.firstChild);
  header.insertAdjacentElement('afterend', hero);
  hero.insertAdjacentElement('afterend', workspace);

  ['.utility','.nav','.hero'].forEach(selector => {
    const node = $(selector);
    if (node && node !== hero) node.remove();
  });
  if (oldMain.isConnected) oldMain.remove();

  let scrollRequestId = 0;
  let resetScrollGuardUntil = 0;
  const scrollToTarget = target => {
    if (Date.now() < resetScrollGuardUntil) return;
    const node = typeof target === 'string' ? $(target) : target;
    if (!node) return;
    const requestId = ++scrollRequestId;

    if (matchMedia('(max-width: 1180px)').matches) {
      node.scrollIntoView({behavior:'smooth',block:'start'});
      return;
    }

    const align = behavior => {
      if (requestId !== scrollRequestId || !node.isConnected) return;
      const leftRect = left.getBoundingClientRect();
      const nodeRect = node.getBoundingClientRect();
      const offset = nodeRect.top - leftRect.top - 2;
      left.scrollTo({top:left.scrollTop + offset,behavior});
    };

    align('smooth');

    // Smooth scrolling is browser-dependent and can still be a few pixels
    // short when a preceding section changes height. Finish quickly and
    // deterministically so the active step sits at the top of the scroller.
    setTimeout(() => align('auto'), 260);
  };

  const stepSection = number => sections[number-1];
  Array.from(hero.querySelectorAll('.pmv2-flow-step')).forEach(button => {
    button.addEventListener('click', () => scrollToTarget(stepSection(Number(button.dataset.pmv2Step))));
  });
  Array.from(review.querySelectorAll('[data-pmv2-edit]')).forEach(button => {
    button.addEventListener('click', () => scrollToTarget(stepSection(Number(button.dataset.pmv2Edit))));
  });

  licenseSection.addEventListener('change', event => {
    if (event.target.matches('input[name="mslicense"]')) setTimeout(() => scrollToTarget(appSection), 90);
  });

  appSection.addEventListener('click', event => {
    const card = event.target.closest(free ? '.app' : '.app-card');
    if (!card) return;
    if (card.classList.contains('locked') || card.dataset.prolocked === '1' || card.dataset.locked === '1') return;
    setTimeout(() => {
      if (!taskSection.classList.contains('hidden')) scrollToTarget(taskSection);
    }, 130);
  });

  taskSection.addEventListener('click', event => {
    const task = event.target.closest('.task');
    if (!task || task.classList.contains('locked') || task.dataset.prolocked === '1') return;
    setTimeout(() => {
      if (!contextSection.classList.contains('hidden')) scrollToTarget(contextSection);
    }, 110);
  });

  audienceSection.addEventListener('change', event => {
    if (event.target.matches('input[name="audience"]')) {
      setTimeout(() => {
        if (!focusSection.classList.contains('hidden')) scrollToTarget(focusSection);
      }, 90);
    }
  });

  left.addEventListener('click', event => {
    const next = event.target.closest('[data-pmv2-next]');
    if (!next) return;
    const target = next.dataset.pmv2Next;
    if (target === '5' && !free) {
      const emptyRequired = $$('.input-card.required .task-input', contextSection)
        .find(input => !(input.value || '').trim());
      if (emptyRequired) {
        emptyRequired.focus();
        return;
      }
    }
    if (target === 'review') scrollToTarget(review);
    else scrollToTarget(stepSection(Number(target)));
  });

  const selectedAppName = () => {
    if (free) {
      const input = $('input[name="app"]:checked');
      return input?.closest('.app')?.querySelector('.app-name')?.textContent.trim() || 'Noch nicht gewählt';
    }
    return $('.app-card.selected .app-name')?.textContent.trim() || 'Noch nicht gewählt';
  };
  const selectedTaskName = () => $('.task.selected .task-title')?.textContent.trim() || 'Noch nicht gewählt';
  const selectedAudience = () => {
    const input = $('input[name="audience"]:checked');
    return input?.closest('.option')?.textContent.replace(/\s+/g,' ').trim() || 'Noch nicht gewählt';
  };
  const outputSummary = () => {
    const values = [$('#formatSelect'), $('#detailSelect'), $('#toneSelect')]
      .filter(Boolean)
      .map(select => select.selectedOptions?.[0]?.textContent.trim())
      .filter(value => value && !/^Bitte auswählen/i.test(value));
    return values.length ? values.join(' · ') : 'Noch nicht vollständig';
  };
  const updateReview = () => {
    $('[data-pmv2-review="app"]', review).textContent = selectedAppName();
    $('[data-pmv2-review="task"]', review).textContent = selectedTaskName();
    $('[data-pmv2-review="audience"]', review).textContent = selectedAudience();
    $('[data-pmv2-review="output"]', review).textContent = outputSummary();
  };
  left.addEventListener('change', () => setTimeout(updateReview,0));
  left.addEventListener('click', () => setTimeout(updateReview,80));
  new MutationObserver(updateReview).observe(left,{subtree:true,attributes:true,attributeFilter:['class','checked','disabled']});
  updateReview();

  const oldProgressText = $('#progressText');
  const oldProgressBar = $('#progressBar');
  const updateFlow = () => {
    const raw = parseInt((oldProgressText?.textContent || '0').replace(/\D/g,''),10) || 0;
    const thresholds = free ? [0,12,28,43,57,72,88] : [0,8,20,38,55,70,86];
    Array.from(hero.querySelectorAll('.pmv2-flow-step')).forEach((button,index) => {
      button.classList.toggle('active', raw >= thresholds[index]);
    });
    if (oldProgressBar) oldProgressBar.setAttribute('aria-label', raw + ' Prozent vollständig');
  };
  if (oldProgressText) new MutationObserver(updateFlow).observe(oldProgressText,{subtree:true,childList:true,characterData:true});
  if (oldProgressBar) new MutationObserver(updateFlow).observe(oldProgressBar,{attributes:true,attributeFilter:['style']});
  updateFlow();

  $('#resetBtn').addEventListener('click', () => {
    resetScrollGuardUntil = Date.now() + 800;
    scrollRequestId += 1;

    const resetToTop = () => {
      if (matchMedia('(max-width: 1180px)').matches) {
        window.scrollTo({top:0,behavior:'auto'});
      } else {
        left.scrollTo({top:0,behavior:'auto'});
        left.scrollTop = 0;
      }
    };

    resetToTop();
    setTimeout(resetToTop, 100);
    setTimeout(resetToTop, 400);
    setTimeout(() => {
      resetToTop();
      resetScrollGuardUntil = 0;
      updateReview();
    }, 800);
  });

  $('#switchRequiredBtn')?.addEventListener('click', () => setTimeout(() => scrollToTarget(licenseSection),80));
  $('#switchBusinessBtn')?.addEventListener('click', () => setTimeout(() => scrollToTarget(licenseSection),80));

  document.body.dataset.pmv2Ready = '1';
  window.dispatchEvent(new CustomEvent('pm-v2-ready',{detail:{edition}}));
})();