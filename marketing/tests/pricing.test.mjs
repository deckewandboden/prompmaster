import test from 'node:test';
import assert from 'node:assert/strict';
import catalog from '../public/catalog.json' with {type:'json'};
import {quote,normalizeQuantity,money} from '../src/pricing.js';
test('Vereinbarte Jahrespreise für 1, 3 und 8 Benutzer',()=>{
  for(const [count,gross] of [[1,3588],[3,10764],[8,28704]])assert.equal(quote(catalog,count).gross,gross);
});
test('MwSt. ist im vereinbarten Bruttopreis enthalten und wird nicht aufgeschlagen',()=>{
  assert.deepEqual([quote(catalog,1).net,quote(catalog,1).tax,quote(catalog,1).gross],[3015,573,3588]);
  assert.deepEqual([quote(catalog,3).net,quote(catalog,3).tax,quote(catalog,3).gross],[9045,1719,10764]);
  assert.deepEqual([quote(catalog,8).net,quote(catalog,8).tax,quote(catalog,8).gross],[24121,4583,28704]);
});
test('Grenzen und manipulierte Mengen bleiben gültig',()=>{
  for(const invalid of [undefined,NaN,Infinity,-1,0,'', 'abc', '-80'])assert.equal(normalizeQuantity(invalid),1);
  assert.equal(normalizeQuantity('3.9'),3);
  assert.equal(normalizeQuantity(1e20),999);
  assert.equal(quote(catalog,'999999').quantity,999);
});
test('Ein aktualisierter Katalog ändert Preise ohne Änderung der Rechenlogik',()=>{
  const changed=structuredClone(catalog);changed.products[1].monthlyGrossCents=399;
  assert.equal(quote(changed,3).gross,14364);
  assert.equal(quote(catalog,3).gross,10764);
});
test('Ungültige Kataloge werden abgewiesen',()=>{
  for(const value of [-1,2.99,NaN,Infinity]){const changed=structuredClone(catalog);changed.products[1].monthlyGrossCents=value;assert.throws(()=>quote(changed,1))}
  assert.throws(()=>quote({...catalog,products:[]},1));
});
test('Deutsche Währungsdarstellung',()=>assert.equal(money(3588).replace(/\s/g,' '),'35,88 €'));
