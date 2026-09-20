import * as THREE from 'three';
import {GLTFLoader} from 'three/addons/loaders/GLTFLoader.js';
import {MeshSurfaceSampler} from 'three/addons/math/MeshSurfaceSampler.js';

const MODEL_URL='/models/head.glb';
const clamp=(value,min,max)=>Math.min(max,Math.max(min,value));
const smoothstep=(edge0,edge1,value)=>{
  const t=clamp((value-edge0)/Math.max(.000001,edge1-edge0),0,1);
  return t*t*(3-2*t);
};

function seeded(seed=0x51f15e){
  let state=seed>>>0;
  return ()=>{
    state=(state*1664525+1013904223)>>>0;
    return state/4294967296;
  };
}

export function createShootingStarCanvas(reverse=false){
  const sprite=document.createElement('canvas');
  sprite.width=256;sprite.height=32;
  const ctx=sprite.getContext('2d',{alpha:true});
  const gradient=ctx.createLinearGradient(0,0,256,0);
  if(reverse){
    gradient.addColorStop(0,'rgba(255,255,255,1)');
    gradient.addColorStop(.06,'rgba(190,245,255,.9)');
    gradient.addColorStop(.28,'rgba(90,205,255,.32)');
    gradient.addColorStop(1,'rgba(40,150,255,0)');
  }else{
    gradient.addColorStop(0,'rgba(40,150,255,0)');
    gradient.addColorStop(.72,'rgba(90,205,255,.32)');
    gradient.addColorStop(.94,'rgba(190,245,255,.9)');
    gradient.addColorStop(1,'rgba(255,255,255,1)');
  }
  ctx.fillStyle=gradient;ctx.fillRect(0,0,256,32);
  const feather=ctx.createLinearGradient(0,0,0,32);
  feather.addColorStop(0,'rgba(255,255,255,0)');
  feather.addColorStop(.5,'rgba(255,255,255,1)');
  feather.addColorStop(1,'rgba(255,255,255,0)');
  ctx.globalCompositeOperation='destination-in';
  ctx.fillStyle=feather;ctx.fillRect(0,0,256,32);
  ctx.globalCompositeOperation='source-over';
  return sprite;
}

export function getShootingStarState(spec,elapsed,pointerX=0){
  const activeTime=elapsed-spec.offset;
  const local=activeTime>=0?activeTime%spec.period:-1;
  const active=local>=0&&local<3.45;
  const progress=active?local/3.45:0;
  const startX=spec.direction>0?-3.25:3.25;
  return {
    active,
    progress,
    x:startX+spec.direction*progress*4.75-pointerX*.035,
    y:spec.y-progress*.76,
    z:spec.z,
    opacity:Math.sin(progress*Math.PI)*spec.opacity,
    width:.72+progress*.48+spec.scaleBias,
    height:.026+progress*.022,
  };
}

export function createLowerSceneData(mobile=false){
  const random=seeded(712367);
  const landscapeCount=mobile?1500:4200;
  const landscape=[];
  for(let i=0;i<landscapeCount;i++){
    const city=i<landscapeCount*.36;
    const mountain=i>=landscapeCount*.36&&i<landscapeCount*.78;
    const x=(random()-.5)*(city?7.4:9.4);
    const edge=Math.min(1,Math.max(0,(Math.abs(x)-.7)/3.9));
    const ridge=-1.08+edge*.68+Math.sin(x*2.25)*.075+Math.sin(x*5.1)*.035;
    const level=city?Math.floor(random()*12):0;
    const y=city
      ? -1.38+level*(.028+random()*.012)
      : mountain
        ? ridge-random()*(.18+edge*.48)
        : -1.3-random()*.3;
    const z=city?-.42-random()*1.9:mountain?-1-random()*2.8:-.25-random()*3.4;
    const cyan=.55+random()*.45;
    const violet=random()>.88;
    landscape.push({
      x,y,z,
      color:violet?[.42*cyan,.38*cyan,cyan]:[.08*cyan,.58*cyan,cyan],
      phase:random()*Math.PI*2,
      size:city?.65+random()*1.15:mountain?.4+random()*.85:.3+random()*.65,
    });
  }

  const blendCount=mobile?850:2400;
  const blend=[];
  for(let i=0;i<blendCount;i++){
    const x=(random()-.5)*9.4;
    const center=1-Math.min(1,Math.abs(x)/4.7);
    const top=-1.18+center*.16;
    blend.push({
      x,
      y:top-random()*(.12+center*.34),
      z:-.5-random()*2.35,
      phase:random()*Math.PI*2,
      size:.45+random()*1.05,
    });
  }

  const beaconCount=mobile?58:150;
  const beacons=[];
  for(let i=0;i<beaconCount;i++){
    beacons.push({
      x:(random()-.5)*9,
      y:-1.43+random()*.42,
      z:-.18-random()*2.25,
      phase:random()*Math.PI*2,
      rate:.42+random()*.64,
    });
  }

  const trafficCount=mobile?16:38;
  const traffic=[];
  for(let i=0;i<trafficCount;i++){
    traffic.push({
      y:-1.39+random()*.3,
      z:-.15-random()*1.4,
      speed:(random()>.5?1:-1)*(.11+random()*.24),
      phase:random()*8.4,
    });
  }

  const skyCount=mobile?105:245;
  const sky=[];
  for(let i=0;i<skyCount;i++){
    sky.push({
      x:(random()-.5)*9.2,
      y:.42+random()*1.32,
      z:-1.2-random()*2.8,
      phase:random()*Math.PI*2,
      size:.35+random()*.85,
    });
  }

  const starHeights=[1.42,1.16,.92,1.3,1.02,.76];
  const starDepths=[-1.25,-1.75,-1.45,-2.05,-1.6,-2.3];
  const shootingStars=Array.from({length:6},(_,index)=>({
    direction:index%2?-1:1,
    offset:.45+index*1.72,
    period:9.1+(index%3)*1.05,
    y:starHeights[index],
    z:starDepths[index],
    opacity:.72-(index%3)*.055,
    scaleBias:(index%3)*.04,
  }));

  return {landscape,blend,beacons,traffic,sky,shootingStars};
}

