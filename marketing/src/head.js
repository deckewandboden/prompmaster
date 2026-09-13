import * as THREE from 'three';
import {GLTFLoader} from 'three/addons/loaders/GLTFLoader.js';
import {MeshSurfaceSampler} from 'three/addons/math/MeshSurfaceSampler.js';

export async function initHead(){
  const canvas=document.getElementById('particle-head');
  if(!canvas)return;
  const stage=canvas.parentElement;
  const fallback=stage.querySelector('.head-fallback');
  let renderer;
  try{renderer=new THREE.WebGLRenderer({canvas,alpha:true,antialias:true,powerPreference:'low-power'});}
  catch{canvas.hidden=true;fallback.hidden=false;return;}
  const mobile=matchMedia('(max-width:800px)').matches;
  renderer.setPixelRatio(Math.min(devicePixelRatio,mobile?1.5:2));
  const scene=new THREE.Scene();
  const camera=new THREE.PerspectiveCamera(39,1,.1,50);
  camera.position.set(0,.06,4.35);
  const group=new THREE.Group();scene.add(group);
  const reduced=matchMedia('(prefers-reduced-motion:reduce)');
  let paused=reduced.matches,visible=true,disposed=false,edition='',pointerX=0,pointerY=0,lastPointerX=0,lastPointerY=0,stretch=0,lastTime=0,elapsed=0;
  const motion=document.createElement('button');motion.className='motion-button';motion.type='button';
  const label=()=>{motion.textContent=paused?'Bewegung aktivieren':'Bewegung pausieren';motion.setAttribute('aria-pressed',String(!paused))};label();
  document.body.append(motion);
  const geometries=[],materials=[];
  const resize=()=>{const {width,height}=stage.getBoundingClientRect();renderer.setSize(width,height,false);camera.aspect=width/Math.max(height,1);camera.position.z=width<650?5.3:4.35;camera.updateProjectionMatrix();if(paused)renderer.render(scene,camera)};
  const ro=new ResizeObserver(resize);ro.observe(stage);
  try{
    const gltf=await new GLTFLoader().loadAsync('/models/head.glb');
    let mesh;gltf.scene.traverse(o=>{if(o.isMesh&&!mesh)mesh=o});
    if(!mesh)throw new Error('Kopfgeometrie fehlt');
    const geometry=mesh.geometry.clone();geometry.applyMatrix4(mesh.matrixWorld);geometry.center();geometry.computeBoundingBox();
    const size=new THREE.Vector3();geometry.boundingBox.getSize(size);geometry.scale(2.9/size.y,2.9/size.y,2.9/size.y);
    geometries.push(geometry);
    const samplingMesh=new THREE.Mesh(geometry);
    const sampler=new MeshSurfaceSampler(samplingMesh).build();
    let seed=93;sampler.setRandomGenerator(()=>{seed=(seed*1664525+1013904223)>>>0;return seed/4294967296});
    const count=mobile?6500:16000;
    const positions=new Float32Array(count*3),colors=new Float32Array(count*3),p=new THREE.Vector3(),n=new THREE.Vector3();
    for(let i=0;i<count;i++){
      sampler.sample(p,n);positions.set([p.x,p.y,p.z],i*3);
      const intensity=.48+Math.max(0,n.z)*.65;
      colors.set([.14*intensity,.63*intensity,1*intensity],i*3);
    }
    const pointsGeometry=new THREE.BufferGeometry();pointsGeometry.setAttribute('position',new THREE.BufferAttribute(positions,3));pointsGeometry.setAttribute('color',new THREE.BufferAttribute(colors,3));geometries.push(pointsGeometry);
    const pointMaterial=new THREE.ShaderMaterial({transparent:true,depthWrite:false,blending:THREE.AdditiveBlending,vertexColors:true,uniforms:{uTime:{value:0},uPower:{value:1},uPixel:{value:renderer.getPixelRatio()},uPointer:{value:new THREE.Vector2()},uStretch:{value:0}},vertexShader:'uniform float uTime; uniform float uPower; uniform float uPixel; uniform vec2 uPointer; uniform float uStretch; varying vec3 vColor; void main(){vColor=color;vec3 p=position;float band=exp(-pow((p.y-uPointer.y*.58)*1.8,2.));float wave=sin(p.y*8.+uTime*1.35)+cos(p.x*7.-uTime*.9);p.x+=uPointer.x*.14*band*(.6+uStretch);p.y+=uPointer.y*.045*exp(-pow(p.x*1.4,2.));p+=normalize(position)*wave*(.006+.018*uStretch);p.x*=1.+sin(uTime*.62+p.y*2.8)*(.012+.028*uStretch);p.y*=1.+cos(uTime*.48+p.x*2.2)*(.008+.018*uStretch);vec4 mv=modelViewMatrix*vec4(p,1.);gl_PointSize=(2.1+uPower*.55+uStretch*.7)*uPixel*(4.5/-mv.z);gl_Position=projectionMatrix*mv;}',fragmentShader:'uniform float uPower; varying vec3 vColor; void main(){float d=length(gl_PointCoord-.5);if(d>.5)discard;float a=pow(1.-d*2.,1.65);gl_FragColor=vec4(vColor*(1.5+uPower*.5),a);}'});
    materials.push(pointMaterial);group.add(new THREE.Points(pointsGeometry,pointMaterial));
    const edgesGeometry=new THREE.WireframeGeometry(geometry);geometries.push(edgesGeometry);
    const lineMaterial=new THREE.LineBasicMaterial({color:0x3eafff,transparent:true,opacity:.12,depthWrite:false,blending:THREE.AdditiveBlending});materials.push(lineMaterial);
    const lines=new THREE.LineSegments(edgesGeometry,lineMaterial);group.add(lines);
    const baseEdges=Math.floor(edgesGeometry.attributes.position.count*.64/2)*2;
    edgesGeometry.setDrawRange(0,baseEdges);
    group.rotation.y=0;
    // Transparent depth occlusion keeps the facial features legible through the back of the head.
    const depthMaterial=new THREE.MeshBasicMaterial({colorWrite:false});materials.push(depthMaterial);
    const depthMesh=new THREE.Mesh(geometry,depthMaterial);depthMesh.renderOrder=-1;depthMesh.scale.setScalar(.992);group.add(depthMesh);
    const makeGlow=(size,opacity)=>{
      const glowCanvas=document.createElement('canvas');glowCanvas.width=128;glowCanvas.height=128;
      const context=glowCanvas.getContext('2d');const gradient=context.createRadialGradient(64,64,0,64,64,64);
      gradient.addColorStop(0,'rgba(255,255,255,1)');gradient.addColorStop(.08,'rgba(181,246,255,1)');gradient.addColorStop(.23,'rgba(55,197,255,.98)');gradient.addColorStop(.52,'rgba(0,111,255,.34)');gradient.addColorStop(1,'rgba(0,80,255,0)');
      context.fillStyle=gradient;context.fillRect(0,0,128,128);
      const texture=new THREE.CanvasTexture(glowCanvas);texture.colorSpace=THREE.SRGBColorSpace;
      const material=new THREE.SpriteMaterial({map:texture,transparent:true,opacity,depthTest:false,depthWrite:false,blending:THREE.AdditiveBlending});
      const sprite=new THREE.Sprite(material);sprite.scale.setScalar(size);materials.push(material);materials.push(texture);return sprite;
    };
    const eyes=new THREE.Group();
    for(const x of [-.18,.18]){
      const halo=makeGlow(.5,.95);halo.position.set(x,.6,.84);eyes.add(halo);
      const core=makeGlow(.17,1);core.position.set(x,.6,.87);eyes.add(core);
    }
    group.add(eyes);
    const dustPositions=[];for(let i=0;i<(mobile?220:680);i++){const a=i*2.399963;const r=1.5+(i%43)*.095;dustPositions.push(Math.cos(a)*r,Math.sin(a)*r*.65,Math.sin(i)*.7-.5)}
    const dustGeo=new THREE.BufferGeometry();dustGeo.setAttribute('position',new THREE.Float32BufferAttribute(dustPositions,3));geometries.push(dustGeo);
    const dustMat=new THREE.PointsMaterial({color:0x3493df,size:.012,transparent:true,opacity:.36,depthWrite:false});materials.push(dustMat);const dust=new THREE.Points(dustGeo,dustMat);scene.add(dust);
    function render(time=0){
      const dt=Math.min((time-lastTime)/1000,.05);lastTime=time;
      if(!paused){elapsed+=Math.max(0,dt);const targetX=edition==='free'?-.28:edition==='pro'?.28:pointerX*.25;
        group.rotation.y+= (targetX-group.rotation.y)*Math.min(1,dt*4);
        group.rotation.x+= (-pointerY*.13-group.rotation.x)*Math.min(1,dt*4);
        group.position.y=Math.sin(elapsed*.5)*.016;
        pointMaterial.uniforms.uTime.value=elapsed;
        stretch+=(Math.min(1,stretch)-stretch)*Math.min(1,dt*2);
        stretch=Math.max(0,stretch-dt*.45);
        pointMaterial.uniforms.uPointer.value.set(pointerX,pointerY);
        pointMaterial.uniforms.uStretch.value=stretch+(edition==='pro'?.32:0);
        const power=edition==='pro'?1.65:edition==='free'?.7:1;
        pointMaterial.uniforms.uPower.value+=(power-pointMaterial.uniforms.uPower.value)*Math.min(1,dt*3);
        lineMaterial.opacity+=( (edition==='pro'?.22:.12)-lineMaterial.opacity)*Math.min(1,dt*3);
        edgesGeometry.setDrawRange(0,edition==='pro'?edgesGeometry.attributes.position.count:baseEdges);
        const scaleX=1+(edition==='pro'?.045:0)+Math.abs(pointerX)*.018+stretch*.035;
        const scaleY=1-(edition==='pro'?.018:0)+Math.abs(pointerY)*.012-stretch*.014;
        group.scale.x+=(scaleX-group.scale.x)*Math.min(1,dt*3.5);
        group.scale.y+=(scaleY-group.scale.y)*Math.min(1,dt*3.5);
        eyes.position.x+=(pointerX*.045-eyes.position.x)*Math.min(1,dt*7);
        eyes.position.y+=(pointerY*.032-eyes.position.y)*Math.min(1,dt*7);
        const eyePulse=1+Math.sin(elapsed*2.4)*.045+(edition==='pro'?.12:0);
        eyes.scale.setScalar(eyePulse);
        dust.rotation.z=elapsed*.012;
      }
      renderer.render(scene,camera);
    }
    function syncLoop(){renderer.setAnimationLoop(!paused&&visible&&!document.hidden?render:null);render(lastTime)}
    motion.addEventListener('click',()=>{paused=!paused;label();syncLoop()});
    const onReduced=()=>{paused=reduced.matches;label();syncLoop()};reduced.addEventListener('change',onReduced);
    const onVisibility=()=>syncLoop();document.addEventListener('visibilitychange',onVisibility);
    const onPointer=e=>{const nextX=Math.max(-1,Math.min(1,e.clientX/innerWidth*2-1));const nextY=Math.max(-1,Math.min(1,e.clientY/innerHeight*2-1));stretch=Math.min(1,stretch+Math.hypot(nextX-lastPointerX,nextY-lastPointerY)*2.8);lastPointerX=nextX;lastPointerY=nextY;pointerX=nextX;pointerY=nextY};
    window.addEventListener('pointermove',onPointer,{passive:true});
    const controls=new AbortController();
    document.querySelectorAll('[data-edition]').forEach(card=>{for(const event of ['pointerenter','focusin'])card.addEventListener(event,()=>{edition=card.dataset.edition},{signal:controls.signal});for(const event of ['pointerleave','focusout'])card.addEventListener(event,()=>{edition=''},{signal:controls.signal})});
    const observer=new IntersectionObserver(([entry])=>{visible=entry.isIntersecting;syncLoop()},{rootMargin:'80px'});observer.observe(canvas);
    const onLost=e=>{e.preventDefault();renderer.setAnimationLoop(null);canvas.hidden=true;motion.hidden=true;fallback.hidden=false};canvas.addEventListener('webglcontextlost',onLost);
    resize();syncLoop();
    const cleanup=()=>{if(disposed)return;disposed=true;renderer.setAnimationLoop(null);observer.disconnect();ro.disconnect();controls.abort();window.removeEventListener('pointermove',onPointer);document.removeEventListener('visibilitychange',onVisibility);reduced.removeEventListener('change',onReduced);geometries.forEach(g=>g.dispose());materials.forEach(m=>m.dispose());renderer.dispose()};
    window.addEventListener('pagehide',cleanup,{once:true});
    if(import.meta.hot)import.meta.hot.dispose(cleanup);
  }catch(error){ro.disconnect();renderer.dispose();canvas.hidden=true;motion.hidden=true;fallback.hidden=false;console.error('Partikelkopf nicht verfügbar.',error)}
}
