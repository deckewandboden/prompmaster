/* PromptMaster V2 high-resolution brand asset override. */
(() => {
  'use strict';
  const apply = () => {
    const logo = document.querySelector('.pmv2-brand img');
    if (!logo) return false;
    logo.src = '/static/brand/promptmaster-logo-hq.png?v=20260925-hq1';
    logo.alt = 'PromptMaster';
    logo.decoding = 'async';
    logo.draggable = false;
    return true;
  };
  if (!apply()) {
    document.addEventListener('DOMContentLoaded', apply, {once:true});
  }
})();
