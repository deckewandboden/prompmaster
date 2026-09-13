import {renderContent,footer,calculator} from './content.js';
import {quote,normalizeQuantity,money} from './pricing.js';
const toggle=document.querySelector('.menu-toggle');
toggle.addEventListener('click',()=>{const open=toggle.getAttribute('aria-expanded')!=='true';toggle.setAttribute('aria-expanded',String(open));document.querySelector('nav').classList.toggle('open',open)});
document.querySelectorAll('nav a').forEach(a=>a.addEventListener('click',()=>{toggle.setAttribute('aria-expanded','false');document.querySelector('nav').classList.remove('open')}));
const motionReduced=matchMedia('(prefers-reduced-motion:reduce)');
let scrollQueued=false;
const syncScene=()=>{
  scrollQueued=false;
  const progress=Math.min(1,scrollY/Math.max(innerHeight*.9,1));
  document.documentElement.style.setProperty('--scene-scroll',String(progress));
};
addEventListener('scroll',()=>{if(!scrollQueued){scrollQueued=true;requestAnimationFrame(syncScene)}},{passive:true});
syncScene();
if(!motionReduced.matches){
  const revealObserver=new IntersectionObserver(entries=>entries.forEach(entry=>{if(entry.isIntersecting){entry.target.classList.add('in-view');revealObserver.unobserve(entry.target)}}),{rootMargin:'0px 0px -8% 0px',threshold:.08});
  document.querySelectorAll('.section').forEach(section=>revealObserver.observe(section));
}
async function initializePricing(){
  const input=document.getElementById('quantity');
  try {
    const response=await fetch('/catalog.json',{cache:'no-cache'});
    if(!response.ok) throw new Error('Produktkatalog nicht verfügbar');
    const catalog=await response.json();
    const initial=quote(catalog,new URLSearchParams(location.search).get('quantity')||1);
    if(home){
      document.querySelector('.pro .price').innerHTML=money(initial.monthlyGross)+'<span>/ Monat</span>';
      document.querySelector('.pro .price-detail').textContent='pro Benutzer · inkl. MwSt. · jährliche Abrechnung: '+money(initial.annualUnitGross);
    }
    if(path==='/free'&&catalog.freeUrl){
      const url=new URL(catalog.freeUrl,location.origin);
      if(url.origin===location.origin&&!['/free','/free/'].includes(url.pathname)) location.replace(url.href);
    }
    if(!input)return;
    input.max=String(catalog.maxQuantity);
    input.value=String(initial.quantity);
    const buy=document.getElementById('buy-licenses');
    function update(){
      const q=quote(catalog,input.value);
      input.value=String(q.quantity);
      for(const [key,value] of Object.entries({monthly:q.monthlyGross,annual:q.annualUnitGross,gross:q.gross})){
        document.querySelector('[data-price="'+key+'"]').textContent=money(value);
      }
      document.getElementById('minus').disabled=q.quantity<=1;
      document.getElementById('plus').disabled=q.quantity>=catalog.maxQuantity;
      if(path==='/checkout'){
        buy.textContent='Kauf noch nicht freigeschaltet';
        buy.removeAttribute('href');buy.setAttribute('aria-disabled','true');
        history.replaceState(null,'','/checkout/?quantity='+q.quantity);
      }else{
        buy.textContent=q.quantity+' PromptMaster-Pro-'+(q.quantity===1?'Lizenz':'Lizenzen')+' kaufen ↗';
        buy.href='/checkout/?quantity='+q.quantity;
      }
    }
    input.addEventListener('change',update);
    input.addEventListener('input',()=>{if(input.value!==''&&Number.isInteger(Number(input.value))&&Number(input.value)>=1)update()});
    document.getElementById('minus').addEventListener('click',()=>{input.value=String(normalizeQuantity(input.value,catalog.maxQuantity)-1);update()});
    document.getElementById('plus').addEventListener('click',()=>{input.value=String(normalizeQuantity(input.value,catalog.maxQuantity)+1);update()});
    update();
  }catch(error){
    if(input){input.disabled=true;document.getElementById('minus').disabled=true;document.getElementById('plus').disabled=true;document.getElementById('catalog-error').hidden=false;const buy=document.getElementById('buy-licenses');buy.removeAttribute('href');buy.setAttribute('aria-disabled','true');buy.textContent='Preis nicht verfügbar';}
    console.error('Preise konnten nicht geladen werden.',error);
  }
}
const path=location.pathname.replace(/\/+$/,'')||'/';
const aliases={'/preise':'preise','/vergleich':'vergleich','/pro':'pro'};
const home=path==='/'||Boolean(aliases[path]);
document.body.classList.toggle('inner-page',!home);
document.querySelector('#footer').innerHTML=footer();
if(home){
  document.querySelector('#content').innerHTML=renderContent();
  if(aliases[path]) requestAnimationFrame(()=>document.getElementById(aliases[path]).scrollIntoView());
  import('./head.js').then(m=>m.initHead()).catch(()=>{document.querySelector('.head-fallback').hidden=false});
}else{
  const legal={'/impressum':'Impressum','/datenschutz':'Datenschutz','/lizenzbedingungen':'Lizenzbedingungen','/agb':'AGB'};
  let title,body;
  if(path==='/checkout'){
    title='Deine PromptMaster-Pro-Lizenzen.';
    body='<p>Prüfe deine gewünschte Benutzerzahl und den Preis für zwölf Monate.</p>'+calculator()+'<div class="notice" role="status">Der Kauf ist in dieser Vorschau noch nicht freigeschaltet. Es wird keine Bestellung angelegt und keine Zahlung ausgelöst.</div><a class="text-link" href="/#preise">← Zurück zu den Preisen</a>';
  }else if(path==='/login'||path==='/portal'||path==='/app/pro'){
    title='Willkommen bei PromptMaster.';
    body='<p>Hier meldest du dich künftig für dein Kundenportal und PromptMaster Pro an.</p><div class="notice">Die Anmeldung ist in dieser Vorschau noch nicht freigeschaltet.</div><a class="button secondary" href="/">Zur Marketingseite →</a>';
  }else if(path==='/free'){
    title='PromptMaster Free.';
    body='<p>Einfach starten. Kostenlos nutzen.</p><div class="notice">Die bestehende PromptMaster-Free-Anwendung ist in dieser Vorschau noch nicht hinterlegt. Sie wird unverändert eingebunden, sobald die Originaldatei vorliegt.</div><a class="button secondary" href="/#funktionen">Free kennenlernen →</a>';
  }else if(legal[path]){
    title=legal[path];
    body='<div class="notice">Die verbindlichen Angaben und Rechtstexte werden vor dem öffentlichen Verkaufsstart ergänzt. Diese Vorschau ermöglicht keinen Kauf.</div><a class="text-link" href="/">← Zurück zur Startseite</a>';
  }else if(path==='/kontakt'||path==='/unternehmen'){
    title=path==='/kontakt'?'Kontakt zu netstyle.':'PromptMaster by netstyle.';
    body='<p>Bessere Prompts für Microsoft Copilot.</p><div class="notice">Die bestätigten Unternehmens- und Kontaktdaten werden vor dem öffentlichen Start ergänzt.</div><a class="text-link" href="/">← Zurück zur Startseite</a>';
  }else{
    title='Diese Seite gibt es nicht.';
    body='<p>Über die Startseite findest du Funktionen, Preise und Antworten auf deine Fragen.</p><a class="button secondary" href="/">Zur Startseite →</a>';
  }
  document.title=title+' | PromptMaster by netstyle';
  document.querySelector('main').innerHTML='<section class="route-page"><span class="status-badge">PromptMaster · Vorschau</span><h1>'+title+'</h1>'+body+'</section>';
}
void initializePricing();
