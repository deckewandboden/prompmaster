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

function deriveVertexNormals(vertices,indexAccessor){
  const normals=new Float32Array(vertices.length);
  const indices=indexAccessor?.data||null;
  const vertexCount=vertices.length/3;
  const triangleCount=indices?Math.floor(indices.length/3):Math.floor(vertexCount/3);
  for(let t=0;t<triangleCount;t++){
    const ia=indices?Math.trunc(indices[t*3]):t*3;
    const ib=indices?Math.trunc(indices[t*3+1]):t*3+1;
    const ic=indices?Math.trunc(indices[t*3+2]):t*3+2;
    if(ia<0||ib<0||ic<0||ia>=vertexCount||ib>=vertexCount||ic>=vertexCount)continue;
    const a=ia*3,b=ib*3,d=ic*3;
    const abx=vertices[b]-vertices[a],aby=vertices[b+1]-vertices[a+1],abz=vertices[b+2]-vertices[a+2];
    const acx=vertices[d]-vertices[a],acy=vertices[d+1]-vertices[a+1],acz=vertices[d+2]-vertices[a+2];
    const nx=aby*acz-abz*acy,ny=abz*acx-abx*acz,nz=abx*acy-aby*acx;
    for(const index of [ia,ib,ic]){
      normals[index*3]+=nx;normals[index*3+1]+=ny;normals[index*3+2]+=nz;
    }
  }
  for(let i=0;i<normals.length;i+=3){
    const length=Math.hypot(normals[i],normals[i+1],normals[i+2])||1;
    normals[i]/=length;normals[i+1]/=length;normals[i+2]/=length;
  }
  return normals;
}

function normalizeNormals(raw){
  const out=new Float32Array(raw.length);
  for(let i=0;i<raw.length;i+=3){
    const length=Math.hypot(raw[i],raw[i+1],raw[i+2])||1;
    out[i]=raw[i]/length;out[i+1]=raw[i+1]/length;out[i+2]=raw[i+2]/length;
  }
  return out;
}

function sampleOriginalSurface(vertices,vertexNormals,indexAccessor,count){
  const indices=indexAccessor?.data||null;
  const vertexCount=vertices.length/3;
  const triangleCount=indices?Math.floor(indices.length/3):Math.floor(vertexCount/3);
  if(!triangleCount)throw new Error('Kopfmodell enthält keine Dreiecke');

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
    totalArea+=Math.hypot(
      aby*acz-abz*acy,
      abz*acx-abx*acz,
      abx*acy-aby*acx
    )*.5;
    cumulative[t]=totalArea;
  }
  if(totalArea<=1e-8)throw new Error('Kopfmodell hat keine nutzbare Oberfläche');

  const random=seeded(93);
  const positions=new Float32Array(count*3);
  const normals=new Float32Array(count*3);
  const colors=new Float32Array(count*3);
  const seeds=new Float32Array(count);
  const scatter=new Float32Array(count*3);

  for(let i=0;i<count;i++){
    const target=random()*totalArea;
    let low=0,high=triangleCount-1;
    while(low<high){
      const mid=(low+high)>>1;
      if(target<=cumulative[mid])high=mid;else low=mid+1;
    }
    const t=low;
    const ia=indices?Math.trunc(indices[t*3]):t*3;
    const ib=indices?Math.trunc(indices[t*3+1]):t*3+1;
    const ic=indices?Math.trunc(indices[t*3+2]):t*3+2;
    const a=ia*3,b=ib*3,d=ic*3;

    // Three.js MeshSurfaceSampler uses exactly two additional random values
    // and folds the barycentric pair when u+v>1. Reproduce that sequence so
    // Firefox receives the same deterministic point cloud as the original
    // WebGL/Edge renderer, not a stylistic approximation.
    let u=random(),v=random();
    if(u+v>1){u=1-u;v=1-v;}
    const wa=1-u-v,wb=u,wc=v;
    const o=i*3;
    positions[o]=vertices[a]*wa+vertices[b]*wb+vertices[d]*wc;
    positions[o+1]=vertices[a+1]*wa+vertices[b+1]*wb+vertices[d+1]*wc;
    positions[o+2]=vertices[a+2]*wa+vertices[b+2]*wb+vertices[d+2]*wc;

    let nx=vertexNormals[a]*wa+vertexNormals[b]*wb+vertexNormals[d]*wc;
    let ny=vertexNormals[a+1]*wa+vertexNormals[b+1]*wb+vertexNormals[d+1]*wc;
    let nz=vertexNormals[a+2]*wa+vertexNormals[b+2]*wb+vertexNormals[d+2]*wc;
    const nl=Math.hypot(nx,ny,nz)||1;nx/=nl;ny/=nl;nz/=nl;
    normals[o]=nx;normals[o+1]=ny;normals[o+2]=nz;

    const front=clamp((nz+.08)/1.08,0,1);
    const intensity=.42+front*.58;
    colors[o]=.14*intensity;colors[o+1]=.63*intensity;colors[o+2]=intensity;

    const pointSeed=random();
    const side=random()-.5;
    const lift=random();
    seeds[i]=pointSeed;
    const distance=.065+pointSeed*.22;
    scatter[o]=nx*distance+side*.05;
    scatter[o+1]=ny*distance+lift*.065;
    scatter[o+2]=nz*distance;
  }
  return {positions,normals,colors,seeds,scatter};
}

