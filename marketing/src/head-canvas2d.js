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
  return {grid,cols,rows};
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
  canvas.style.filter='brightness(1.03)';
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
      context.fillStyle=`rgba(80,190,255,${.035+twinkle*.18})`;
      const r=.35+star.size*.62+twinkle*.5;
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
      const a=dot.alpha*(.16+pulse*.25);
      context.fillStyle=dot.violet
        ? `rgba(112,96,255,${a})`
        : `rgba(22,154,255,${a})`;
      const size=.45+dot.size*.82+pulse*.35;
      context.fillRect(x,y,size,size);
    }
    for(const dot of blendParticles){
      const pulse=.5+.5*Math.sin(elapsed*(.55+dot.size*.28)+dot.phase);
      const x=(.5+dot.x)*width;
      const y=dot.y*height+Math.sin(elapsed*.24+dot.phase)*height*.001;
      context.fillStyle=`rgba(35,170,255,${.035+pulse*.09})`;
      const size=.45+dot.size*.68+pulse*.32;
      context.fillRect(x,y,size,size);
    }
    for(const beacon of beacons){
      const wave=.5+.5*Math.sin(elapsed*beacon.rate+beacon.phase);
      const flash=Math.pow(wave,7);
      const x=(.5+beacon.x)*width;
      const y=beacon.y*height;
      const radius=.8+flash*3.4;
      const g=context.createRadialGradient(x,y,0,x,y,radius);
      g.addColorStop(0,`rgba(170,245,255,${.10+flash*.45})`);
      g.addColorStop(1,'rgba(20,130,255,0)');
      context.fillStyle=g;
      context.beginPath();context.arc(x,y,radius,0,Math.PI*2);context.fill();
    }
    for(const light of traffic){
      let x=(light.phase+elapsed*light.speed)%1;
      if(x<0)x+=1;
      context.fillStyle=`rgba(125,225,255,${light.alpha*.38})`;
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
    // colorless depth occluder at scale .992.
    const depthCell=3;
    const depthRaster=rasterizeDepthMesh(cloud.depth,project,width,height,depthCell);
    const depthCols=depthRaster.cols;
    const depthRows=depthRaster.rows;
    const depthGrid=depthRaster.grid;
    const surfaceBuckets=Array.from({length:10},()=>[]);
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
      const pointSize=(1.9+pointPower*.43+released*.9)*(4.5/depth);
      const colorBoost=1.42+pointPower*.42;
      const r=Math.round(clamp(surface.colors[o]*colorBoost,0,1)*255);
      const g=Math.round(clamp(surface.colors[o+1]*colorBoost,0,1)*255);
      const b=Math.round(clamp(surface.colors[o+2]*colorBoost,0,1)*255);
      const bucket=clamp(Math.floor((rz2+1.7)/3.4*10),0,9);
      surfaceBuckets[bucket].push(sx2,sy2,pointSize,r,g,b,alpha,depthIndex,rz2);
    }
    for(const bucket of surfaceBuckets){
      for(let i=0;i<bucket.length;i+=9){
        const [x,y,size,r,g,b,a,depthIndex,rz2]=bucket.slice(i,i+9);
        if(depthGrid[depthIndex]>-1e8&&rz2<depthGrid[depthIndex]-.025)continue;
        headMinX=Math.min(headMinX,x);headMaxX=Math.max(headMaxX,x);
        headMinY=Math.min(headMinY,y);headMaxY=Math.max(headMaxY,y);
        // At CSS-pixel scale the WebGL radial point shader is visually a
        // sub-2px dot. Keeping the Canvas quad in that range eliminates the
        // blocky Firefox mask while preserving the deterministic point cloud.
        const renderSize=Math.max(.45,Math.min(1.45,size*.52));
        context.fillStyle=`rgba(${r},${g},${b},${clamp(a*.44,0,1)})`;
        context.fillRect(x-renderSize*.5,y-renderSize*.5,renderSize,renderSize);
      }
    }

    const topology=cloud.topology;
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
      const r=Math.round(clamp(topology.colors[o]*detailBoost*1.55,0,1)*255);
      const g=Math.round(clamp(topology.colors[o+1]*detailBoost*1.55,0,1)*255);
      const b=Math.round(clamp(topology.colors[o+2]*detailBoost*1.55,0,1)*255);
      const renderSize=Math.max(.45,Math.min(1.65,size*.50));
      context.fillStyle=`rgba(${r},${g},${b},${clamp(alpha*.40,0,1)})`;
      context.fillRect(sx2-renderSize*.5,sy2-renderSize*.5,renderSize,renderSize);
    }

    if(Number.isFinite(headMinX)){
      stage.dataset.headBounds=[headMinX,headMinY,headMaxX,headMaxY].map(v=>Math.round(v)).join(',');
    }

    const eyePulse=1+Math.sin(elapsed*1.8)*.025+(edition==='pro'?.055:0);
    for(const [x,y,z] of [[-.245,.6,.755],[.18,.6,.75]]){
      const [eyeX,eyeY,,,perspective]=project(x,y,z);
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
