const MODEL_URL='/models/head.glb';
const clamp=(value,min,max)=>Math.min(max,Math.max(min,value));

function seeded(seed=0x51f15e){
  let state=seed>>>0;
  return ()=>{
    state=(state*1664525+1013904223)>>>0;
    return state/4294967296;
  };
}

function componentsFor(type){
  return {SCALAR:1,VEC2:2,VEC3:3,VEC4:4,MAT2:4,MAT3:9,MAT4:16}[type]||0;
}

function componentInfo(type){
  return {
    5120:[Int8Array,1],
    5121:[Uint8Array,1],
    5122:[Int16Array,2],
    5123:[Uint16Array,2],
    5125:[Uint32Array,4],
    5126:[Float32Array,4],
  }[type]||null;
}

function parseGlb(buffer){
  const view=new DataView(buffer);
  if(view.byteLength<20||view.getUint32(0,true)!==0x46546c67)throw new Error('Ungültiges GLB');
  let offset=12,json=null,bin=null;
  while(offset+8<=view.byteLength){
    const length=view.getUint32(offset,true);
    const type=view.getUint32(offset+4,true);
    offset+=8;
    if(offset+length>view.byteLength)throw new Error('Beschädigtes GLB');
    if(type===0x4e4f534a)json=JSON.parse(new TextDecoder().decode(new Uint8Array(buffer,offset,length)).replaceAll(String.fromCharCode(0),'').trimEnd());
    if(type===0x004e4942)bin=new Uint8Array(buffer,offset,length);
    offset+=length;
  }
  if(!json||!bin)throw new Error('GLB-Chunks fehlen');
  return {json,bin};
}

function readAccessor(gltf,bin,index){
  const accessor=gltf.accessors?.[index];
  if(!accessor||accessor.bufferView===undefined||accessor.sparse)throw new Error('Nicht unterstützter GLB-Accessor');
  const bufferView=gltf.bufferViews?.[accessor.bufferView];
  if(!bufferView)throw new Error('GLB-BufferView fehlt');
  const info=componentInfo(accessor.componentType);
  const components=componentsFor(accessor.type);
  if(!info||!components)throw new Error('Nicht unterstütztes GLB-Datenformat');
  const [,bytes]=info;
  const stride=bufferView.byteStride||components*bytes;
  const start=(bufferView.byteOffset||0)+(accessor.byteOffset||0);
  const data=new DataView(bin.buffer,bin.byteOffset,bin.byteLength);
  const getter={
    5120:'getInt8',5121:'getUint8',5122:'getInt16',5123:'getUint16',5125:'getUint32',5126:'getFloat32',
  }[accessor.componentType];
  const little=bytes>1;
  const out=new Float32Array(accessor.count*components);
  for(let i=0;i<accessor.count;i++){
    const row=start+i*stride;
    for(let c=0;c<components;c++)out[i*components+c]=data[getter](row+c*bytes,little);
  }
  return {data:out,count:accessor.count,components};
}

function findPrimitive(gltf){
  for(let meshIndex=0;meshIndex<(gltf.meshes||[]).length;meshIndex++){
    for(const primitive of gltf.meshes[meshIndex].primitives||[]){
      if(primitive.attributes?.POSITION!==undefined)return {meshIndex,primitive};
    }
  }
  throw new Error('Kopfgeometrie fehlt');
}

function normalizePoints(raw){
  let minX=Infinity,minY=Infinity,minZ=Infinity,maxX=-Infinity,maxY=-Infinity,maxZ=-Infinity;
  for(let i=0;i<raw.length;i+=3){
    const x=raw[i],y=raw[i+1],z=raw[i+2];
    if(x<minX)minX=x;if(x>maxX)maxX=x;
    if(y<minY)minY=y;if(y>maxY)maxY=y;
    if(z<minZ)minZ=z;if(z>maxZ)maxZ=z;
  }
  const cx=(minX+maxX)/2,cy=(minY+maxY)/2,cz=(minZ+maxZ)/2;
  const scale=2.9/Math.max(.0001,maxY-minY);
  const out=new Float32Array(raw.length);
  for(let i=0;i<raw.length;i+=3){
    out[i]=(raw[i]-cx)*scale;
    out[i+1]=(raw[i+1]-cy)*scale;
    out[i+2]=(raw[i+2]-cz)*scale;
  }
  return out;
}

