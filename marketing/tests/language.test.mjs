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
 assert.match(source,/pf-marketing-language/);
 assert.match(source,/promptfinisher_language/);
 assert.match(source,/\/auth\/language\/\?language=/);
 assert.match(source,/next=\+encodeURIComponent\(next\)/);
 assert.match(source,/document\.documentElement\.lang=lang/);
});
test('marketing localization must never change forms, products or typed prompts',async()=>{
 const source=await readFile('src/locale.js','utf8');
 assert.match(source,/input,textarea,select,option,script,style,\[contenteditable\]/);
 assert.match(source,/\.app-pill/);
 assert.doesNotMatch(source,/\.value\s*=\s*translated/);
});
test('marketing switcher layout does not create stacked actions',async()=>{
 const css=await readFile('src/style.css','utf8');
 assert.match(css,/\.pf-marketing-locale\{/);
 assert.match(css,/header nav\{order:2\}/);
 assert.match(css,/max-width:430px/);
});
