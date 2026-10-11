import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {renderContent,checkoutPage,footer} from '../src/content.js';
import faq from '../src/faq.json' with {type:'json'};
test('Alle 20 FAQ und vereinbarten Inhaltsbereiche vorhanden',()=>{
  assert.equal(faq.length,20);
  const html=renderContent();
  for(const id of ['funktionen','ablauf','vergleich','preise','pro','faq'])assert.ok(html.includes('id="'+id+'"'));
  assert.equal((html.match(/<details>/g)||[]).length,20);
  for(const app of ['OneNote','OneDrive','SharePoint','Forms','Whiteboard','Loop','Clipchamp','Notebooks','Pages','Planner'])assert.ok(html.includes(app));
});
test('Keine erfundenen Referenzen, KI-Versprechen oder Video-Funktion',async()=>{
  const html=renderContent()+await readFile('index.html','utf8');
  for(const forbidden of ['10.000','Erfolgsgeschichten','Video ansehen','Video abspielen','unsere KI','Priorisierter Support'])assert.ok(!html.includes(forbidden));
});
test('Sichtbare Preise entsprechen der letzten Festlegung inklusive MwSt.',async()=>{
  const html=renderContent()+await readFile('index.html','utf8');
  assert.ok(html.includes('2,99 €'));
  assert.ok(html.includes('35,88 €'));
  assert.ok(html.includes('inkl. MwSt.'));
  for(const forbidden of ['zzgl. gesetzlicher MwSt.','netto pro Benutzer','pro Benutzer · netto'])assert.ok(!html.includes(forbidden),forbidden);
});
test('Alle internen Inhaltsanker existieren',async()=>{
  const html=renderContent()+await readFile('index.html','utf8');
  const ids=new Set([...html.matchAll(/id="([^"]+)"/g)].map(m=>m[1]));
  for(const match of html.matchAll(/href="(?:\/)?#([^"]+)"/g))assert.ok(ids.has(match[1]),match[1]);
});
test('Kopfmodell ist gültiges binäres glTF mit Geometrie',async()=>{
  const b=await readFile('public/models/head.glb');
  assert.equal(b.toString('ascii',0,4),'glTF');assert.equal(b.readUInt32LE(8),b.length);
  const gltf=JSON.parse(b.toString('utf8',20,20+b.readUInt32LE(12)));
  assert.ok(gltf.meshes.length>0);assert.ok(gltf.accessors.some(a=>a.type==='VEC3'&&a.count>1000));
});

test('Pro-Kachel auf der Startseite führt zum Lizenzrechner',async()=>{
  const index=await readFile('index.html','utf8');
  const main=await readFile('src/main.js','utf8');
  assert.match(index,/class="button pro-calculator-link" href="#preise"/);
  assert.match(main,/const scrollToProCalculator=/);
  assert.match(main,/querySelector\('#preise \.calculator'\)/);
  assert.match(main,/scrollIntoView\(\{behavior:motionReduced\.matches\?'auto':'smooth',block:'center'\}\)/);
  assert.match(main,/querySelector\('\.product\.pro'\)/);
});


test('öffentliche Checkout-Seite enthält den vereinbarten Neukunden-Kaufaufbau',async()=>{
  const html=checkoutPage(7);
  const main=await readFile('src/main.js','utf8');
  assert.match(html,/PROMPTFINISHER Pro kaufen/);
  assert.match(html,/value="company" checked/);
  assert.match(html,/value="private"/);
  for(const field of ['first_name','last_name','email','company_name','legal_form','vat_id','tax_number','street','house_number','postal_code','city','country']){
    assert.match(html,new RegExp('name="'+field+'"'));
  }
  assert.match(html,/Bereits|Schon bei PROMPTFINISHER registriert/);
  assert.match(html,/Zahlungspflichtig kaufen/);
  assert.match(html,/Mollie/);
  assert.match(html,/Keine automatische Verlängerung|keine automatische Verlängerung/);
  assert.match(main,/checkoutPage\(requestedQuantity\)/);
  assert.match(main,/customer_type/);
  assert.match(main,/data-checkout-company/);
  assert.match(main,/data-checkout-private/);
});


test('Hauptnavigation benennt Free und Pro eindeutig',async()=>{
  const index=await readFile('index.html','utf8');
  assert.match(index,/href="\/#start">PROMPTFINISHER Free &amp; Pro<\/a>/);
  assert.match(index,/href="\/#funktionen">Funktionen<\/a>/);
  assert.match(index,/href="\/#preise">Preise<\/a>/);
  assert.match(index,/href="\/#vergleich">Vergleich<\/a>/);
  assert.match(index,/href="\/#faq">FAQ<\/a>/);
  assert.doesNotMatch(index,/href="\/#start">Produkte<\/a>/);
  assert.doesNotMatch(index,/href="\/#vergleich">Free vs\. Pro<\/a>/);
});


test('Pro-Kachel verwendet das PROMPTFINISHER-Dreieck statt der Krone',async()=>{
  const index=await readFile('index.html','utf8');
  assert.match(index,/class="brand-triangle-mark"/);
  assert.match(index,/<image href="\/brand\/promptfinisher-logo-hq\.png\?v=20261011-logo1"/);
  assert.doesNotMatch(index,/m7 15 10 8 7-15 7 15 10-8-6 21H13Z/);
  assert.doesNotMatch(index,/M13 42h22/);
});


test('Alle Links von der Marketingseite zu Free öffnen einen neuen Tab ohne Zugriff auf den Ursprungstab',async()=>{
  const index=await readFile('index.html','utf8');
  const main=await readFile('src/main.js','utf8');
  const pages=[
    ['Startseite',index,2],
    ['Marketing-Inhalt',renderContent(),3],
    ['Footer',footer(),1],
    ['Free-Fallback',main,1],
  ];
  for(const [label,html,expected] of pages){
    const links=[...html.matchAll(/<a\\b[^>]*\\bhref="\\/free\\/"[^>]*>/g)].map(match=>match[0]);
    assert.equal(links.length,expected,label+': unerwartete Anzahl Free-Links');
    for(const link of links){
      assert.match(link,/\\btarget="_blank"/,label+': Free muss in neuem Tab öffnen');
      assert.match(link,/\\brel="[^"]*\\bnoopener\\b[^"]*"/,label+': opener muss isoliert bleiben');
      assert.match(link,/\\brel="[^"]*\\bnoreferrer\\b[^"]*"/,label+': Referrer-Schutz fehlt');
    }
  }
  const proLink=index.match(/<a\\b[^>]*class="button pro-calculator-link"[^>]*>/)?.[0];
  assert.ok(proLink,'Pro-Rechner-CTA fehlt');
  assert.doesNotMatch(proLink,/target="_blank"/,'Pro-Rechner bleibt im aktuellen Tab');
});