function sampleSurfacePoints(vertices,indexAccessor,count){
  const indices=indexAccessor?.data||null;
  const vertexCount=vertices.length/3;
  const triangleCount=indices?Math.floor(indices.length/3):Math.floor(vertexCount/3);
  if(!triangleCount)return samplePoints(vertices,count);

  const cumulative=new Float64Array(triangleCount);
  let totalArea=0;
  for(let t=0;t<triangleCount;t++){
    const ia=indices?Math.trunc(indices[t*3]):t*3;
    const ib=indices?Math.trunc(indices[t*3+1]):t*3+1;
    const ic=indices?Math.trunc(indices[t*3+2]):t*3+2;
    if(ia<0||ib<0||ic<0||ia>=vertexCount||ib>=vertexCount||ic>=vertexCount){
      cumulative[t]=totalArea;continue;
    }
    const a=ia*3,b=ib*3,d=ic*3;
    const abx=vertices[b]-vertices[a],aby=vertices[b+1]-vertices[a+1],abz=vertices[b+2]-vertices[a+2];
    const acx=vertices[d]-vertices[a],acy=vertices[d+1]-vertices[a+1],acz=vertices[d+2]-vertices[a+2];
    const cx=aby*acz-abz*acy,cy=abz*acx-abx*acz,cz=abx*acy-aby*acx;
    totalArea+=Math.sqrt(cx*cx+cy*cy+cz*cz)*.5;
    cumulative[t]=totalArea;
  }
  if(totalArea<=1e-8)return samplePoints(vertices,count);

  const random=seeded(93);
  const out=new Float32Array(count*3);
  for(let i=0;i<count;i++){
    const target=random()*totalArea;
    let lo=0,hi=triangleCount-1;
    while(lo<hi){
      const mid=(lo+hi)>>1;
      if(cumulative[mid]<target)lo=mid+1;else hi=mid;
    }
    const t=lo;
    const ia=indices?Math.trunc(indices[t*3]):t*3;
    const ib=indices?Math.trunc(indices[t*3+1]):t*3+1;
    const ic=indices?Math.trunc(indices[t*3+2]):t*3+2;
    const a=ia*3,b=ib*3,d=ic*3;
    const root=Math.sqrt(random()),mix=random();
    const wa=1-root,wb=root*(1-mix),wc=root*mix;
    const o=i*3;
    out[o]=vertices[a]*wa+vertices[b]*wb+vertices[d]*wc;
    out[o+1]=vertices[a+1]*wa+vertices[b+1]*wb+vertices[d+1]*wc;
    out[o+2]=vertices[a+2]*wa+vertices[b+2]*wb+vertices[d+2]*wc;
  }
  return out;
}

function mergePoints(surface,topology){
  const out=new Float32Array(surface.length+topology.length);
  out.set(surface,0);out.set(topology,surface.length);
  return out;
}

async function modelPoints(surfaceCount,topologyCount){
  const response=await fetch(MODEL_URL,{cache:'force-cache'});
  if(!response.ok)throw new Error('Kopfmodell nicht verfügbar');
  const {json,bin}=parseGlb(await response.arrayBuffer());
  const {primitive}=findPrimitive(json);
  if(primitive.mode!==undefined&&primitive.mode!==4)throw new Error('Kopfmodell verwendet keinen TRIANGLES-Modus');
  const positions=readAccessor(json,bin,primitive.attributes.POSITION);
  if(positions.components!==3||positions.count<100)throw new Error('Kopfmodell enthält zu wenig Geometrie');
  const normalized=normalizePoints(positions.data);
  const indices=primitive.indices===undefined?null:readAccessor(json,bin,primitive.indices);
  const surface=sampleSurfacePoints(normalized,indices,surfaceCount);
  const topology=samplePoints(normalized,topologyCount);
  return mergePoints(surface,topology);
}

