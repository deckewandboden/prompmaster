import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const read=(p)=>readFileSync(new URL('../'+p,import.meta.url),'utf8');

test('reconstructed marketing uses latest recovered head engine',()=>{
  const head=read('src/head.js');
  assert.match(head,/count=mobile\?8200:22000/);
  assert.match(head,/topologyGeometry/);
  assert.match(head,/uDissolve/);
  assert.match(head,/shootingStars/);
  assert.match(head,/initCanvasHead/);
  assert.doesNotMatch(head,/pm-headtrack|getUserMedia|enumerateDevices/);
  assert.doesNotMatch(head,/Bewegung pausieren|Bewegung aktivieren|motion-button/);
  assert.match(head,/loadAsync\('\/models\/head\.glb'\)/);
});

test('non-WebGL fallback keeps the actual head visible without camera access',()=>{
  const fallback=read('src/head-canvas2d.js');
  assert.match(fallback,/models\/head\.glb/);
  assert.match(fallback,/getContext\('2d'/);
  assert.match(fallback,/head-fallback-canvas/);
  assert.doesNotMatch(fallback,/getUserMedia|enumerateDevices|camera|Bewegung pausieren|Bewegung aktivieren|motion-button/i);
  assert.doesNotMatch(fallback,/Aus deiner Aufgabe wird ein präziser Copilot-Prompt/i);
  assert.match(fallback,/const base=height\*projectionScale/);
  assert.match(fallback,/groundParticles/);
  assert.match(fallback,/blendParticles/);
  assert.match(fallback,/beacons/);
  assert.match(fallback,/traffic/);
  assert.match(fallback,/skyLights/);
  assert.match(fallback,/shootingStars/);
  assert.match(fallback,/sampleSurfacePoints/);
  assert.match(fallback,/viewZ=mobile\?5\.3:4\.35/);
  assert.match(fallback,/projectionScale=1\/\(2\*Math\.tan\(39\*Math\.PI\/360\)\*viewZ\)/);
});

test('hero and marketing copy use recovered V15 decisions',()=>{
  const index=read('index.html');
  const content=read('src/content.js');
  assert.doesNotMatch(index,/Aus deiner Aufgabe wird ein präziser Copilot-Prompt/i);
  assert.match(index,/WENIGE KLICKS/);
  assert.match(index,/Erweiterter Copilot-Katalog/);
  assert.match(index,/Laufende Weiterentwicklungen inklusive/);
  assert.match(content,/Aus einer Idee wird ein Auftrag, den Copilot versteht/);
  assert.match(content,/Kontext ergänzen/);
  assert.match(content,/Detailgrad, Tonalität und Quellenstrategie/);
  assert.doesNotMatch(content,/Vorschau · Kauf und Anmeldung noch nicht freigeschaltet/);
});

test('pricing calculator survives stale non-JSON browser responses',()=>{
  const main=read('src/main.js');
  assert.match(main,/fallbackCatalog/);
  assert.match(main,/cache:'no-store'/);
  assert.match(main,/Accept:'application\/json'/);
  assert.match(main,/eingebetteter Preiskatalog/);
});

test('static compatibility pages no longer claim product is unavailable',()=>{
  const main=read('src/main.js');
  assert.doesNotMatch(main,/Kauf noch nicht freigeschaltet/);
  assert.doesNotMatch(main,/Anmeldung ist in dieser Vorschau noch nicht freigeschaltet/);
  assert.doesNotMatch(main,/Vorschau/);
  assert.doesNotMatch(main,/öffentlichen Start/);
  assert.match(main,/\/portal\/licenses\/buy\//);
  assert.match(main,/\/auth\/login\//);
});