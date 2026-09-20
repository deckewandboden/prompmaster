import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
const file=(p)=>readFileSync(new URL('../'+p,import.meta.url));
const read=(p)=>file(p).toString('utf8');
const gitBlobSha=(p)=>{
  const data=file(p);
  return createHash('sha1')
    .update(Buffer.from(`blob ${data.length}\0`))
    .update(data)
    .digest('hex');
};

test('reconstructed marketing uses latest recovered head engine',()=>{
  const head=read('src/head.js');
  assert.match(head,/count=mobile\?8200:22000/);
  assert.match(head,/topologyGeometry/);
  assert.match(head,/uDissolve/);
  assert.match(head,/shootingStars/);
  assert.match(head,/createLowerSceneData/);
  assert.match(head,/stage\.dataset\.beaconProbe=probe\.join\(','\)/);
  assert.match(head,/stage\.dataset\.headYaw=group\.rotation\.y\.toFixed\(4\)/);
  assert.match(head,/point\.x\+cityBeacons\.position\.x/);
  assert.match(head,/createShootingStarCanvas/);
  assert.match(head,/getShootingStarState/);
  assert.match(head,/new THREE\.CanvasTexture\(createShootingStarCanvas\(reverse\)\)/);
  assert.match(head,/const state=getShootingStarState\(spec,elapsed,smoothPointerX\)/);
  assert.match(head,/lowerSceneContract='edge-shared-v1'/);
  assert.match(head,/initCanvasHead/);
  assert.doesNotMatch(head,/pm-headtrack|getUserMedia|enumerateDevices/);
  assert.doesNotMatch(head,/Bewegung pausieren|Bewegung aktivieren|motion-button/);
  assert.match(head,/loadAsync\('\/models\/head\.glb'\)/);
  assert.doesNotMatch(head,/const firefox=\/Firefox\\\//);
  assert.doesNotMatch(head,/powerPreference=firefox/);
  assert.match(head,/powerPreference:'low-power'/);
  assert.match(head,/failIfMajorPerformanceCaveat:false/);
  assert.match(head,/stage\.dataset\.webglInit=attempt\.id/);
  assert.match(head,/edge-webgl2-no-msaa/);
  assert.match(head,/edge-webgl2-minimal/);
  assert.match(head,/edge-three-managed-no-msaa/);
  assert.match(head,/stage\.dataset\.webglAttempts/);
  assert.match(head,/stage\.dataset\.webglCleanup='1'/);
  assert.match(head,/stage\.dataset\.webglInit='canvas-context-loss'/);
  assert.match(head,/delete stage\.dataset\.eyeContract/);
  assert.match(head,/canvas\.removeEventListener\('webglcontextlost',onLost\)/);
  assert.match(head,/const freshCanvas=/);
  assert.match(head,/cloneNode\(false\)/);
  assert.match(head,/attemptIndex>0\)freshCanvas\(\)/);
  assert.match(head,/stage\.dataset\.webglInit='canvas-emergency'/);
  assert.match(head,/eyeContract='edge-shared-webgl'/);
  assert.match(head,/let cleanup=\(\)=>\{\}/);
  assert.match(head,/cleanup\(\);[\s\S]*initCanvasHead\(\{sourceCanvas:canvas,stage,fallback\}\)/);
  assert.match(head,/canvas\.removeEventListener\('webglcontextlost',onLost\)/);
  assert.match(head,/new THREE\.WebGLRenderer/);
  assert.equal(gitBlobSha('public/models/head.glb'),'cff335de726fa518c1ef80f4c8aa540037b2f5b2');
});