function parametricPoints(){
  const random=seeded();
  const count=7200;
  const out=new Float32Array((count+1100)*3);
  let cursor=0;
  for(let i=0;i<count;i++){
    const a=random()*Math.PI*2;
    const radius=Math.sqrt(random());
    let x=Math.cos(a)*radius*.78;
    const y=Math.sin(a)*radius*1.32+.12;
    const jaw=clamp((y+.95)/.75,0,1);
    x*=.72+.28*jaw;
    const z=Math.sqrt(Math.max(0,1-(x/.82)**2-((y-.12)/1.42)**2))*(random()>.5?1:-1)*.45;
    out[cursor++]=x;out[cursor++]=y;out[cursor++]=z;
  }
  for(let i=0;i<1100;i++){
    const side=random()>.5?1:-1;
    const x=side*(.24+random()*1.35);
    const y=-1.18-random()*.5;
    const z=(random()-.5)*.5;
    out[cursor++]=x;out[cursor++]=y;out[cursor++]=z;
  }
  return out;
}

function samplePoints(points,maxPoints=12500){
  const count=points.length/3;
  if(count<=maxPoints)return points;
  const out=new Float32Array(maxPoints*3);
  const step=count/maxPoints;
  for(let i=0;i<maxPoints;i++){
    const src=Math.floor(i*step)*3;
    out.set(points.subarray(src,src+3),i*3);
  }
  return out;
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

  let points;
  const mobile=matchMedia('(max-width:650px)').matches;
  const surfaceCount=mobile?6500:13500;
  const topologyCount=mobile?1800:3500;
  try{points=await modelPoints(surfaceCount,topologyCount);}
  catch(error){
    console.warn('2D-Kopf verwendet geometrischen Fallback.',error);
    points=parametricPoints();
  }

  // Canvas2D mirrors the animated lower scene of the WebGL edition instead of
  // degrading Firefox/VDI clients to a head-only fallback.
  const sceneRandom=seeded(712367);
  const groundParticles=Array.from({length:mobile?520:1450},()=>{
    const x=sceneRandom()-.5;
    const edge=Math.min(1,Math.max(0,(Math.abs(x)-.08)/.42));
    const ridge=.765-edge*.075-Math.sin(x*14)*.008-Math.sin(x*31)*.004;
    const city=sceneRandom()<.38;
    return {
      x,
      y:city?.82-sceneRandom()*.13:ridge+sceneRandom()*(.025+edge*.055),
      phase:sceneRandom()*Math.PI*2,
      size:.45+sceneRandom()*1.25,
      alpha:.16+sceneRandom()*.42,
      violet:sceneRandom()>.88,
    };
  });
  const blendParticles=Array.from({length:mobile?360:950},()=>{
    const x=(sceneRandom()-.5)*.92;
    const center=1-Math.min(1,Math.abs(x)/.46);
    return {
      x,
      y:.775-center*.02+sceneRandom()*(.018+center*.045),
      phase:sceneRandom()*Math.PI*2,
      size:.45+sceneRandom()*1.15,
    };
  });
  const beacons=Array.from({length:mobile?34:88},()=>({
    x:(sceneRandom()-.5)*.88,
    y:.735+sceneRandom()*.09,
    phase:sceneRandom()*Math.PI*2,
    rate:.8+sceneRandom()*1.2,
  }));
  const traffic=Array.from({length:mobile?12:30},()=>({
    phase:sceneRandom(),
    y:.785+sceneRandom()*.045,
    speed:(sceneRandom()>.5?1:-1)*(.025+sceneRandom()*.055),
    alpha:.38+sceneRandom()*.35,
  }));
  const skyLights=Array.from({length:mobile?55:135},()=>({
    x:sceneRandom(),
    y:.13+sceneRandom()*.30,
    phase:sceneRandom()*Math.PI*2,
    size:.35+sceneRandom()*.85,
  }));
  const shootingStars=Array.from({length:mobile?2:4},(_,index)=>({
    phase:sceneRandom(),
    y:.14+sceneRandom()*.24,
    direction:index%2?1:-1,
    speed:.035+sceneRandom()*.025,
  }));

  const reduced=matchMedia('(prefers-reduced-motion:reduce)');
  let paused=reduced.matches,disposed=false,visible=true,last=0,lastFrame=0,elapsed=0,targetX=0,targetY=0,smoothX=0,smoothY=0,headYaw=0,headPitch=0,edition='',raf=0,width=1,height=1,dpr=1;
  const resize=()=>{
    const rect=stage.getBoundingClientRect();
    width=Math.max(1,Math.round(rect.width));
    height=Math.max(1,Math.round(rect.height));
    dpr=Math.min(devicePixelRatio||1,1.5);
    canvas.width=Math.round(width*dpr);
    canvas.height=Math.round(height*dpr);
    canvas.style.width=width+'px';
    canvas.style.height=height+'px';
    context.setTransform(dpr,0,0,dpr,0,0);
    draw(performance.now());
  };

  function draw(now){
    if(disposed)return;
    const dt=Math.min(.05,Math.max(0,(now-last)/1000||0));last=now;elapsed+=dt;
    smoothX+=(targetX-smoothX)*Math.min(1,dt*3.4);
    smoothY+=(targetY-smoothY)*Math.min(1,dt*3.4);
    context.clearRect(0,0,width,height);
    const glow=context.createRadialGradient(width*.5,height*.42,0,width*.5,height*.42,Math.min(width,height)*.38);
    glow.addColorStop(0,'rgba(30,155,255,.12)');
    glow.addColorStop(.45,'rgba(13,95,180,.05)');
    glow.addColorStop(1,'rgba(0,30,80,0)');
    context.fillStyle=glow;context.fillRect(0,0,width,height);
    context.globalCompositeOperation='lighter';

    // Animated sky, city/floor particles and the soft bridge between the head
    // and the night landscape. Coordinates intentionally follow the WebGL
    // scene composition so both renderers have the same visual weight.
    for(const star of skyLights){
      const wave=.5+.5*Math.sin(elapsed*(1.05+star.size*.72)+star.phase);
      const twinkle=Math.pow(wave,3.2);
      context.fillStyle=`rgba(80,190,255,${.11+twinkle*.55})`;
      const r=.45+star.size*.9+twinkle*.8;
      context.fillRect(star.x*width,star.y*height,r,r);
    }
    for(const star of shootingStars){
      const progress=(star.phase+elapsed*star.speed)%1;
      if(progress<.26){
        const p=progress/.26;
        const start=star.direction>0?-.08:1.08;
        const x=(start+star.direction*p*1.16)*width;
        const y=(star.y+p*.085)*height;
        const alpha=Math.sin(p*Math.PI)*.52;
        context.strokeStyle=`rgba(85,205,255,${alpha})`;
        context.lineWidth=1;
        context.beginPath();
        context.moveTo(x,y);
        context.lineTo(x-star.direction*width*.035,y-height*.012);
        context.stroke();
      }
    }
    for(const dot of groundParticles){
      const pulse=.5+.5*Math.sin(elapsed*(.5+dot.size*.38)+dot.phase);
      const x=(.5+dot.x)*width;
      const y=dot.y*height+Math.sin(elapsed*.22+dot.phase)*height*.0008;
      const a=dot.alpha*(.45+pulse*.72);
      context.fillStyle=dot.violet
        ? `rgba(112,96,255,${a})`
        : `rgba(22,154,255,${a})`;
      const size=.7+dot.size*1.15+pulse*.55;
      context.fillRect(x,y,size,size);
    }
    for(const dot of blendParticles){
      const pulse=.5+.5*Math.sin(elapsed*(.55+dot.size*.28)+dot.phase);
      const x=(.5+dot.x)*width;
      const y=dot.y*height+Math.sin(elapsed*.24+dot.phase)*height*.001;
      context.fillStyle=`rgba(35,170,255,${.10+pulse*.27})`;
      const size=.65+dot.size*.95+pulse*.5;
      context.fillRect(x,y,size,size);
    }
    for(const beacon of beacons){
      const wave=.5+.5*Math.sin(elapsed*beacon.rate+beacon.phase);
      const flash=Math.pow(wave,7);
      const x=(.5+beacon.x)*width;
      const y=beacon.y*height;
      const radius=1.1+flash*4.8;
      const g=context.createRadialGradient(x,y,0,x,y,radius);
      g.addColorStop(0,`rgba(170,245,255,${.25+flash*.72})`);
      g.addColorStop(1,'rgba(20,130,255,0)');
      context.fillStyle=g;
      context.beginPath();context.arc(x,y,radius,0,Math.PI*2);context.fill();
    }
    for(const light of traffic){
      let x=(light.phase+elapsed*light.speed)%1;
      if(x<0)x+=1;
      context.fillStyle=`rgba(125,225,255,${light.alpha})`;
      context.fillRect(x*width,light.y*height,2.2,1.3);
    }

    const yawTarget=edition==='free'?-.22:edition==='pro'?.22:smoothX*.3;
    headYaw+=(yawTarget-headYaw)*Math.min(1,dt*3);
    headPitch+=(smoothY*.18-headPitch)*Math.min(1,dt*3);
    const yaw=headYaw,pitch=headPitch;
    const cy=Math.cos(yaw),sy=Math.sin(yaw),cp=Math.cos(pitch),sp=Math.sin(pitch);
    const viewZ=mobile?5.3:4.35;
    const projectionScale=1/(2*Math.tan(39*Math.PI/360)*viewZ);
    const base=height*projectionScale;
    const centerX=width*.5;
    const centerY=height*.5+.06*base;
    const pulse=1+Math.sin(elapsed*.9)*.008;
    let headMinX=Infinity,headMinY=Infinity,headMaxX=-Infinity,headMaxY=-Infinity;

    const buckets=[[],[],[],[]];
    for(let i=0;i<points.length;i+=3){
      const x=points[i],y=points[i+1],z=points[i+2];
      const rx=x*cy+z*sy;
      const rz=-x*sy+z*cy;
      const ry=y*cp-rz*sp;
      const rz2=y*sp+rz*cp;
      const perspective=viewZ/(viewZ-rz2);
      const sx2=centerX+rx*base*perspective*pulse;
      const sy2=centerY-ry*base*perspective*pulse;
      if(sx2<-3||sx2>width+3||sy2<-3||sy2>height+3)continue;
      headMinX=Math.min(headMinX,sx2);headMaxX=Math.max(headMaxX,sx2);
      headMinY=Math.min(headMinY,sy2);headMaxY=Math.max(headMaxY,sy2);
      const depth=clamp(Math.floor((rz2+1.5)/3*4),0,3);
      buckets[depth].push(sx2,sy2);
    }
    if(Number.isFinite(headMinX)){
      stage.dataset.headBounds=[headMinX,headMinY,headMaxX,headMaxY].map(v=>Math.round(v)).join(',');
    }
    const styles=['rgba(20,103,190,.22)','rgba(28,139,230,.36)','rgba(38,178,255,.58)','rgba(129,230,255,.88)'];
    for(let b=0;b<4;b++){
      context.fillStyle=styles[b];
      const size=(.9+b*.22)*(width<650?.9:1);
      const bucket=buckets[b];
      for(let i=0;i<bucket.length;i+=2)context.fillRect(bucket[i],bucket[i+1],size,size);
    }

    const projectEye=(x,y,z)=>{
      const rx=x*cy+z*sy;
      const rz=-x*sy+z*cy;
      const ry=y*cp-rz*sp;
      const rz2=y*sp+rz*cp;
      const perspective=viewZ/(viewZ-rz2);
      return [centerX+rx*base*perspective,centerY-ry*base*perspective,perspective];
    };
    context.shadowBlur=18;
    context.shadowColor='rgba(70,205,255,.9)';
    context.fillStyle='rgba(190,248,255,.94)';
    for(const [x,y,z] of [[-.245,.6,.755],[.18,.6,.75]]){
      const [eyeX,eyeY,eyePerspective]=projectEye(x,y,z);
      context.beginPath();
      context.arc(eyeX,eyeY,Math.max(1.7,base*.021*eyePerspective),0,Math.PI*2);
      context.fill();
    }
    context.shadowBlur=0;
    context.globalCompositeOperation='source-over';
  }

  function loop(now){
    if(disposed||paused||!visible||document.hidden){raf=0;return;}
    if(now-lastFrame>=32){lastFrame=now;draw(now);}
    raf=requestAnimationFrame(loop);
  }
  function sync(){
    if(raf){cancelAnimationFrame(raf);raf=0;}
    draw(performance.now());
    if(!paused&&visible&&!document.hidden)raf=requestAnimationFrame(loop);
  }

  const onPointer=(event)=>{
    targetX=clamp(event.clientX/Math.max(1,innerWidth)*2-1,-1,1);
    targetY=clamp(event.clientY/Math.max(1,innerHeight)*2-1,-1,1);
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