async function modelCloud(surfaceCount){
  const gltf=await new GLTFLoader().loadAsync(MODEL_URL);
  let mesh;
  gltf.scene.traverse(object=>{if(object.isMesh&&!mesh)mesh=object;});
  if(!mesh)throw new Error('Kopfgeometrie fehlt');

  // This is deliberately the same geometry pipeline as the canonical
  // Chromium/Edge WebGL renderer. Canvas2D differs only at the final raster
  // step, never in model loading, world transforms or point sampling.
  const geometry=mesh.geometry.clone();
  geometry.applyMatrix4(mesh.matrixWorld);
  geometry.center();
  geometry.computeBoundingBox();
  const size=new THREE.Vector3();
  geometry.boundingBox.getSize(size);
  geometry.scale(2.9/size.y,2.9/size.y,2.9/size.y);

  const samplingMesh=new THREE.Mesh(geometry);
  const sampler=new MeshSurfaceSampler(samplingMesh).build();
  let seed=93;
  sampler.setRandomGenerator(()=>{
    seed=(seed*1664525+1013904223)>>>0;
    return seed/4294967296;
  });

  const positions=new Float32Array(surfaceCount*3);
  const colors=new Float32Array(surfaceCount*3);
  const seeds=new Float32Array(surfaceCount);
  const scatter=new Float32Array(surfaceCount*3);
  const p=new THREE.Vector3();
  const n=new THREE.Vector3();

  for(let i=0;i<surfaceCount;i++){
    sampler.sample(p,n);
    positions.set([p.x,p.y,p.z],i*3);
    const front=Math.max(0,Math.min(1,(n.z+.08)/1.08));
    const intensity=.42+front*.58;
    colors.set([.14*intensity,.63*intensity,1*intensity],i*3);
    const pointSeed=(seed=(seed*1664525+1013904223)>>>0)/4294967296;
    const side=(seed=(seed*1664525+1013904223)>>>0)/4294967296-.5;
    const lift=(seed=(seed*1664525+1013904223)>>>0)/4294967296;
    seeds[i]=pointSeed;
    const distance=.065+pointSeed*.22;
    scatter.set([n.x*distance+side*.05,n.y*distance+lift*.065,n.z*distance],i*3);
  }

  const vertexPosition=geometry.getAttribute('position');
  const vertexNormal=geometry.getAttribute('normal');
  const vertexCount=vertexPosition.count;
  const curvature=new Float32Array(vertexCount);
  const neighbors=new Uint16Array(vertexCount);
  const index=geometry.index?.array;
  const accumulate=(a,b)=>{
    const dot=
      vertexNormal.getX(a)*vertexNormal.getX(b)+
      vertexNormal.getY(a)*vertexNormal.getY(b)+
      vertexNormal.getZ(a)*vertexNormal.getZ(b);
    const bend=Math.max(0,1-dot);
    curvature[a]+=bend;
    curvature[b]+=bend;
    neighbors[a]++;
    neighbors[b]++;
  };
  if(index){
    for(let i=0;i<index.length;i+=3){
      const a=index[i],b=index[i+1],d=index[i+2];
      accumulate(a,b);
      accumulate(b,d);
      accumulate(d,a);
    }
  }

  const topologyPositions=new Float32Array(vertexCount*3);
  const topologyColors=new Float32Array(vertexCount*3);
  const topologyDetail=new Float32Array(vertexCount);
  for(let i=0;i<vertexCount;i++){
    const detail=Math.min(1,Math.sqrt((curvature[i]/Math.max(1,neighbors[i]))*13));
    const front=Math.max(0,Math.min(1,(vertexNormal.getZ(i)+.1)/1.1));
    const intensity=.28+front*.43+detail*.46;
    topologyPositions.set(
      [vertexPosition.getX(i),vertexPosition.getY(i),vertexPosition.getZ(i)],
      i*3
    );
    topologyColors.set([.1*intensity,.58*intensity,1*intensity],i*3);
    topologyDetail[i]=detail;
  }

  const depthIndices=index
    ? new index.constructor(index)
    : null;

  return {
    surface:{positions,colors,seeds,scatter},
    topology:{
      positions:topologyPositions,
      colors:topologyColors,
      detail:topologyDetail,
    },
    depth:{
      positions:topologyPositions,
      indices:depthIndices,
      screen:new Float32Array(topologyPositions.length),
    },
  };
}