test('non-WebGL fallback keeps the actual head visible without camera access',()=>{
  const fallback=read('src/head-canvas2d.js');
  assert.match(fallback,/models\/head\.glb/);
  assert.match(fallback,/getContext\('2d'/);
  assert.match(fallback,/head-fallback-canvas/);
  assert.doesNotMatch(fallback,/getUserMedia|enumerateDevices|navigator\.mediaDevices|pm-headtrack|Bewegung pausieren|Bewegung aktivieren|motion-button/i);
  assert.doesNotMatch(fallback,/Aus deiner Aufgabe wird ein präziser Copilot-Prompt/i);
  assert.match(fallback,/const base=height\*projectionScale/);
  assert.match(fallback,/groundParticles/);
  assert.match(fallback,/mobile\?1500:4200/);
  assert.match(fallback,/blendParticles/);
  assert.match(fallback,/mobile\?850:2400/);
  assert.match(fallback,/beacons/);
  assert.match(fallback,/mobile\?58:150/);
  assert.match(fallback,/const beaconProbe=\[\]/);
  assert.match(fallback,/stage\.dataset\.beaconProbe=beaconProbe\.join\(','\)/);
  assert.match(fallback,/traffic/);
  assert.match(fallback,/mobile\?16:38/);
  assert.match(fallback,/skyLights/);
  assert.match(fallback,/mobile\?105:245/);
  assert.match(fallback,/eyeAnchors/);
  assert.match(fallback,/stage\.dataset\.eyeAnchors/);
  assert.match(fallback,/delete stage\.dataset\.eyeContract/);
  assert.match(fallback,/shootingStars/);
  assert.match(fallback,/export function createShootingStarCanvas/);
  assert.match(fallback,/export function getShootingStarState/);
  assert.match(fallback,/const state=getShootingStarState\(star,elapsed,smoothX\)/);
  assert.match(fallback,/createShootingStarCanvas\(false\)/);
  assert.match(fallback,/createShootingStarCanvas\(true\)/);
  assert.match(fallback,/export function createLowerSceneData/);
  assert.match(fallback,/length:6/);
  assert.match(fallback,/offset:\.45\+index\*1\.72/);
  assert.match(fallback,/period:9\.1\+\(index%3\)\*1\.05/);
  assert.match(fallback,/sceneLayers/);
  assert.match(fallback,/drawSceneLayers/);
  assert.match(fallback,/const dustCount=mobile\?220:680/);
  assert.match(fallback,/dustPoints/);
  assert.match(fallback,/dustLayer=createSceneLayer\(\)/);
  assert.match(fallback,/rgba\(52,147,223,\.30\)/);
  assert.match(fallback,/\.012\*\(height\*\.5\)\/depth/);
  assert.match(fallback,/offsetX=-smoothX\*\.06\*worldPixelScale/);
  assert.match(fallback,/offsetY=-smoothY\*\.03\*worldPixelScale/);
  assert.match(fallback,/drawDustLayer\(\)/);
  assert.match(fallback,/meta\.scaleSum\+=worldPixelScale/);
  assert.match(fallback,/drawSceneLayers\(sceneLayers\.landscape,\.72,\.075,\.018,\.22,\.006\)/);
  assert.match(fallback,/drawSceneLayers\(sceneLayers\.blend,\.68,\.075,0,\.24,\.008\)/);
  assert.match(fallback,/sceneProject\(beacon\.x-smoothX\*\.075,beacon\.y,beacon\.z\)/);
  assert.match(fallback,/worldX=worldX-4\.2;/);
  assert.match(fallback,/sceneProject\(worldX-smoothX\*\.075,light\.y,light\.z\)/);
  assert.ok(
    fallback.indexOf('smoothX+=(mouseX-smoothX)') <
      fallback.indexOf('drawSceneLayers(sceneLayers.sky'),
    'Canvas pointer smoothing must happen before lower-scene drawing like Edge',
  );
  assert.match(fallback,/maskPath/);
  assert.match(fallback,/destination-out/);
  assert.match(fallback,/makePointBatches/);
  assert.match(fallback,/paintPointBatches/);
  assert.match(fallback,/makeShaderPointSprite/);
  assert.match(fallback,/makeShaderPointSprite\(64,\[97,230,255\],1\.35\)/);
  assert.match(fallback,/makeShaderPointSprite\(32,\[107,230,255\],1\)/);
  assert.match(fallback,/context\.drawImage\(trafficSprite,x-size\*\.5,y-size\*\.5,size,size\)/);
  assert.match(fallback,/canvasDrawMs/);
  assert.match(fallback,/canvasDrawPeakMs/);
  assert.match(fallback,/stage\.dataset\.canvasElapsed=elapsed\.toFixed\(3\)/);
  assert.match(fallback,/stage\.dataset\.headYaw=headYaw\.toFixed\(4\)/);
  assert.match(fallback,/const rawDt=last>0\?Math\.max\(0,\(now-last\)\/1000\):0/);
  assert.match(fallback,/const dt=Math\.min\(\.10,rawDt\)/);
  assert.match(fallback,/elapsed\+=Math\.min\(rawDt,\.25\)/);
  assert.match(fallback,/context\.rotate\(star\.direction>0\?\.22:-\.22\)/);
  assert.match(fallback,/lowerSceneContract='edge-shared-v1'/);
  assert.match(fallback,/async function modelCloud\(surfaceCount\)/);
  assert.match(fallback,/mobile\?8200:22000/);
  assert.match(fallback,/MeshSurfaceSampler/);
  assert.match(fallback,/new MeshSurfaceSampler\(samplingMesh\)\.build\(\)/);
  assert.match(fallback,/sampler\.setRandomGenerator/);
  assert.doesNotMatch(fallback,/parametricPoints/);
  assert.match(fallback,/viewZ=width<650\?5\.3:4\.35/);
  assert.match(fallback,/projectionScale=1\/\(2\*Math\.tan\(39\*Math\.PI\/360\)\*viewZ\)/);
});

test('hero and marketing copy use recovered V15 decisions',()=>{
  const index=read('index.html');
  const content=read('src/content.js');
  assert.doesNotMatch(index,/Aus deiner Aufgabe wird ein präziser Copilot-Prompt/i);
  assert.doesNotMatch(index,/WENIGE KLICKS|EIN PROMPT, DER SITZT|PromptMaster entdecken/);
  assert.match(index,/<div class="hero-center"><h1 class="sr-only">Hol mehr aus Microsoft Copilot heraus\.<\/h1><\/div>/);
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