import {setupMarketingLocale,marketingT} from './locale.js';
import {renderContent,footer,checkoutPage} from './content.js';
import {quote,normalizeQuantity,money} from './pricing.js';
const toggle=document.querySelector('.menu-toggle');
toggle.addEventListener('click',()=>{const open=toggle.getAttribute('aria-expanded')!=='true';toggle.setAttribute('aria-expanded',String(open));document.querySelector('nav').classList.toggle('open',open)});
document.querySelectorAll('nav a').forEach(a=>a.addEventListener('click',()=>{toggle.setAttribute('aria-expanded','false');document.querySelector('nav').classList.remove('open')}));
const fallbackCatalog={currency:'EUR',priceBasis:'gross',taxBasisPoints:1900,market:'DE',products:[{id:'PROMPTFINISHER_FREE',monthlyGrossCents:0,annualGrossCents:0,termDays:0},{id:'PROMPTFINISHER_PRO',monthlyGrossCents:299,annualGrossCents:3588,termDays:365}],maxQuantity:500,checkoutEnabled:false,loginEnabled:false,freeUrl:null};
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
      if(path==='/checkout'){
        throw new Error('Sicherer Live-Produktkatalog für den Checkout nicht verfügbar',{cause:error});
      }
      console.warn('Live-Produktkatalog nicht verfügbar; eingebetteter Preiskatalog wird verwendet.',error);
      quote(catalog,1);
    }
    if(path==='/checkout'&&catalog.checkoutEnabled!==true){
      throw new Error('Checkout ist im Live-Produktkatalog nicht freigeschaltet');
    }
    const initial=quote(catalog,new URLSearchParams(location.search).get('quantity')||1);
    if(home){
      document.querySelector('.pro .price').innerHTML=money(initial.monthlyGross)+'<span>/ Monat</span>';
      document.querySelector('.pro .price-detail').textContent=marketingT('pro Benutzer · inkl. MwSt.')+' · '+marketingT('jährliche Abrechnung')+': '+money(initial.annualUnitGross);
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
        const checkoutForm=document.getElementById('public-checkout-form');
        const vatField=checkoutForm?.elements.namedItem('vat_id');
        const taxField=checkoutForm?.elements.namedItem('tax_number');
        if(vatField)vatField.required=catalog.companyRequireVatId===true;
        if(taxField)taxField.required=catalog.companyRequireTaxNumber===true;
        const login=document.getElementById('checkout-login-link');
        if(login)login.href='/auth/login/?next='+encodeURIComponent('/portal/licenses/buy/?quantity='+q.quantity);
        const checkoutSubmit=document.getElementById('checkout-submit');
        if(checkoutSubmit){
          checkoutSubmit.disabled=false;
          checkoutSubmit.textContent=marketingT('Zahlungspflichtig kaufen →');
        }
        if(buy?.tagName==='A'){
          buy.textContent=marketingT('Zahlungspflichtig kaufen →');
          buy.href='/portal/licenses/buy/?quantity='+q.quantity;
        }
        history.replaceState(null,'','/checkout/?quantity='+q.quantity);
      }else if(catalog.checkoutEnabled===true){
        buy.removeAttribute('aria-disabled');
        buy.textContent=q.quantity+' '+marketingT(q.quantity===1?'PROMPTFINISHER-Pro-Lizenz kaufen ↗':'PROMPTFINISHER-Pro-Lizenzen kaufen ↗');
        buy.href='/checkout/?quantity='+q.quantity;
      }else{
        buy.removeAttribute('href');
        buy.setAttribute('aria-disabled','true');
        buy.textContent=marketingT('Kauf vorübergehend nicht verfügbar');
      }
    }
    input.addEventListener('change',update);
    input.addEventListener('input',()=>{if(input.value!==''&&Number.isInteger(Number(input.value))&&Number(input.value)>=1)update()});
    document.getElementById('minus').addEventListener('click',()=>{input.value=String(normalizeQuantity(input.value,catalog.maxQuantity)-1);update()});
    document.getElementById('plus').addEventListener('click',()=>{input.value=String(normalizeQuantity(input.value,catalog.maxQuantity)+1);update()});
    update();
  }catch(error){
    if(input){
      input.disabled=true;
      document.getElementById('minus').disabled=true;
      document.getElementById('plus').disabled=true;
      const catalogError=document.getElementById('catalog-error');
      if(catalogError)catalogError.hidden=false;
      const buy=document.getElementById('buy-licenses');
      if(buy){
        buy.removeAttribute('href');
        buy.setAttribute('aria-disabled','true');
        buy.textContent=marketingT('Preis nicht verfügbar');
      }
      const checkoutSubmit=document.getElementById('checkout-submit');
      if(checkoutSubmit){
        checkoutSubmit.disabled=true;
        checkoutSubmit.textContent=marketingT('Preis nicht verfügbar');
      }
      const checkoutStage=document.getElementById('checkout-stage-message');
      if(checkoutStage){
        checkoutStage.hidden=false;
        checkoutStage.textContent='Der aktuelle Preis und Kaufstatus konnten nicht sicher geladen werden. Es wird keine Bestellung gestartet. Bitte lade die Seite neu und versuche es erneut.';
      }
    }
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
  const legal={'/impressum':'Impressum','/datenschutz':'Datenschutz','/lizenzbedingungen':'Lizenzbedingungen','/agb':'AGB','/widerruf':'Widerrufsbelehrung','/barrierefreiheit':'Barrierefreiheit'};
  let title,body;
  if(path==='/checkout'){
    title='PROMPTFINISHER Pro kaufen.';
    const requestedQuantity=normalizeQuantity(new URLSearchParams(location.search).get('quantity')||1,fallbackCatalog.maxQuantity);
    document.querySelector('main').innerHTML=checkoutPage(requestedQuantity);
    body=null;
  }else if(path==='/checkout/success'){
    title='Zahlung wird bestätigt.';
    body='<span class="status-badge">PROMPTFINISHER PRO</span><h1>Zahlung wird bestätigt.</h1><p>Mollie hat dich zu PROMPTFINISHER zurückgeführt. Sobald die Zahlung serverseitig bestätigt wurde, werden deine Pro-Lizenzen automatisch aktiviert.</p><p>Bei einem neu angelegten Kundenkonto erhältst du anschließend eine E-Mail, über die du dein Passwort festlegst und den Zugang aktivierst.</p><a class="button" href="/auth/login/">Zum Kundenkonto →</a><a class="button secondary" href="/">Zur Startseite →</a>';
  }else if(path==='/login'||path==='/portal'||path==='/app/pro'){
    title='Willkommen bei PROMPTFINISHER.';
    body='<p>Melde dich an, um Kundenportal und PROMPTFINISHER Pro zu öffnen.</p><a class="button" href="/auth/login/">Zur Anmeldung →</a><a class="button secondary" href="/">Zur Marketingseite →</a>';
  }else if(path==='/free'){
    title='PROMPTFINISHER Free.';
    body='<p>Einfach starten. Kostenlos nutzen.</p><a class="button" href="/free/" target="_blank" rel="noopener noreferrer">PROMPTFINISHER Free starten →</a><a class="button secondary" href="/#funktionen">Free kennenlernen →</a>';
  }else if(legal[path]){
    title=legal[path];
    body='<p>PROMPTFINISHER stellt die jeweils gültigen Rechtstexte versioniert über die Commercial-Plattform bereit.</p><a class="text-link" href="/">← Zurück zur Startseite</a>';
  }else if(path==='/kontakt'||path==='/unternehmen'){
    const contact=path==='/kontakt';
    title=marketingT(contact?'Kontakt zu netstyle':'Über netstyle');
    const intro=marketingT(contact
      ?'Fragen zu PROMPTFINISHER? Wir helfen dir bei Produktfragen und Anfragen weiter.'
      :'PROMPTFINISHER ist ein Produkt der netstyle Informationstechnik GmbH aus Kreuztal.');
    const details=contact
      ? marketingT('Du erreichst das Team per E-Mail, telefonisch oder über das Kontaktformular von netstyle.')
      : marketingT('netstyle ist ein IT-Systemhaus für kleine und mittelständische Unternehmen. Schwerpunkte sind IT-Infrastruktur, ERP-Lösungen rund um Sage 100 und ergänzende Softwarelösungen.');
    body=`<div class="info-intro"><p>${intro}</p><p>${details}</p></div>
      <div class="info-grid">
        <section class="info-card"><span class="info-card-icon" aria-hidden="true">✉</span>
          <h2>${marketingT('Direkter Kontakt')}</h2>
          <p><a href="mailto:info@netstyle.de">info@netstyle.de</a></p>
          <p><a href="tel:+49273259280">+49 2732 59280</a></p>
          <a class="button secondary" href="mailto:info@netstyle.de">${marketingT('E-Mail schreiben')} →</a>
        </section>
        <section class="info-card"><span class="info-card-icon" aria-hidden="true">↗</span>
          <h2>${marketingT('netstyle Informationstechnik GmbH')}</h2>
          <p>Am Bühl 2<br>57223 Kreuztal</p>
          <a class="button" href="https://www.netstyle.de/kontakt/" target="_blank" rel="noopener noreferrer">${marketingT('Kontaktformular öffnen')} ↗</a>
        </section>
      </div>
      <div class="info-bottom"><a class="text-link" href="https://www.netstyle.de/" target="_blank" rel="noopener noreferrer">${marketingT('Mehr über netstyle erfahren')} ↗</a>
      <a class="text-link" href="/">← ${marketingT('Zurück zur Startseite')}</a></div>`;
  }else{
    title='Diese Seite gibt es nicht.';
    body='<p>Über die Startseite findest du Funktionen, Preise und Antworten auf deine Fragen.</p><a class="button secondary" href="/">Zur Startseite →</a>';
  }
  document.title=title+' | PROMPTFINISHER by netstyle';
  if(body!==null){
    document.querySelector('main').innerHTML='<section class="route-page'+((path==='/kontakt'||path==='/unternehmen')?' info-route':'')+'"><span class="status-badge">PROMPTFINISHER</span><h1>'+title+'</h1>'+body+'</section>';
  }
}