function rasterizeDepthMesh(depth,project,width,height,cell){
  const cols=Math.max(1,Math.ceil(width/cell));
  const rows=Math.max(1,Math.ceil(height/cell));
  const grid=new Float32Array(cols*rows);
  grid.fill(-1e9);
  const maskPath=new Path2D();
  const vertexCount=depth.positions.length/3;
  for(let i=0;i<vertexCount;i++){
    const o=i*3;
    const p=project(depth.positions[o]*.992,depth.positions[o+1]*.992,depth.positions[o+2]*.992);
    depth.screen[o]=p[0];depth.screen[o+1]=p[1];depth.screen[o+2]=p[2];
  }
  const triangleCount=depth.indices?Math.floor(depth.indices.length/3):Math.floor(vertexCount/3);
  for(let t=0;t<triangleCount;t++){
    const ia=depth.indices?Math.trunc(depth.indices[t*3]):t*3;
    const ib=depth.indices?Math.trunc(depth.indices[t*3+1]):t*3+1;
    const ic=depth.indices?Math.trunc(depth.indices[t*3+2]):t*3+2;
    if(ia<0||ib<0||ic<0||ia>=vertexCount||ib>=vertexCount||ic>=vertexCount)continue;
    const a=ia*3,b=ib*3,d=ic*3;
    const ax=depth.screen[a],ay=depth.screen[a+1],az=depth.screen[a+2];
    const bx=depth.screen[b],by=depth.screen[b+1],bz=depth.screen[b+2];
    const cx=depth.screen[d],cy=depth.screen[d+1],cz=depth.screen[d+2];
    const area=(bx-ax)*(cy-ay)-(by-ay)*(cx-ax);
    if(Math.abs(area)<1e-7)continue;
    maskPath.moveTo(ax,ay);
    maskPath.lineTo(bx,by);
    maskPath.lineTo(cx,cy);
    maskPath.closePath();
    let minX=Math.floor(Math.min(ax,bx,cx)/cell),maxX=Math.floor(Math.max(ax,bx,cx)/cell);
    let minY=Math.floor(Math.min(ay,by,cy)/cell),maxY=Math.floor(Math.max(ay,by,cy)/cell);
    if(maxX<0||maxY<0||minX>=cols||minY>=rows)continue;
    minX=clamp(minX,0,cols-1);maxX=clamp(maxX,0,cols-1);
    minY=clamp(minY,0,rows-1);maxY=clamp(maxY,0,rows-1);
    for(let gy=minY;gy<=maxY;gy++){
      const py=(gy+.5)*cell;
      for(let gx=minX;gx<=maxX;gx++){
        const px=(gx+.5)*cell;
        const wa=((bx-px)*(cy-py)-(by-py)*(cx-px))/area;
        const wb=((cx-px)*(ay-py)-(cy-py)*(ax-px))/area;
        const wc=1-wa-wb;
        if(wa<-.001||wb<-.001||wc<-.001)continue;
        const rz=wa*az+wb*bz+wc*cz;
        const index=gy*cols+gx;
        if(rz>grid[index])grid[index]=rz;
      }
    }
  }
  return {grid,cols,rows,maskPath};
}
export async function initCanvasHead({sourceCanvas,stage,fallback}){
  sourceCanvas.hidden=true;
  fallback.hidden=false;
  fallback.classList.add('canvas-fallback');
  fallback.dataset.renderer='canvas2d';
  delete fallback.dataset.ready;
  stage.dataset.headRenderer='canvas2d';
  delete stage.dataset.headReady;
  fallback.replaceChildren();

  const canvas=document.createElement('canvas');
  canvas.className='head-fallback-canvas';
  // Empirically align Canvas2D luminance with the canonical Edge/WebGL point
  // energy without changing geometry, alpha coverage or the base scene.
  canvas.style.filter='brightness(1.04)';
  canvas.setAttribute('aria-hidden','true');
  fallback.append(canvas);
  const context=canvas.getContext('2d',{alpha:true});
  if(!context){
    fallback.classList.remove('canvas-fallback');
    fallback.hidden=true;
    stage.dataset.headRenderer='none';
    stage.dataset.headReady='1';
    return ()=>{};
  }

  const mobile=matchMedia('(max-width:800px)').matches;
  let cloud;
  try{cloud=await modelCloud(mobile?8200:22000);}
  catch(error){
    console.error('Originaler PromptMaster-Kopf konnte nicht geladen werden; kein Ersatzkopf wird erzeugt.',error);
    fallback.classList.remove('canvas-fallback');
    fallback.hidden=true;
    stage.dataset.headRenderer='original-unavailable';
    stage.dataset.headReady='1';
    return ()=>{};
  }

  // WebGL point shaders use a radial alpha falloff, while Canvas2D fillRect would
  // otherwise paint the whole point quad at full alpha. The fallback therefore
  // uses smaller quads and shader-energy-equivalent alpha so Firefox/no-WebGL
  // stays visually aligned with the canonical Chromium/Edge composition.
  // Canvas2D mirrors the animated lower scene of the WebGL edition instead of
  // degrading Firefox/VDI clients to a head-only fallback.
  const sceneData=createLowerSceneData(mobile);
    stage.dataset.lowerSceneContract='edge-shared-v1';
  const groundParticles=sceneData.landscape;
  const blendParticles=sceneData.blend;
  const beacons=sceneData.beacons;
  const traffic=sceneData.traffic;
  const skyLights=sceneData.sky;
  const shootingStars=sceneData.shootingStars;

  const makeShaderPointSprite=(size,[r,g,b],exponent)=>{
    const sprite=document.createElement('canvas');
    sprite.width=size;sprite.height=size;
    const ctx=sprite.getContext('2d',{alpha:true});
    const image=ctx.createImageData(size,size);
    const radius=size*.5;
    for(let py=0;py<size;py++){
      for(let px=0;px<size;px++){
        const dx=(px+.5-radius)/radius;
        const dy=(py+.5-radius)/radius;
        const distance=Math.hypot(dx,dy);
        const alpha=distance<=1?Math.pow(1-distance,exponent):0;
        const offset=(py*size+px)*4;
        image.data[offset]=r;
        image.data[offset+1]=g;
        image.data[offset+2]=b;
        image.data[offset+3]=Math.round(alpha*255);
      }
    }
    ctx.putImageData(image,0,0);
    return sprite;
  };
  // Exact Canvas equivalents of the WebGL fragment point profiles.
  const beaconSprite=makeShaderPointSprite(64,[97,230,255],1.35);
  const trafficSprite=makeShaderPointSprite(32,[107,230,255],1);
  const shootingStarLtr=createShootingStarCanvas(false);
  const shootingStarRtl=createShootingStarCanvas(true);

  const reduced=matchMedia('(prefers-reduced-motion:reduce)');
  let paused=reduced.matches,disposed=false,visible=true,last=0,lastFrame=0,elapsed=0,mouseX=0,mouseY=0,smoothX=0,smoothY=0,lastPointerX=0,lastPointerY=0,hasPointer=false,cursorEnergy=0,dissolve=0,headYaw=0,headPitch=0,pointPower=1,topologyPower=1,edition='',raf=0,width=1,height=1,dpr=1;
  let sceneLayers={landscape:[],blend:[],sky:[]};
  let cachedDepth=null,cachedDepthYaw=Infinity,cachedDepthPitch=Infinity,cachedDepthAt=-Infinity;
  let canvasFrameCount=0,canvasSteadyPeakMs=0;

  const makePointBatches=()=>Array.from({length:24},()=>new Path2D());
  const addPointToBatch=(batches,x,y,size,intensity,alpha)=>{
    const ib=clamp(Math.floor(clamp(intensity,0,1)*6),0,5);
    const ab=clamp(Math.floor(clamp(alpha,0,1)*4),0,3);
    batches[ab*6+ib].rect(x-size*.5,y-size*.5,size,size);
  };
  const paintPointBatches=(batches,rRatio,gRatio)=>{
    for(let ab=0;ab<4;ab++){
      const alpha=(ab+.65)/4;
      for(let ib=0;ib<6;ib++){
        const intensity=(ib+.58)/6;
        const r=Math.round(clamp(rRatio*intensity,0,1)*255);
        const g=Math.round(clamp(gRatio*intensity,0,1)*255);
        const b=Math.round(clamp(intensity,0,1)*255);
        context.fillStyle=`rgba(${r},${g},${b},${alpha})`;
        context.fill(batches[ab*6+ib]);
      }
    }
  };

  const sceneProject=(x,y,z)=>{
    const viewZ=width<650?5.3:4.35;
    const base=height/(2*Math.tan(39*Math.PI/360)*viewZ);
    const depth=viewZ-z;
    const perspective=viewZ/depth;
    return [
      width*.5+x*base*perspective,
      height*.5-(y-.06)*base*perspective,
      depth,
      perspective,
      base*perspective,
    ];
  };

  const createSceneLayer=()=>{
    const layer=document.createElement('canvas');
    const layerScale=Math.min(1,Math.max(.6,dpr*.5));
    layer.width=Math.max(1,Math.round(width*layerScale));
    layer.height=Math.max(1,Math.round(height*layerScale));
    const layerContext=layer.getContext('2d',{alpha:true});
    layerContext.setTransform(layerScale,0,0,layerScale,0,0);
    layerContext.globalCompositeOperation='lighter';
    return [layer,layerContext,{scaleSum:0,count:0}];
  };

  const rebuildSceneLayers=()=>{
    const LAND_BUCKETS=6,BLEND_BUCKETS=4,SKY_BUCKETS=4;
    sceneLayers={
      landscape:Array.from({length:LAND_BUCKETS},createSceneLayer),
      blend:Array.from({length:BLEND_BUCKETS},createSceneLayer),
      sky:Array.from({length:SKY_BUCKETS},createSceneLayer),
    };

    for(const point of groundParticles){
      const bucket=Math.floor((point.phase/(Math.PI*2))*LAND_BUCKETS)%LAND_BUCKETS;
      const [,ctx,meta]=sceneLayers.landscape[bucket];
      const [x,y,depth,,worldPixelScale]=sceneProject(point.x,point.y,point.z);
      if(depth<=.1||x<-8||x>width+8||y<-8||y>height+8)continue;
      meta.scaleSum+=worldPixelScale;meta.count++;
      const pointScale=4.5/depth;
      const size=Math.max(.35,(1.15+point.size*1.5+.36)*pointScale);
      const [r,g,b]=point.color.map(value=>Math.round(value*255));
      ctx.fillStyle=`rgba(${r},${g},${b},.72)`;
      ctx.fillRect(x,y,size,size);
    }

    for(const point of blendParticles){
      const bucket=Math.floor((point.phase/(Math.PI*2))*BLEND_BUCKETS)%BLEND_BUCKETS;
      const [,ctx,meta]=sceneLayers.blend[bucket];
      const [x,y,depth,,worldPixelScale]=sceneProject(point.x,point.y,point.z);
      if(depth<=.1||x<-8||x>width+8||y<-8||y>height+8)continue;
      meta.scaleSum+=worldPixelScale;meta.count++;
      const pointScale=4.5/depth;
      const size=Math.max(.3,(1.05+point.size*1.35+.35)*pointScale);
      ctx.fillStyle='rgba(31,168,255,.58)';
      ctx.fillRect(x,y,size,size);
    }

    for(const point of skyLights){
      const bucket=Math.floor((point.phase/(Math.PI*2))*SKY_BUCKETS)%SKY_BUCKETS;
      const [,ctx,meta]=sceneLayers.sky[bucket];
      const [x,y,depth,,worldPixelScale]=sceneProject(point.x,point.y,point.z);
      if(depth<=.1||x<-8||x>width+8||y<-8||y>height+8)continue;
      meta.scaleSum+=worldPixelScale;meta.count++;
      const pointScale=4.5/depth;
      const size=Math.max(.3,(.9+point.size*1.55+.9)*pointScale);
      ctx.fillStyle='rgba(132,214,255,.78)';
      ctx.fillRect(x,y,size,size);
    }
  };

  const drawSceneLayers=(
    layers,
    baseRate,
    worldShiftX,
    pointerWorldShiftY=0,
    bobRate=0,
    bobWorldAmplitude=0
  )=>{
    const count=layers.length;
    for(let index=0;index<count;index++){
      const phase=index/count*Math.PI*2;
      const pulse=.5+.5*Math.sin(elapsed*baseRate+phase);
      const [layer,,meta]=layers[index];
      const worldPixelScale=meta.count?meta.scaleSum/meta.count:height*.22;
      const offsetX=-smoothX*worldShiftX*worldPixelScale;
      const pointerOffsetY=-smoothY*pointerWorldShiftY*worldPixelScale;
      const bobOffsetY=bobWorldAmplitude
        ? -Math.sin(elapsed*bobRate+phase)*bobWorldAmplitude*worldPixelScale
        : 0;
      context.globalAlpha=.34+pulse*.66;
      context.drawImage(layer,offsetX,pointerOffsetY+bobOffsetY,width,height);
    }
    context.globalAlpha=1;
  };
  const resize=()=>{
    const rect=stage.getBoundingClientRect();
    width=Math.max(1,Math.round(rect.width));
    height=Math.max(1,Math.round(rect.height));
    dpr=1;
    canvas.width=Math.round(width*dpr);
    canvas.height=Math.round(height*dpr);
    canvas.style.width=width+'px';
    canvas.style.height=height+'px';
    context.setTransform(dpr,0,0,dpr,0,0);
    rebuildSceneLayers();
    draw(performance.now());
  };

  function draw(now){
    if(disposed)return;
    const drawStarted=performance.now();
    const rawDt=last>0?Math.max(0,(now-last)/1000):0;
    const dt=Math.min(.10,rawDt);
    last=now;
    // Keep animation phase tied to wall-clock time. The old code added only
    // the clamped dt, so a slow Canvas frame also slowed the entire head,
    // beacons and shooting stars and produced the observed millimetre crawl.
    elapsed+=Math.min(rawDt,.25);
    // Edge updates smoothed pointer input before moving any scene object.
    // Keep the fallback in the same frame order so ground/stars never lag a
    // frame behind the head.
    const inputFollow=3.15;
    smoothX+=(mouseX-smoothX)*Math.min(1,dt*inputFollow);
    smoothY+=(mouseY-smoothY)*Math.min(1,dt*inputFollow);
    context.clearRect(0,0,width,height);
    const glow=context.createRadialGradient(width*.5,height*.42,0,width*.5,height*.42,Math.min(width,height)*.38);
    glow.addColorStop(0,'rgba(30,155,255,.12)');
    glow.addColorStop(.45,'rgba(13,95,180,.05)');
    glow.addColorStop(1,'rgba(0,30,80,0)');
    context.fillStyle=glow;context.fillRect(0,0,width,height);
    context.globalCompositeOperation='lighter';

    // Draw the thousands of weak Edge-equivalent points from cached phase
    // layers. Positions remain exact; only their shimmer is grouped into phase
    // buckets so Firefox does not repaint 6,000+ individual quads every frame.
    drawSceneLayers(sceneLayers.sky,1.34,.025);
    drawSceneLayers(sceneLayers.landscape,.72,.075,.018,.22,.006);
    drawSceneLayers(sceneLayers.blend,.68,.075,0,.24,.008);

    // Edge/WebGL shooting-star contract: same six trails, schedule, direction,
    // height, depth, duration and scale progression.
    let activeStarProbe='';
    for(let starIndex=0;starIndex<shootingStars.length;starIndex++){
      const star=shootingStars[starIndex];
      const state=getShootingStarState(star,elapsed,smoothX);
      if(!state.active)continue;
      const {progress}=state;
      const [x,y,depth,,worldPixelScale]=sceneProject(state.x,state.y,state.z);
      if(depth<=.1)continue;
      const trailWidth=state.width*worldPixelScale;
      const trailHeight=Math.max(1,state.height*worldPixelScale);
      const alpha=state.opacity;
      if(!activeStarProbe){
        activeStarProbe=[starIndex,x,y,star.direction,progress].map(value=>
          typeof value==='number'?value.toFixed(3):value
        ).join(',');
      }
      context.save();
      context.globalAlpha=alpha;
      context.translate(x,y);
      context.rotate(star.direction>0?.22:-.22);
      context.drawImage(
        star.direction>0?shootingStarLtr:shootingStarRtl,
        -trailWidth*.5,-trailHeight*.5,trailWidth,trailHeight
      );
      context.restore();
    }
    stage.dataset.starProbe=activeStarProbe;

    // Strong beacons use the exact same 3D positions/phases/rates as Edge.
    for(const beacon of beacons){
      const wave=.5+.5*Math.sin(elapsed*(1.05+beacon.rate)+beacon.phase);
      const flash=Math.pow(wave,7);
      const [x,y,depth]=sceneProject(beacon.x-smoothX*.075,beacon.y,beacon.z);
      if(depth<=.1)continue;
      const pointScale=4.5/depth;
      const diameter=Math.max(1.6,(2.8+flash*8.5)*pointScale);
      context.save();
      context.globalAlpha=Math.min(1,.14+flash*1.28);
      context.drawImage(beaconSprite,x-diameter*.5,y-diameter*.5,diameter,diameter);
      context.restore();
    }

    // Moving traffic lights also follow Edge's world-space lane coordinates.
    for(const light of traffic){
      let worldX=(light.phase+elapsed*light.speed+4.2)%8.4;
      if(worldX<0)worldX+=8.4;
      worldX=worldX-4.2;
      const [x,y,depth]=sceneProject(worldX-smoothX*.075,light.y,light.z);
      if(depth<=.1)continue;
      const alpha=.48+.35*Math.sin(elapsed*1.7+light.phase);
      const size=Math.max(.8,2.5*(4.5/depth));
      context.save();
      context.globalAlpha=alpha;
      context.drawImage(trafficSprite,x-size*.5,y-size*.5,size,size);
      context.restore();
    }

    const yawTarget=edition==='free'?-.22:edition==='pro'?.22:smoothX*.3;
    headYaw+=(yawTarget-headYaw)*Math.min(1,dt*3);
    headPitch+=(smoothY*.18-headPitch)*Math.min(1,dt*3);
    const powerTarget=edition==='pro'?1.28:edition==='free'?.7:1;
    pointPower+=(powerTarget-pointPower)*Math.min(1,dt*3);
    topologyPower+=(powerTarget-topologyPower)*Math.min(1,dt*3);
    cursorEnergy=Math.max(0,cursorEnergy-dt*.75);
    const dissolveTarget=Math.min(.58,Math.max(edition?.42:.055,cursorEnergy*.5));
    const dissolveSpeed=dissolveTarget<dissolve?6:1.75;
    dissolve+=(dissolveTarget-dissolve)*Math.min(1,dt*dissolveSpeed);

    const yaw=headYaw,pitch=headPitch;
    const cy=Math.cos(yaw),sy=Math.sin(yaw),cp=Math.cos(pitch),sp=Math.sin(pitch);
    const viewZ=width<650?5.3:4.35;
    const projectionScale=1/(2*Math.tan(39*Math.PI/360)*viewZ);
    const base=height*projectionScale;
    const centerX=width*.5;
    const centerY=height*.5;
    const cameraY=.06;
    const bob=Math.sin(elapsed*.42)*.008;
    let headMinX=Infinity,headMinY=Infinity,headMaxX=-Infinity,headMaxY=-Infinity;

    const project=(x,y,z)=>{
      const rx=x*cy+z*sy;
      const rz=-x*sy+z*cy;
      const ry=y*cp-rz*sp+bob;
      const rz2=y*sp+rz*cp;
      const depth=viewZ-rz2;
      const perspective=viewZ/depth;
      return [
        centerX+rx*base*perspective,
        centerY-(ry-cameraY)*base*perspective,
        rz2,
        depth,
        perspective,
      ];
    };
    context.shadowBlur=0;
    context.globalCompositeOperation='lighter';

    const surface=cloud.surface;
    // Match Three.js: the original GLB triangle mesh is rendered first as a
    // colorless depth occluder at scale .992. Rebuild the CPU depth mesh only
    // when the head orientation changed materially; the Edge renderer keeps
    // this on the GPU, while re-rasterizing every Canvas frame caused the
    // observed multi-hundred-millisecond stalls.
    const depthCell=6;
    if(
      !cachedDepth
      || Math.abs(yaw-cachedDepthYaw)>.018
      || Math.abs(pitch-cachedDepthPitch)>.014
      || elapsed-cachedDepthAt>.14
    ){
      cachedDepth=rasterizeDepthMesh(cloud.depth,project,width,height,depthCell);
      cachedDepthYaw=yaw;
      cachedDepthPitch=pitch;
      cachedDepthAt=elapsed;
    }
    const depthRaster=cachedDepth;
    const depthCols=depthRaster.cols;
    const depthRows=depthRaster.rows;
    const depthGrid=depthRaster.grid;

    // WebGL's invisible depth mesh blocks stars and ground lights behind the
    // head. Canvas point gaps previously let those effects shine through and
    // look as if they were in front of the face/neck.
    context.save();
    context.globalCompositeOperation='destination-out';
    context.globalAlpha=1;
    context.fillStyle='#000';
    context.fill(depthRaster.maskPath);
    context.restore();
    stage.dataset.canvasOcclusion='head-silhouette-v1';
    context.globalCompositeOperation='lighter';

    const surfaceBatches=makePointBatches();
    for(let i=0;i<surface.seeds.length;i++){
      const o=i*3;
      const x=surface.positions[o],y=surface.positions[o+1],z=surface.positions[o+2];
      const vertical=(y+1.45)/2.9;
      const threshold=surface.seeds[i]*.61+vertical*.13;
      let released=smoothstep(threshold-.14,threshold+.08,dissolve);
      const shimmer=.5+.5*Math.sin(elapsed*(.48+surface.seeds[i]*.32)+surface.seeds[i]*23);
      const shoulderFade=1-smoothstep(-1.28,-.10,y);
      released=Math.max(released,shoulderFade*(.92+.08*shimmer));
      const spread=released*(.78+.34*shimmer)+shoulderFade*1.95;
      let px=x+surface.scatter[o]*spread;
      let py=y+surface.scatter[o+1]*spread;
      let pz=z+surface.scatter[o+2]*spread;
      px+=Math.sign(x)*(.12+Math.abs(x)*.16)*shoulderFade;
      py-=.30*shoulderFade;
      pz-=.08*shoulderFade;
      const alpha=(1-released*(.12+surface.seeds[i]*.22))*(1-shoulderFade*.995);
      if(alpha<=.006)continue;

      const [sx2,sy2,rz2,depth]=project(px,py,pz);
      if(depth<=.1||sx2<-5||sx2>width+5||sy2<-5||sy2>height+5)continue;
      const cellX=clamp(Math.floor(sx2/depthCell),0,depthCols-1);
      const cellY=clamp(Math.floor(sy2/depthCell),0,depthRows-1);
      const depthIndex=cellY*depthCols+cellX;
      if(depthGrid[depthIndex]>-1e8&&rz2<depthGrid[depthIndex]-.025)continue;
      const pointSize=(1.9+pointPower*.43+released*.9)*(4.5/depth);
      const colorBoost=1.42+pointPower*.42;
      const intensity=clamp(surface.colors[o+2]*colorBoost,0,1);
      headMinX=Math.min(headMinX,sx2);headMaxX=Math.max(headMaxX,sx2);
      headMinY=Math.min(headMinY,sy2);headMaxY=Math.max(headMaxY,sy2);
      const renderSize=Math.max(.465,Math.min(1.50,pointSize*.538));
      addPointToBatch(surfaceBatches,sx2,sy2,renderSize,intensity,clamp(alpha*.44,0,1));
    }
    paintPointBatches(surfaceBatches,.14,.63);

    const topology=cloud.topology;
    const topologyBatches=makePointBatches();
    for(let i=0;i<topology.detail.length;i++){
      const o=i*3;
      const x=topology.positions[o],y=topology.positions[o+1],z=topology.positions[o+2];
      const shoulderFade=1-smoothstep(-1.20,-.08,y);
      const px=x+Math.sign(x)*(.10+Math.abs(x)*.12)*shoulderFade;
      const py=y-.22*shoulderFade;
      const pz=z-.05*shoulderFade;
      const alpha=(.62+topology.detail[i]*.3)*(1-shoulderFade*.997);
      if(alpha<=.006)continue;
      const [sx2,sy2,rz2,depth]=project(px,py,pz);
      if(depth<=.1||sx2<-5||sx2>width+5||sy2<-5||sy2>height+5)continue;
      const cellX=clamp(Math.floor(sx2/depthCell),0,depthCols-1);
      const cellY=clamp(Math.floor(sy2/depthCell),0,depthRows-1);
      const depthIndex=cellY*depthCols+cellX;
      const nearest=depthGrid[depthIndex];
      if(nearest>-1e8&&rz2<nearest-.025)continue;
      headMinX=Math.min(headMinX,sx2);headMaxX=Math.max(headMaxX,sx2);
      headMinY=Math.min(headMinY,sy2);headMaxY=Math.max(headMaxY,sy2);
      const size=(1.55+topology.detail[i]*1.75+topologyPower*.18)*(4.5/depth);
      const detailBoost=1+topology.detail[i]*.72;
      const intensity=clamp(topology.colors[o+2]*detailBoost*1.55,0,1);
      const renderSize=Math.max(.465,Math.min(1.71,size*.518));
      addPointToBatch(topologyBatches,sx2,sy2,renderSize,intensity,clamp(alpha*.40,0,1));
    }
    paintPointBatches(topologyBatches,.10,.58);

    if(Number.isFinite(headMinX)){
      stage.dataset.headBounds=[headMinX,headMinY,headMaxX,headMaxY].map(v=>Math.round(v)).join(',');
    }

    const eyePulse=1+Math.sin(elapsed*1.8)*.025+(edition==='pro'?.055:0);
    const eyeSpecs=[[-.245,.6,.755],[.18,.6,.75]];
    const renderedEyes=[];
    for(let eyeIndex=0;eyeIndex<eyeSpecs.length;eyeIndex++){
      const [x,y,z]=eyeSpecs[eyeIndex];
      const projected=project(x,y,z);
      const eyeX=projected[0];
      const eyeY=projected[1];
      const perspective=projected[4];
      renderedEyes.push(Math.round(eyeX),Math.round(eyeY));
      const haloRadius=.135*base*perspective*eyePulse;
      const halo=context.createRadialGradient(eyeX,eyeY,0,eyeX,eyeY,haloRadius);
      halo.addColorStop(0,'rgba(255,255,255,.56)');
      halo.addColorStop(.08,'rgba(181,246,255,.56)');
      halo.addColorStop(.23,'rgba(55,197,255,.55)');
      halo.addColorStop(.52,'rgba(0,111,255,.19)');
      halo.addColorStop(1,'rgba(0,80,255,0)');
      context.fillStyle=halo;
      context.beginPath();context.arc(eyeX,eyeY,haloRadius,0,Math.PI*2);context.fill();

      const coreRadius=.036*base*perspective*eyePulse;
      const core=context.createRadialGradient(eyeX,eyeY,0,eyeX,eyeY,coreRadius);
      core.addColorStop(0,'rgba(255,255,255,.80)');
      core.addColorStop(.18,'rgba(181,246,255,.78)');
      core.addColorStop(.55,'rgba(55,197,255,.42)');
      core.addColorStop(1,'rgba(0,111,255,0)');
      context.fillStyle=core;
      context.beginPath();context.arc(eyeX,eyeY,coreRadius,0,Math.PI*2);context.fill();
    }
    stage.dataset.eyeAnchors=renderedEyes.join(',');
    context.shadowBlur=0;
    context.globalCompositeOperation='source-over';
    const drawMs=performance.now()-drawStarted;
    canvasFrameCount++;
    if(canvasFrameCount>5)canvasSteadyPeakMs=Math.max(canvasSteadyPeakMs,drawMs);
    stage.dataset.canvasDrawMs=drawMs.toFixed(1);
    stage.dataset.canvasDrawPeakMs=canvasSteadyPeakMs.toFixed(1);
    stage.dataset.canvasFrames=String(canvasFrameCount);
  }

  function loop(now){
    if(disposed||paused||!visible||document.hidden){raf=0;return;}
    if(now-lastFrame>=24){lastFrame=now;draw(now);}
    raf=requestAnimationFrame(loop);
  }
  function sync(){
    if(raf){cancelAnimationFrame(raf);raf=0;}
    draw(performance.now());
    if(!paused&&visible&&!document.hidden)raf=requestAnimationFrame(loop);
  }

  const onPointer=(event)=>{
    const nextX=clamp(event.clientX/Math.max(1,innerWidth)*2-1,-1,1);
    const nextY=clamp(event.clientY/Math.max(1,innerHeight)*2-1,-1,1);
    if(hasPointer)cursorEnergy=Math.min(1,cursorEnergy+Math.hypot(nextX-lastPointerX,nextY-lastPointerY)*.34);
    else hasPointer=true;
    lastPointerX=nextX;lastPointerY=nextY;mouseX=nextX;mouseY=nextY;
  };
  const onVisibility=()=>sync();
  const onReduced=()=>{paused=reduced.matches;sync();};
  const controls=new AbortController();
  document.querySelectorAll('[data-edition]').forEach(card=>{
    for(const event of ['pointerenter','focusin'])card.addEventListener(event,()=>{edition=card.dataset.edition},{signal:controls.signal});
    for(const event of ['pointerleave','focusout'])card.addEventListener(event,()=>{edition=''},{signal:controls.signal});
  });
  window.addEventListener('pointermove',onPointer,{passive:true});
  document.addEventListener('visibilitychange',onVisibility);
  reduced.addEventListener('change',onReduced);
  const observer=new IntersectionObserver(([entry])=>{visible=entry.isIntersecting;sync();},{rootMargin:'80px'});
  observer.observe(fallback);
  const resizeObserver=new ResizeObserver(resize);resizeObserver.observe(stage);
  resize();sync();
  fallback.dataset.ready='1';
  stage.dataset.headReady='1';

  const cleanup=()=>{
    if(disposed)return;
    disposed=true;
    if(raf)cancelAnimationFrame(raf);
    observer.disconnect();resizeObserver.disconnect();controls.abort();
    window.removeEventListener('pointermove',onPointer);
    document.removeEventListener('visibilitychange',onVisibility);
    reduced.removeEventListener('change',onReduced);
  };
  window.addEventListener('pagehide',cleanup,{once:true});
  return cleanup;
}
