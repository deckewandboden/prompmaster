import {renderContent,footer,calculator,checkoutPage} from './content.js';
import {quote,normalizeQuantity,money} from './pricing.js';
const toggle=document.querySelector('.menu-toggle');
toggle.addEventListener('click',()=>{const open=toggle.getAttribute('aria-expanded')!=='true';toggle.setAttribute('aria-expanded',String(open));document.querySelector('nav').classList.toggle('open',open)});
document.querySelectorAll('nav a').forEach(a=>a.addEventListener('click',()=>{toggle.setAttribute('aria-expanded','false');document.querySelector('nav').classList.remove('open')}));
const fallbackCatalog={currency:'EUR',priceBasis:'gross',taxBasisPoints:1900,market:'DE',products:[{id:'PROMPTMASTER_FREE',monthlyGrossCents:0,termMonths:0},{id:'PROMPTMASTER_PRO',monthlyGrossCents:299,termMonths:12}],maxQuantity:500,checkoutEnabled:false,loginEnabled:false,freeUrl:null};
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
    let catalog=fallbackCatalog;
    try{
      const response=await fetch('/catalog.json?marketing=20260919',{cache:'no-store',headers:{Accept:'application/json'}});
      if(!response.ok)throw new Error('Produktkatalog nicht verfügbar');
      const contentType=(response.headers.get('content-type')||'').toLowerCase();
      if(!contentType.includes('application/json'))throw new Error('Produktkatalog wurde nicht als JSON ausgeliefert');
      const liveCatalog=await response.json();
      quote(liveCatalog,1);
      catalog=liveCatalog;
    }catch(error){
      console.warn('Live-Produktkatalog nicht verfügbar; eingebetteter Preiskatalog wird verwendet.',error);
      quote(catalog,1);
    }
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
        const hidden=document.getElementById('checkout-quantity-hidden');
        if(hidden)hidden.value=String(q.quantity);
        const login=document.getElementById('checkout-login-link');
        if(login)login.href='/auth/login/?next='+encodeURIComponent('/portal/licenses/buy/?quantity='+q.quantity);
        if(buy?.tagName==='A'){
          buy.textContent='Zahlungspflichtig kaufen →';
          buy.href='/portal/licenses/buy/?quantity='+q.quantity;
        }
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
  const scrollToProCalculator=()=>{
    const target=document.querySelector('#preise .calculator');
    if(!target)return false;
    target.scrollIntoView({behavior:motionReduced.matches?'auto':'smooth',block:'center'});
    return true;
  };
  document.querySelector('.pro-calculator-link')?.addEventListener('click',event=>{
    if(scrollToProCalculator())event.preventDefault();
  });
  document.querySelector('.product.pro')?.addEventListener('click',event=>{
    if(event.target.closest('a,button,input,select,textarea,label'))return;
    scrollToProCalculator();
  });
  if(aliases[path]) requestAnimationFrame(()=>document.getElementById(aliases[path]).scrollIntoView());
  import('./head.js').then(m=>m.initHead()).catch(()=>{document.querySelector('.head-fallback').hidden=false});
}else{
  const legal={'/impressum':'Impressum','/datenschutz':'Datenschutz','/lizenzbedingungen':'Lizenzbedingungen','/agb':'AGB'};
  let title,body;
  if(path==='/checkout'){
    title='PromptMaster Pro kaufen.';
    const requestedQuantity=normalizeQuantity(new URLSearchParams(location.search).get('quantity')||1,fallbackCatalog.maxQuantity);
    document.querySelector('main').innerHTML=checkoutPage(requestedQuantity);
    body=null;
  }else if(path==='/login'||path==='/portal'||path==='/app/pro'){
    title='Willkommen bei PromptMaster.';
    body='<p>Melde dich an, um Kundenportal und PromptMaster Pro zu öffnen.</p><a class="button" href="/auth/login/">Zur Anmeldung →</a><a class="button secondary" href="/">Zur Marketingseite →</a>';
  }else if(path==='/free'){
    title='PromptMaster Free.';
    body='<p>Einfach starten. Kostenlos nutzen.</p><a class="button" href="/free/">PromptMaster Free starten →</a><a class="button secondary" href="/#funktionen">Free kennenlernen →</a>';
  }else if(legal[path]){
    title=legal[path];
    body='<p>PromptMaster stellt die jeweils gültigen Rechtstexte versioniert über die Commercial-Plattform bereit.</p><a class="text-link" href="/">← Zurück zur Startseite</a>';
  }else if(path==='/kontakt'||path==='/unternehmen'){
    title=path==='/kontakt'?'Kontakt zu netstyle.':'PromptMaster by netstyle.';
    body='<p>PromptMaster by netstyle – bessere Prompts für Microsoft Copilot.</p><a class="text-link" href="/">← Zurück zur Startseite</a>';
  }else{
    title='Diese Seite gibt es nicht.';
    body='<p>Über die Startseite findest du Funktionen, Preise und Antworten auf deine Fragen.</p><a class="button secondary" href="/">Zur Startseite →</a>';
  }
  document.title=title+' | PromptMaster by netstyle';
  if(body!==null){
    document.querySelector('main').innerHTML='<section class="route-page"><span class="status-badge">PromptMaster</span><h1>'+title+'</h1>'+body+'</section>';
  }
}

function setupCheckoutPage(){
  if(path!=='/checkout')return;
  const form=document.getElementById('public-checkout-form');
  if(!form)return;

  const companySection=form.querySelector('[data-checkout-company]');
  const privateLine=form.querySelector('[data-checkout-private]');
  const companyFields=['company_name','legal_form','vat_id','tax_number']
    .map(name=>form.elements.namedItem(name))
    .filter(Boolean);
  const withdrawal=form.elements.namedItem('accept_withdrawal');
  const stage=document.getElementById('checkout-stage-message');

  const syncCustomerType=()=>{
    const type=form.elements.namedItem('customer_type').value;
    const company=type==='company';
    if(companySection)companySection.hidden=!company;
    companyFields.forEach(field=>{
      if(field.name==='company_name')field.required=company;
      field.disabled=!company;
    });
    if(privateLine)privateLine.hidden=company;
    if(withdrawal){
      withdrawal.required=!company;
      if(company)withdrawal.checked=false;
    }
  };

  form.querySelectorAll('input[name="customer_type"]').forEach(input=>{
    input.addEventListener('change',syncCustomerType);
  });
  syncCustomerType();

  form.addEventListener('submit',event=>{
    event.preventDefault();
    if(!form.reportValidity())return;
    if(stage){
      stage.hidden=false;
      stage.innerHTML='<strong>Kaufdaten vollständig.</strong> Die sichere Mollie-Zahlungsübergabe wird als nächster technischer Schritt an diese Maske angebunden; es wurde noch keine Bestellung ausgelöst.';
      stage.scrollIntoView({behavior:motionReduced.matches?'auto':'smooth',block:'nearest'});
    }
  });
}

setupCheckoutPage();
void initializePricing();