function setupCheckoutPage(){
  if(path!=='/checkout')return;
  const form=document.getElementById('public-checkout-form');
  if(!form)return;

  const companySection=form.querySelector('[data-checkout-company]');
  const privateLines=[...form.querySelectorAll('[data-checkout-private]')];
  const companyFields=['company_name','legal_form','vat_id','tax_number']
    .map(name=>form.elements.namedItem(name))
    .filter(Boolean);
  const withdrawal=form.elements.namedItem('accept_withdrawal');
  const earlyPerformance=form.elements.namedItem('request_early_performance');
  const stage=document.getElementById('checkout-stage-message');
  const submit=document.getElementById('checkout-submit');
  const csrfInput=document.getElementById('checkout-csrf');
  const legalInput=document.getElementById('checkout-legal-snapshot');

  const showStage=(message)=>{
    if(!stage)return;
    stage.hidden=false;
    stage.textContent=message;
  };

  const checkoutError=new URLSearchParams(location.search).get('error');
  if(checkoutError){
    const messages={
      invalid:'Bitte prüfe deine Angaben und versuche es erneut.',
      unavailable:'Der Kauf ist gerade nicht verfügbar. Bitte versuche es später erneut.',
      payment:'Die Zahlung konnte nicht vorbereitet werden. Es wurde nichts freigeschaltet. Bitte versuche es erneut.',
    };
    showStage(messages[checkoutError]||'Der Kauf konnte nicht gestartet werden. Bitte versuche es erneut.');
  }

  const syncCustomerType=()=>{
    const type=form.elements.namedItem('customer_type').value;
    const company=type==='company';
    if(companySection)companySection.hidden=!company;
    companyFields.forEach(field=>{
      if(field.name==='company_name')field.required=company;
      field.disabled=!company;
    });
    privateLines.forEach(line=>{line.hidden=company});
    for(const field of [withdrawal,earlyPerformance]){
      if(!field)continue;
      field.required=!company;
      if(company)field.checked=false;
    }
  };

  form.querySelectorAll('input[name="customer_type"]').forEach(input=>{
    input.addEventListener('change',syncCustomerType);
  });
  syncCustomerType();

  let legalPromise=null;
  let legalType='';
  const ensureLegalSnapshot=()=>{
    const customerType=form.querySelector('input[name="customer_type"]:checked')?.value||'company';
    if(legalInput?.value && legalType===customerType){
      return Promise.resolve(legalInput.value);
    }
    // Snapshot nonces are session-bound; concurrent customer-type fetches
    // could invalidate the response that the browser displays last.
    if(legalPromise){
      if(legalType===customerType)return legalPromise;
      return legalPromise.catch(()=>null).then(()=>ensureLegalSnapshot());
    }
    legalType=customerType;
    if(legalInput)legalInput.value='';
    const requestedType=customerType;
    const requestPromise=fetch(
      '/api/v1/checkout/legal-snapshot/?customer_type='+encodeURIComponent(requestedType),
      {method:'GET',credentials:'same-origin',cache:'no-store',headers:{Accept:'application/json'}},
    ).then(async response=>{
      if(!response.ok)throw new Error('Legal snapshot unavailable');
      const snapshot=await response.json();
      if(!snapshot.token || snapshot.customerType!==requestedType){
        throw new Error('Invalid legal snapshot');
      }
      if(legalType!==requestedType)return ensureLegalSnapshot();
      if(requestedType==='private' && (
        !snapshot.earlyPerformance?.text || !snapshot.earlyPerformance?.sha256 ||
        !snapshot.earlyPerformance?.statement_id
      ))throw new Error('Early performance consent version missing');
      if(legalInput)legalInput.value=snapshot.token;
      if(requestedType==='private'){
        const statement=form.querySelector('[data-legal-early-performance-text]');
        if(statement)statement.textContent=snapshot.earlyPerformance.text;
      }
      for(const type of ['terms','privacy','license','withdrawal']){
        const href=snapshot.documents?.[type]?.url;
        if(!href)continue;
        const link=form.querySelector('.checkout-legal a[href^="/legal/'+type+'/"]');
        if(link)link.href=href;
      }
      return snapshot.token;
    }).finally(()=>{
      if(legalPromise===requestPromise)legalPromise=null;
    });
    legalPromise=requestPromise;
    return requestPromise;
  };
  form.querySelectorAll('input[name="customer_type"]').forEach(input=>{
    input.addEventListener('change',()=>{
      void ensureLegalSnapshot().catch(()=>{
        showStage(marketingT('Die rechtlichen Dokumentversionen konnten nicht geladen werden. Bitte lade den Kauf erneut.'));
      });
    });
  });
  void ensureLegalSnapshot().catch(()=>{
    showStage(marketingT('Die rechtlichen Dokumentversionen konnten nicht geladen werden. Bitte lade den Kauf erneut.'));
  });

  let csrfPromise=null;
  const ensureCsrf=()=>{
    if(csrfInput?.value)return Promise.resolve(csrfInput.value);
    if(!csrfPromise){
      csrfPromise=fetch('/api/v1/checkout/csrf/',{
        method:'GET',
        credentials:'same-origin',
        cache:'no-store',
        headers:{Accept:'application/json'},
      }).then(async response=>{
        if(!response.ok)throw new Error('CSRF token unavailable');
        const payload=await response.json();
        if(!payload.csrfToken)throw new Error('CSRF token missing');
        if(csrfInput)csrfInput.value=payload.csrfToken;
        return payload.csrfToken;
      }).finally(()=>{csrfPromise=null});
    }
    return csrfPromise;
  };

  void ensureCsrf().catch(()=>{});

  form.addEventListener('submit',async event=>{
    event.preventDefault();
    if(!form.reportValidity())return;
    if(submit){
      submit.disabled=true;
      submit.textContent=marketingT('Kauf wird vorbereitet …');
    }
    try{
      await Promise.all([ensureCsrf(),ensureLegalSnapshot()]);
      if(!legalInput?.value)throw new Error('Legal snapshot missing');
      HTMLFormElement.prototype.submit.call(form);
    }catch(error){
      console.error('Checkout konnte nicht gestartet werden.',error);
      showStage('Die sichere Kaufverbindung konnte nicht vorbereitet werden. Bitte lade die Seite neu und versuche es erneut.');
      if(submit){
        submit.disabled=false;
        submit.textContent=marketingT('Zahlungspflichtig kaufen →');
      }
    }
  });
}

setupCheckoutPage();
void initializePricing();
setupMarketingLocale();