function buildOriginalTopology(vertices,vertexNormals,indexAccessor){
  const vertexCount=vertices.length/3;
  const curvature=new Float32Array(vertexCount);
  const neighbors=new Uint16Array(vertexCount);
  const indices=indexAccessor?.data||null;
  const accumulate=(a,b)=>{
    const ao=a*3,bo=b*3;
    const dot=vertexNormals[ao]*vertexNormals[bo]+vertexNormals[ao+1]*vertexNormals[bo+1]+vertexNormals[ao+2]*vertexNormals[bo+2];
    const bend=Math.max(0,1-dot);
    curvature[a]+=bend;curvature[b]+=bend;neighbors[a]++;neighbors[b]++;
  };
  if(indices){
    for(let i=0;i<indices.length;i+=3){
      const a=Math.trunc(indices[i]),b=Math.trunc(indices[i+1]),d=Math.trunc(indices[i+2]);
      accumulate(a,b);accumulate(b,d);accumulate(d,a);
    }
  }
  const colors=new Float32Array(vertices.length);
  const detail=new Float32Array(vertexCount);
  for(let i=0;i<vertexCount;i++){
    const o=i*3;
    const d=Math.min(1,Math.sqrt((curvature[i]/Math.max(1,neighbors[i]))*13));
    const front=clamp((vertexNormals[o+2]+.1)/1.1,0,1);
    const intensity=.28+front*.43+d*.46;
    colors[o]=.1*intensity;colors[o+1]=.58*intensity;colors[o+2]=intensity;detail[i]=d;
  }
  return {positions:vertices,normals:vertexNormals,colors,detail};
}

