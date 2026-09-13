/* PromptMaster Commercial integration bridge.
 * Keeps the recovered marketing snapshot visually intact while synchronizing
 * product metadata with the live Django catalog when deployed behind Caddy.
 */
(() => {
  const replaceText = (root, from, to) => {
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    const nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);
    for (const node of nodes) {
      if (node.nodeValue && node.nodeValue.includes(from)) {
        node.nodeValue = node.nodeValue.replaceAll(from, to);
      }
    }
  };

  const applyCatalog = (catalog) => {
    const names = Array.isArray(catalog.proApplicationNames) ? catalog.proApplicationNames.filter(Boolean) : [];
    const total = Number(catalog.proApplicationCount || names.length || 0);
    if (!total) return;
    const freeNames = ['Copilot Chat', 'Outlook', 'Teams', 'Word', 'Excel', 'PowerPoint'];
    const additional = Math.max(0, total - freeNames.length);
    replaceText(document.body, '10 weitere Anwendungen', `${additional} weitere Anwendungen`);
    replaceText(document.body, '10 zusätzliche Microsoft-Anwendungen', `${additional} zusätzliche Microsoft-Anwendungen`);
    replaceText(document.body, '10 zusätzliche Pro-Apps', `${additional} zusätzliche Pro-Apps`);

    if (names.length) {
      const additionalNames = names.filter(name => !freeNames.includes(name));
      document.querySelectorAll('.mini-label').forEach(label => {
        if (label.textContent.trim() !== 'MIT PRO ZUSÄTZLICH') return;
        const apps = label.nextElementSibling;
        if (!apps || !apps.classList.contains('apps')) return;
        apps.replaceChildren(...additionalNames.map(name => {
          const span = document.createElement('span');
          span.className = 'app-pill';
          span.textContent = name;
          return span;
        }));
      });
    }

    document.querySelectorAll('.footer-bottom span').forEach(span => {
      if (span.textContent.includes('Vorschau · Kauf und Anmeldung noch nicht freigeschaltet')) {
        span.textContent = 'Kauf und Anmeldung über die PromptMaster Commercial Platform';
      }
    });
  };

  const sync = async () => {
    try {
      const response = await fetch('/catalog.json', {cache: 'no-cache'});
      if (!response.ok) return;
      applyCatalog(await response.json());
    } catch (_) {
      // Marketing remains usable with its committed static fallback catalog.
    }
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => setTimeout(sync, 0), {once: true});
  } else {
    setTimeout(sync, 0);
  }
})();
