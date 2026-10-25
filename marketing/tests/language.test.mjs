import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {languageNames, marketingCatalog} from '../src/locale.js';

const languages=['de','en','es','pt','tr','ru','pl','fr','it','nl'];

test('all ten supported product languages appear in marketing selection',()=>{
 assert.deepEqual(Object.keys(languageNames),languages);
 for(const [term,translations] of Object.entries(marketingCatalog)){
  assert.ok(term.trim(), 'empty source');
  for(const lang of languages.slice(1)){
   assert.ok(typeof translations[lang]==='string' && translations[lang].trim(), lang+': '+term);
   assert.notEqual(translations[lang],undefined);
  }
 }
});
test('language chooser is visible and tied to backend language cookie',async()=>{
 const index=await readFile('index.html','utf8');
 const main=await readFile('src/main.js','utf8');
 const source=await readFile('src/locale.js','utf8');
 assert.match(main,/setupMarketingLocale\(\);/);
 assert.match(index,/promptfinisher_product_i18n\.20261011\.js/);
 const selector=index.match(/<select id="pf-marketing-language"[^>]*>([\s\S]*?)<\/select>/);
 assert.ok(selector,'Selector must render before JavaScript executes');
 for(const lang of languages)assert.match(selector[1],new RegExp('<option value="'+lang+'">'));
 assert.match(source,/let select=document\.getElementById\('pf-marketing-language'\)/);

 assert.match(source,/pf-marketing-language/);
 assert.match(source,/promptfinisher_language/);
 assert.match(source,/\/auth\/language\/\?language=/);
 assert.match(source,/encodeURIComponent\(next\)/);
 assert.match(source,/document\.documentElement\.lang=lang/);
});
test('marketing and Free/Pro ship exactly the same product translation cache revision',async()=>{
 const index=await readFile('index.html','utf8');
 const views=await readFile('../backend/apps/proaccess/views.py','utf8');
 const rev=views.match(/V2_ASSET_REV = b'([^']+)'/);
 assert.ok(rev,'Django V2_ASSET_REV must exist');
 const scripts=[...index.matchAll(/<script[^>]+src="([^"]+)"[^>]*>/g)].map(m=>m[1]);
 const i18n=scripts.filter(s=>s.startsWith('/static/js/promptfinisher_product_i18n.20261011.js?'));
 assert.equal(i18n.length,1,'Marketing must load the product dictionary exactly once');
 assert.equal(i18n[0],'/static/js/promptfinisher_product_i18n.20261011.js?v='+rev[1],
   'Marketing and Django Free/Pro must invalidate old localized JavaScript together');
});
test('marketing localization must never change forms, products or typed prompts',async()=>{
 const source=await readFile('src/locale.js','utf8');
 assert.match(source,/input,textarea,select,option,script,style,\[contenteditable\]/);
 assert.match(source,/\.app-pill/);
 assert.doesNotMatch(source,/\.value\s*=\s*translated/);
});
test('marketing language chooser is right of FAQ, before login, and accessible on narrow screens',async()=>{
 const index=await readFile('index.html','utf8');
 const css=await readFile('src/immersive.css','utf8');
 const headerStart=index.indexOf('<header>');
 const headerEnd=index.indexOf('</header>');
 const header=headerStart>=0 && headerEnd>headerStart ? index.slice(headerStart,headerEnd+'</header>'.length) : null;
 assert.ok(header,'Marketing header missing');
 assert.ok(header.indexOf('href="/#faq"')<header.indexOf('class="header-actions"'),'FAQ must precede header actions');
 assert.ok(header.indexOf('class="pf-marketing-locale"')<header.indexOf('class="login-link"'),'Language control must precede Login');
 assert.equal((header.match(/id="pf-marketing-language"/g)||[]).length,1,'Exactly one synchronized language chooser');
 assert.match(header,/<svg class="pf-marketing-locale-icon"[^>]*aria-hidden="true">/);
 assert.match(header,/<a href="\/login\/" class="mobile-login-link">Anmelden<\/a>/);
 assert.match(header,/<a href="\/free\/"[^>]*class="button mobile-nav-cta">Jetzt starten<\/a>/);
 assert.match(css,/header \.header-actions\{display:flex/);
 assert.match(css,/\.pf-marketing-locale:focus-within\{/);
 assert.match(css,/@media\(max-width:1280px\)/);
 assert.match(css,/header nav\.open\{display:flex\}/);
 assert.match(css,/@media\(max-width:360px\)/);
});

test('all visible static marketing German text is translated in every target language',async()=>{
 const html=(await readFile('index.html','utf8'))+'\n'+(await readFile('src/content.js','utf8'));
 const brandTerms=new Set([
  'PROMPTFINISHER','PROMPTFINISHER Pro','PROMPTFINISHER PRO',
  'PROMPTFINISHER Free &amp; Pro','PROMPTFINISHER · Free &amp; Pro',
  'FAQ','FREE','PRO','Free','Pro','netstyle',
  'Deutsch','English','Español','Português','Türkçe','Русский',
  'Polski','Français','Italiano','Nederlands',
  "':b==='–'?'",
 ]);
 const hits=[...html.matchAll(/>([^<>{}]+)</g)]
  .map(m=>m[1].trim())
  .filter(text=>text.length>2&&/[a-zA-ZÄÖÜäöüß]/.test(text));
 const missing=[...new Set(hits)].filter(text=>{
  if(brandTerms.has(text))return false;
  if(text.startsWith('3D-Modell: Lee Perry-Smith'))return false;
  return !Object.prototype.hasOwnProperty.call(marketingCatalog,text);
 });
 assert.deepEqual(missing,[],'Visible source copy without nine-language marketing translation');
 for(const source of new Set(hits)){
  if(brandTerms.has(source)||source.startsWith('3D-Modell: Lee Perry-Smith')||!marketingCatalog[source])continue;
  for(const lang of languages.slice(1)){
   assert.ok(marketingCatalog[source][lang]?.trim(),source+' is missing '+lang);
  }
 }
});


test('all public rendered marketing/checkout/FAQ text has a translation in nine locales',async()=>{
 const {renderContent,footer,checkoutPage}=await import('../src/content.js');
 const index=await readFile('index.html','utf8');
 const catalogSource=await readFile('../backend/static/js/promptfinisher_product_i18n.20261011.js','utf8');
 const baseMatch=catalogSource.match(/^\s*const TEXT=(\{.*\});\s*$/m);
 const extraMatch=catalogSource.match(/^\s*Object\.assign\(TEXT,(\{.*\})\);\s*$/m);
 assert.ok(baseMatch && extraMatch,'Free/Pro translation dictionaries missing');
 const shared={...JSON.parse(baseMatch[1]),...JSON.parse(extraMatch[1])};
 const html=index+'\n'+renderContent()+footer()+checkoutPage(1);
 const labels=[...html.matchAll(/>([^<>]+)</g)].map(m=>m[1].trim());
 const attrs=[...html.matchAll(/(?:aria-label|placeholder|title)="([^"]+)"/g)].map(m=>m[1].trim());
 const knownBrand=new Set([
  'PROMPTFINISHER','PROMPTFINISHER Free &amp; Pro','PROMPTFINISHER · Free &amp; Pro',
  'Free','Pro','FREE','PRO','FAQ','netstyle','Deutsch','English',
  'Español','Português','Türkçe','Русский','Polski','Français','Italiano','Nederlands',
 ]);
 const appNames=[...html.matchAll(/class="app-pill">([^<]+)</g)].map(m=>m[1]);
 for(const app of appNames)knownBrand.add(app);
 const unknown=[];
 for(const phrase of [...labels,...attrs]){
   if(!phrase || knownBrand.has(phrase) || !/[\p{L}]/u.test(phrase))continue;
   if(/^\d+[\d., ]*\s*(?:€|\/.*)?$/.test(phrase))continue;
   if(/^\s*(?:✓|−|–)\s*$/.test(phrase))continue;
   if(phrase.includes('${') || phrase.includes('`'))continue;
   // Legal attribution CC license names stay verbatim; the leading UI string
   // is translated by the public locale catalog where applicable.
   if(phrase.startsWith('© '))continue;
   const row=marketingCatalog[phrase]||shared[phrase];
   if(!row){unknown.push(phrase);continue;}
   for(const lang of languages.slice(1))
     if(typeof row[lang]!=='string'||!row[lang].trim())
       unknown.push(lang+':'+phrase);
 }
 assert.deepEqual([...new Set(unknown)].sort(),[], 'Unlocalized public text/attributes');
});

test('localized marketing SEO metadata has all ten-language descriptions',async()=>{
 const index=await readFile('index.html','utf8');
 const source=await readFile('src/locale.js','utf8');
 const match=index.match(/<meta name="description" content="([^"]+)"/);
 assert.ok(match,'marketing description must be visible in HTML');
 for(const lang of languages.slice(1)){
  assert.ok(marketingCatalog[match[1]]?.[lang]?.includes('PROMPTFINISHER'),lang+' missing description translation');
 }
 assert.match(source,/description\.setAttribute\('content',translated\)/);
});

test('company and contact pages have substantive routes and complete locale copy',async()=>{
 const main=await readFile('src/main.js','utf8');
 const css=await readFile('src/immersive.css','utf8');
 const required=[
  'Kontakt zu netstyle','Über netstyle','Direkter Kontakt',
  'PROMPTFINISHER ist ein Produkt der netstyle Informationstechnik GmbH aus Kreuztal.',
  'Fragen zu PROMPTFINISHER? Wir helfen dir bei Produktfragen und Anfragen weiter.',
  'Kontaktformular öffnen','Mehr über netstyle erfahren','Zurück zur Startseite',
 ];
 for(const term of required){
  const entries=marketingCatalog[term];
  assert.ok(entries,'Missing company/contact translation: '+term);
  for(const lang of languages.slice(1))
   assert.ok(entries[lang]?.trim(),lang+' missing '+term);
 }
 for(const route of ['/kontakt','/unternehmen'])assert.ok(main.includes(route));
 assert.match(main,/href="mailto:info@netstyle\.de"/);
 assert.match(main,/href="https:\/\/www\.netstyle\.de\/kontakt\/"/);
 assert.match(css,/\.route-page\.info-route/);
 assert.match(css,/\.info-route \.info-grid/);
 assert.match(css,/@media\(max-width:650px\)/);
});

test('every public checkout failure message is localized in all languages',async()=>{
 const messages=[
  'Bitte prüfe deine Angaben und versuche es erneut.',
  'Der Kauf ist gerade nicht verfügbar. Bitte versuche es später erneut.',
  'Die Zahlung konnte nicht vorbereitet werden. Es wurde nichts freigeschaltet. Bitte versuche es erneut.',
  'Der Kauf konnte nicht gestartet werden. Bitte versuche es erneut.',
  'Die sichere Kaufverbindung konnte nicht vorbereitet werden. Bitte lade die Seite neu und versuche es erneut.',
  'Der aktuelle Preis und Kaufstatus konnten nicht sicher geladen werden. Es wird keine Bestellung gestartet. Bitte lade die Seite neu und versuche es erneut.',
 ];
 for(const key of messages){
  const entry=marketingCatalog[key];
  assert.ok(entry, 'checkout error without translation: '+key);
  for(const lang of languages.slice(1)){
   assert.ok(typeof entry[lang]==='string'&&entry[lang].trim(),lang+': '+key);
   assert.notEqual(entry[lang],key,lang+' still displays German checkout error');
  }
 }
 const main=await readFile('src/main.js','utf8');
 assert.match(main,/showStage\(marketingT\(messages\[checkoutError\]/);
 assert.match(main,/showStage\(marketingT\('Die sichere Kaufverbindung konnte nicht vorbereitet werden/);
 assert.ok(main.includes('checkoutStage.textContent=marketingT('),'Catalog failure must be localized');
 assert.ok(main.includes("marketingT('Monat')"),'Dynamic billing period must be localized');
 for(const language of languages.slice(1)){
  assert.ok(marketingCatalog.Monat?.[language]?.trim(),language+' missing price period translation');
 }
});

test('checkout replaces expired signed legal offers before payment submission',async()=>{
 const main=await readFile('src/main.js','utf8');
 assert.match(main,/let legalExpiresAt=0/);
 assert.match(main,/legalExpiresAt>Date\.now\(\)\+60\*1000/);
 assert.match(main,/snapshot\.expiresInSeconds<120/);
 assert.match(main,/legalExpiresAt=Date\.now\(\)\+Math\.min\(/);
 assert.match(main,/await Promise\.all\(\[ensureCsrf\(\),ensureLegalSnapshot\(\)\]\)/);
});