async function modelCloud(surfaceCount){
  const response=await fetch(MODEL_URL,{cache:'force-cache'});
  if(!response.ok)throw new Error('Originales Kopfmodell nicht verfügbar');
  const {json,bin}=parseGlb(await response.arrayBuffer());
  const {primitive}=findPrimitive(json);
  if(primitive.mode!==undefined&&primitive.mode!==4)throw new Error('Kopfmodell verwendet keinen TRIANGLES-Modus');
  const positionsAccessor=readAccessor(json,bin,primitive.attributes.POSITION);
  if(positionsAccessor.components!==3||positionsAccessor.count<100)throw new Error('Kopfmodell enthält zu wenig Geometrie');
  const vertices=normalizePoints(positionsAccessor.data);
  const indices=primitive.indices===undefined?null:readAccessor(json,bin,primitive.indices);
  const vertexNormals=primitive.attributes.NORMAL===undefined
    ? deriveVertexNormals(vertices,indices)
    : normalizeNormals(readAccessor(json,bin,primitive.attributes.NORMAL).data);
  return {
    surface:sampleOriginalSurface(vertices,vertexNormals,indices,surfaceCount),
    topology:buildOriginalTopology(vertices,vertexNormals,indices),
  };
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
  let paused=reduced.matches,disposed=false,visible=true,last=0,lastFrame=0,elapsed=0,mouseX=0,mouseY=0,smoothX=0,smoothY=0,lastPointerX=0,lastPointerY=0,hasPointer=false,cursorEnergy=0,dissolve=0,headYaw=0,headPitch=0,pointPower=1,topologyPower=1,edition='',raf=0,width=1,height=1,dpr=1;
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

    const inputFollow=3.15;
    smoothX+=(mouseX-smoothX)*Math.min(1,dt*inputFollow);
    smoothY+=(mouseY-smoothY)*Math.min(1,dt*inputFollow);
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
    const centerY=height*.5+.06*base;
    const bob=Math.sin(elapsed*.42)*.008;
    let headMinX=Infinity,headMinY=Infinity,headMaxX=-Infinity,headMaxY=-Infinity;

    const project=(x,y,z)=>{
      const rx=x*cy+z*sy;
      const rz=-x*sy+z*cy;
      const ry=y*cp-rz*sp+bob;
      const rz2=y*sp+rz*cp;
      const depth=viewZ-rz2;
      const perspective=viewZ/depth;
      return [centerX+rx*base*perspective,centerY-ry*base*perspective,rz2,depth,perspective];
    };
    const rotateNormal=(nx,ny,nz)=>{
      const rx=nx*cy+nz*sy;
      const rz=-nx*sy+nz*cy;
      const ry=ny*cp-rz*sp;
      const rz2=ny*sp+rz*cp;
      return [rx,ry,rz2];
    };

    context.shadowBlur=0;
    context.globalCompositeOperation='lighter';

    const surface=cloud.surface;
    const surfaceBuckets=Array.from({length:10},()=>[]);
    for(let i=0;i<surface.seeds.length;i++){
      const o=i*3;
      const x=surface.positions[o],y=surface.positions[o+1],z=surface.positions[o+2];
      const nx=surface.normals[o],ny=surface.normals[o+1],nz=surface.normals[o+2];
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

      const [, , normalZ]=rotateNormal(nx,ny,nz);
      // The original WebGL depth mesh hides the rear surface. Normal-facing
      // rejection is the CPU equivalent and prevents a second "ghost" face.
      if(normalZ<-.08)continue;

      const [sx2,sy2,rz2,depth]=project(px,py,pz);
      if(depth<=.1||sx2<-5||sx2>width+5||sy2<-5||sy2>height+5)continue;
      headMinX=Math.min(headMinX,sx2);headMaxX=Math.max(headMaxX,sx2);
      headMinY=Math.min(headMinY,sy2);headMaxY=Math.max(headMaxY,sy2);
      const pointSize=(1.9+pointPower*.43+released*.9)*(4.5/depth);
      const colorBoost=1.42+pointPower*.42;
      const r=Math.round(clamp(surface.colors[o]*colorBoost,0,1)*255);
      const g=Math.round(clamp(surface.colors[o+1]*colorBoost,0,1)*255);
      const b=Math.round(clamp(surface.colors[o+2]*colorBoost,0,1)*255);
      const bucket=clamp(Math.floor((rz2+1.7)/3.4*10),0,9);
      surfaceBuckets[bucket].push(sx2,sy2,pointSize,r,g,b,alpha);
    }
    for(const bucket of surfaceBuckets){
      for(let i=0;i<bucket.length;i+=7){
        const [x,y,size,r,g,b,a]=bucket.slice(i,i+7);
        context.fillStyle=`rgba(${r},${g},${b},${clamp(a*.82,0,1)})`;
        context.fillRect(x-size*.5,y-size*.5,Math.max(.65,size),Math.max(.65,size));
      }
    }

    const topology=cloud.topology;
    for(let i=0;i<topology.detail.length;i++){
      const o=i*3;
      const x=topology.positions[o],y=topology.positions[o+1],z=topology.positions[o+2];
      const nx=topology.normals[o],ny=topology.normals[o+1],nz=topology.normals[o+2];
      const shoulderFade=1-smoothstep(-1.20,-.08,y);
      let px=x+Math.sign(x)*(.10+Math.abs(x)*.12)*shoulderFade;
      let py=y-.22*shoulderFade;
      let pz=z-.05*shoulderFade;
      const alpha=(.62+topology.detail[i]*.3)*(1-shoulderFade*.997);
      if(alpha<=.006)continue;
      const [, , normalZ]=rotateNormal(nx,ny,nz);
      if(normalZ<-.08)continue;
      const [sx2,sy2,,depth]=project(px,py,pz);
      if(depth<=.1||sx2<-5||sx2>width+5||sy2<-5||sy2>height+5)continue;
      const size=(1.55+topology.detail[i]*1.75+topologyPower*.18)*(4.5/depth);
      const detailBoost=1+topology.detail[i]*.72;
      const r=Math.round(clamp(topology.colors[o]*detailBoost*1.55,0,1)*255);
      const g=Math.round(clamp(topology.colors[o+1]*detailBoost*1.55,0,1)*255);
      const b=Math.round(clamp(topology.colors[o+2]*detailBoost*1.55,0,1)*255);
      context.fillStyle=`rgba(${r},${g},${b},${clamp(alpha*.78,0,1)})`;
      context.fillRect(sx2-size*.5,sy2-size*.5,Math.max(.65,size),Math.max(.65,size));
    }

    if(Number.isFinite(headMinX)){
      stage.dataset.headBounds=[headMinX,headMinY,headMaxX,headMaxY].map(v=>Math.round(v)).join(',');
    }

    const eyePulse=1+Math.sin(elapsed*1.8)*.025+(edition==='pro'?.055:0);
    for(const [x,y,z] of [[-.245,.6,.755],[.18,.6,.75]]){
      const [eyeX,eyeY,,depth,perspective]=project(x,y,z);
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
