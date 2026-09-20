import * as THREE from 'three';
import {GLTFLoader} from 'three/addons/loaders/GLTFLoader.js';
import {MeshSurfaceSampler} from 'three/addons/math/MeshSurfaceSampler.js';
import {createLowerSceneData,createShootingStarCanvas,initCanvasHead} from './head-canvas2d.js';

export async function initHead(){
  let canvas=document.getElementById('particle-head');
  if(!canvas)return;
  const stage=canvas.parentElement;
  const fallback=stage.querySelector('.head-fallback');
  // Edge is the rendering contract. Every browser gets the exact same
  // WebGL2 initialization first; there is no Firefox-specific renderer.
  // A second Three.js-managed WebGL retry uses the same scene/animation code
  // before the CPU Canvas2D emergency fallback is allowed.
  let renderer;
  let webglError=null;
  const webglAttempts=[
    {
      id:'edge-webgl2',
      context:{
        alpha:true,
        antialias:true,
        powerPreference:'low-power',
        failIfMajorPerformanceCaveat:false,
      },
      renderer:{alpha:true,antialias:true,powerPreference:'low-power'},
    },
    {
      id:'edge-webgl2-no-msaa',
      context:{
        alpha:true,
        antialias:false,
        depth:true,
        stencil:false,
        premultipliedAlpha:true,
        preserveDrawingBuffer:false,
        powerPreference:'default',
        failIfMajorPerformanceCaveat:false,
      },
      renderer:{alpha:true,antialias:false,powerPreference:'default'},
    },
    {
      id:'edge-webgl2-minimal',
      context:{
        alpha:true,
        antialias:false,
        failIfMajorPerformanceCaveat:false,
      },
      renderer:{alpha:true,antialias:false},
    },
  ];
  const attempted=[];
  const freshCanvas=()=>{
    const replacement=canvas.cloneNode(false);
    canvas.replaceWith(replacement);
    canvas=replacement;
    return canvas;
  };
  for(let attemptIndex=0;attemptIndex<webglAttempts.length;attemptIndex++){
    const attempt=webglAttempts[attemptIndex];
    if(renderer)break;
    attempted.push(attempt.id);
    if(attemptIndex>0)freshCanvas();
    try{
      const webglContext=canvas.getContext('webgl2',attempt.context);
      if(!webglContext)continue;
      renderer=new THREE.WebGLRenderer({
        canvas,
        context:webglContext,
        ...attempt.renderer,
      });
      stage.dataset.webglInit=attempt.id;
    }catch(error){
      webglError=error;
    }
  }
  if(!renderer){
    attempted.push('edge-three-managed-no-msaa');
    freshCanvas();
    try{
      renderer=new THREE.WebGLRenderer({
        canvas,
        alpha:true,
        antialias:false,
        powerPreference:'default',
      });
      stage.dataset.webglInit='edge-three-managed-no-msaa';
    }catch(error){
      webglError=error;
    }
  }
  stage.dataset.webglAttempts=attempted.join(',');
  if(!renderer){
    console.info(
      'WebGL2 nicht verfügbar – Canvas2D-Notfallrenderer wird verwendet.',
      webglError?.message||webglError||''
    );
    stage.dataset.webglInit='canvas-emergency';
    stage.dataset.webglFailure=String(webglError?.message||webglError||'context-unavailable').slice(0,240);
    await initCanvasHead({sourceCanvas:canvas,stage,fallback});
    return;
  }
  const mobile=matchMedia('(max-width:800px)').matches;
  renderer.setPixelRatio(Math.min(devicePixelRatio,mobile?1.5:2));
  const scene=new THREE.Scene();
  const camera=new THREE.PerspectiveCamera(39,1,.1,50);
  camera.position.set(0,.06,4.35);
  const group=new THREE.Group();scene.add(group);
  const reduced=matchMedia('(prefers-reduced-motion:reduce)');
  let paused=reduced.matches,visible=true,disposed=false,edition='',mouseX=0,mouseY=0,smoothPointerX=0,smoothPointerY=0,lastPointerX=0,lastPointerY=0,hasPointer=false,cursorEnergy=0,dissolve=0,lastTime=0,elapsed=0;
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
    const count=mobile?8200:22000;
    const positions=new Float32Array(count*3),colors=new Float32Array(count*3),seeds=new Float32Array(count),scatter=new Float32Array(count*3),p=new THREE.Vector3(),n=new THREE.Vector3();
    for(let i=0;i<count;i++){
      sampler.sample(p,n);positions.set([p.x,p.y,p.z],i*3);
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
    const pointsGeometry=new THREE.BufferGeometry();pointsGeometry.setAttribute('position',new THREE.BufferAttribute(positions,3));pointsGeometry.setAttribute('color',new THREE.BufferAttribute(colors,3));pointsGeometry.setAttribute('aSeed',new THREE.BufferAttribute(seeds,1));pointsGeometry.setAttribute('aScatter',new THREE.BufferAttribute(scatter,3));geometries.push(pointsGeometry);
    const pointMaterial=new THREE.ShaderMaterial({transparent:true,depthWrite:false,blending:THREE.AdditiveBlending,vertexColors:true,uniforms:{uTime:{value:0},uPower:{value:1},uPixel:{value:renderer.getPixelRatio()},uDissolve:{value:0}},vertexShader:'uniform float uTime; uniform float uPower; uniform float uPixel; uniform float uDissolve; attribute float aSeed; attribute vec3 aScatter; varying vec3 vColor; varying float vAlpha; void main(){vColor=color;float vertical=(position.y+1.45)/2.9;float threshold=aSeed*.61+vertical*.13;float released=smoothstep(threshold-.14,threshold+.08,uDissolve);float shimmer=.5+.5*sin(uTime*(.48+aSeed*.32)+aSeed*23.);float shoulderFade=1.-smoothstep(-1.28,-0.10,position.y);released=max(released, shoulderFade*(.92+.08*shimmer));vec3 scatter=aScatter*(released*(.78+.34*shimmer)+shoulderFade*1.95);vec3 p=position+scatter; p.x+=sign(position.x)*(0.12+abs(position.x)*0.16)*shoulderFade; p.y-=0.30*shoulderFade; p.z-=0.08*shoulderFade; vAlpha=(1.-released*(.12+aSeed*.22))*(1.-shoulderFade*.995); vec4 mv=modelViewMatrix*vec4(p,1.);gl_PointSize=(1.9+uPower*.43+released*.9)*uPixel*(4.5/-mv.z);gl_Position=projectionMatrix*mv;}',fragmentShader:'uniform float uPower; varying vec3 vColor; varying float vAlpha; void main(){float d=length(gl_PointCoord-.5);if(d>.5)discard;float a=pow(1.-d*2.,1.75)*vAlpha;gl_FragColor=vec4(vColor*(1.42+uPower*.42),a);}'});
    materials.push(pointMaterial);group.add(new THREE.Points(pointsGeometry,pointMaterial));

    // A stable topology layer uses the model's real vertices. Fine geometry naturally
    // concentrates vertices around lips, nostrils, eyelids and ears without drawing
    // artificial facial shapes on top of the head.
    const vertexPosition=geometry.getAttribute('position'),vertexNormal=geometry.getAttribute('normal'),vertexCount=vertexPosition.count;
    const curvature=new Float32Array(vertexCount),neighbors=new Uint16Array(vertexCount),index=geometry.index?.array;
    const accumulate=(a,b)=>{const dot=vertexNormal.getX(a)*vertexNormal.getX(b)+vertexNormal.getY(a)*vertexNormal.getY(b)+vertexNormal.getZ(a)*vertexNormal.getZ(b);const bend=Math.max(0,1-dot);curvature[a]+=bend;curvature[b]+=bend;neighbors[a]++;neighbors[b]++};
    if(index){for(let i=0;i<index.length;i+=3){const a=index[i],b=index[i+1],c=index[i+2];accumulate(a,b);accumulate(b,c);accumulate(c,a)}}
    const topologyPositions=new Float32Array(vertexCount*3),topologyColors=new Float32Array(vertexCount*3),topologyDetail=new Float32Array(vertexCount);
    for(let i=0;i<vertexCount;i++){
      const detail=Math.min(1,Math.sqrt((curvature[i]/Math.max(1,neighbors[i]))*13));
      const front=Math.max(0,Math.min(1,(vertexNormal.getZ(i)+.1)/1.1));
      const intensity=.28+front*.43+detail*.46;
      topologyPositions.set([vertexPosition.getX(i),vertexPosition.getY(i),vertexPosition.getZ(i)],i*3);
      topologyColors.set([.1*intensity,.58*intensity,1*intensity],i*3);topologyDetail[i]=detail;
    }
    const topologyGeometry=new THREE.BufferGeometry();topologyGeometry.setAttribute('position',new THREE.BufferAttribute(topologyPositions,3));topologyGeometry.setAttribute('color',new THREE.BufferAttribute(topologyColors,3));topologyGeometry.setAttribute('aDetail',new THREE.BufferAttribute(topologyDetail,1));geometries.push(topologyGeometry);
    const topologyMaterial=new THREE.ShaderMaterial({transparent:true,depthWrite:false,blending:THREE.AdditiveBlending,vertexColors:true,uniforms:{uPixel:{value:renderer.getPixelRatio()},uPower:{value:1}},vertexShader:'uniform float uPixel; uniform float uPower; attribute float aDetail; varying vec3 vColor; varying float vAlpha; void main(){vColor=color*(1.+aDetail*.72);float shoulderFade=1.-smoothstep(-1.20,-0.08,position.y);vec3 p=position; p.x+=sign(position.x)*(0.10+abs(position.x)*0.12)*shoulderFade; p.y-=0.22*shoulderFade; p.z-=0.05*shoulderFade; vAlpha=(.62+aDetail*.3)*(1.-shoulderFade*.997);vec4 mv=modelViewMatrix*vec4(p,1.);gl_PointSize=(1.55+aDetail*1.75+uPower*.18)*uPixel*(4.5/-mv.z);gl_Position=projectionMatrix*mv;}',fragmentShader:'varying vec3 vColor; varying float vAlpha; void main(){float d=length(gl_PointCoord-.5);if(d>.5)discard;float a=pow(1.-d*2.,1.8)*vAlpha;gl_FragColor=vec4(vColor*1.55,a);}'});
    materials.push(topologyMaterial);group.add(new THREE.Points(topologyGeometry,topologyMaterial));
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
      const material=new THREE.SpriteMaterial({map:texture,transparent:true,opacity,depthTest:true,depthWrite:false,blending:THREE.AdditiveBlending});
      const sprite=new THREE.Sprite(material);sprite.userData.baseSize=size;sprite.scale.setScalar(size);materials.push(material);materials.push(texture);return sprite;
    };
    const eyes=new THREE.Group();
    for(const [x,y,z] of [[-.245,.6,.755],[.18,.6,.75]]){
      const halo=makeGlow(.27,.56);halo.position.set(x,y,z);eyes.add(halo);
      const core=makeGlow(.072,.8);core.position.set(x,y,z+.025);eyes.add(core);
    }
    group.add(eyes);
    // Soft dissolve cloud: the shoulder particles spread gently left and right and fade out toward the image edges.
    const dustCount=mobile?220:680,dustPositions=[];
    for(let i=0;i<dustCount;i++){
      const t=i/Math.max(1,dustCount-1);
      const side=(i%2===0?1:-1);
      const edge=Math.pow((i%2===0?t:1-t), .72);
      const span=.55 + edge*3.65;
      const jitter=(Math.sin(i*12.37)+Math.cos(i*5.91))*0.045;
      const x=side*(span + jitter);
      const y=-0.22 - Math.pow((i*0.61803398875)%1, .96)*1.95;
      const z=-1.1 + Math.sin(i*0.37)*0.55;
      dustPositions.push(x,y,z);
    }
    const dustGeo=new THREE.BufferGeometry();dustGeo.setAttribute('position',new THREE.Float32BufferAttribute(dustPositions,3));geometries.push(dustGeo);
    const dustMat=new THREE.PointsMaterial({color:0x3493df,size:.012,transparent:true,opacity:.30,depthWrite:false});materials.push(dustMat);const dust=new THREE.Points(dustGeo,dustMat);scene.add(dust);

    // Layered ground and skyline lights visually connect the 3D head with the landscape.
    // Edge/WebGL and Firefox/Canvas2D consume the exact same deterministic scene data.
    const sceneData=createLowerSceneData(mobile);
    stage.dataset.lowerSceneContract='edge-shared-v1';
    const landscapeCount=sceneData.landscape.length,landscapePositions=new Float32Array(landscapeCount*3),landscapeColors=new Float32Array(landscapeCount*3),landscapePhase=new Float32Array(landscapeCount),landscapeSize=new Float32Array(landscapeCount);
    for(let i=0;i<landscapeCount;i++){
      const point=sceneData.landscape[i];
      landscapePositions.set([point.x,point.y,point.z],i*3);
      landscapeColors.set(point.color,i*3);
      landscapePhase[i]=point.phase;landscapeSize[i]=point.size;
    }
    const landscapeGeometry=new THREE.BufferGeometry();landscapeGeometry.setAttribute('position',new THREE.BufferAttribute(landscapePositions,3));landscapeGeometry.setAttribute('color',new THREE.BufferAttribute(landscapeColors,3));landscapeGeometry.setAttribute('aPhase',new THREE.BufferAttribute(landscapePhase,1));landscapeGeometry.setAttribute('aSize',new THREE.BufferAttribute(landscapeSize,1));geometries.push(landscapeGeometry);
    const landscapeMaterial=new THREE.ShaderMaterial({transparent:true,depthWrite:false,blending:THREE.AdditiveBlending,vertexColors:true,uniforms:{uTime:{value:0},uPixel:{value:renderer.getPixelRatio()}},vertexShader:'uniform float uTime; uniform float uPixel; attribute float aPhase; attribute float aSize; varying vec3 vColor; varying float vAlpha; void main(){float pulse=.5+.5*sin(uTime*(.5+aSize*.38)+aPhase);vec3 p=position;p.y+=sin(uTime*.22+aPhase)*.006;vColor=color;vAlpha=.24+pulse*.58;vec4 mv=modelViewMatrix*vec4(p,1.);gl_PointSize=(1.15+aSize*1.5+pulse*.72)*uPixel*(4.5/-mv.z);gl_Position=projectionMatrix*mv;}',fragmentShader:'varying vec3 vColor; varying float vAlpha; void main(){float d=length(gl_PointCoord-.5);if(d>.5)discard;float a=pow(1.-d*2.,1.7)*vAlpha;gl_FragColor=vec4(vColor*1.72,a);}'});
    materials.push(landscapeMaterial);const landscapeLights=new THREE.Points(landscapeGeometry,landscapeMaterial);scene.add(landscapeLights);

    // A low, wide particle veil blends the base of the head into the landscape.
    // Its curved upper edge stays below the mountain silhouette at both sides.
    const blendCount=sceneData.blend.length,blendPositions=new Float32Array(blendCount*3),blendPhases=new Float32Array(blendCount),blendSizes=new Float32Array(blendCount);
    for(let i=0;i<blendCount;i++){
      const point=sceneData.blend[i];
      blendPositions.set([point.x,point.y,point.z],i*3);blendPhases[i]=point.phase;blendSizes[i]=point.size;
    }
    const blendGeometry=new THREE.BufferGeometry();blendGeometry.setAttribute('position',new THREE.BufferAttribute(blendPositions,3));blendGeometry.setAttribute('aPhase',new THREE.BufferAttribute(blendPhases,1));blendGeometry.setAttribute('aSize',new THREE.BufferAttribute(blendSizes,1));geometries.push(blendGeometry);
    const blendMaterial=new THREE.ShaderMaterial({transparent:true,depthWrite:false,blending:THREE.AdditiveBlending,uniforms:{uTime:{value:0},uPixel:{value:renderer.getPixelRatio()}},vertexShader:'uniform float uTime;uniform float uPixel;attribute float aPhase;attribute float aSize;varying float vAlpha;void main(){float pulse=.5+.5*sin(uTime*(.55+aSize*.28)+aPhase);vAlpha=.16+pulse*.42;vec3 p=position;p.y+=sin(uTime*.24+aPhase)*.008;vec4 mv=modelViewMatrix*vec4(p,1.);gl_PointSize=(1.05+aSize*1.35+pulse*.7)*uPixel*(4.5/-mv.z);gl_Position=projectionMatrix*mv;}',fragmentShader:'varying float vAlpha;void main(){float d=length(gl_PointCoord-.5);if(d>.5)discard;gl_FragColor=vec4(.12,.66,1.,pow(1.-d*2.,1.65)*vAlpha);}'});
    materials.push(blendMaterial);const landscapeBlend=new THREE.Points(blendGeometry,blendMaterial);scene.add(landscapeBlend);

    // Sparse light nodes switch on at changing positions across the ground plane.
    const beaconCount=sceneData.beacons.length,beaconPositions=new Float32Array(beaconCount*3),beaconPhases=new Float32Array(beaconCount),beaconRates=new Float32Array(beaconCount);
    for(let i=0;i<beaconCount;i++){const point=sceneData.beacons[i];beaconPositions.set([point.x,point.y,point.z],i*3);beaconPhases[i]=point.phase;beaconRates[i]=point.rate}
    const beaconGeometry=new THREE.BufferGeometry();beaconGeometry.setAttribute('position',new THREE.BufferAttribute(beaconPositions,3));beaconGeometry.setAttribute('aPhase',new THREE.BufferAttribute(beaconPhases,1));beaconGeometry.setAttribute('aRate',new THREE.BufferAttribute(beaconRates,1));geometries.push(beaconGeometry);
    const beaconMaterial=new THREE.ShaderMaterial({transparent:true,depthWrite:false,blending:THREE.AdditiveBlending,uniforms:{uTime:{value:0},uPixel:{value:renderer.getPixelRatio()}},vertexShader:'uniform float uTime;uniform float uPixel;attribute float aPhase;attribute float aRate;varying float vAlpha;void main(){float wave=.5+.5*sin(uTime*(1.05+aRate)+aPhase);float flash=pow(wave,7.);vAlpha=.14+flash*1.28;vec4 mv=modelViewMatrix*vec4(position,1.);gl_PointSize=(2.8+flash*8.5)*uPixel*(4.5/-mv.z);gl_Position=projectionMatrix*mv;}',fragmentShader:'varying float vAlpha;void main(){float d=length(gl_PointCoord-.5);if(d>.5)discard;float glow=pow(1.-d*2.,1.35);gl_FragColor=vec4(.38,.9,1.,glow*vAlpha);}'});
    materials.push(beaconMaterial);const cityBeacons=new THREE.Points(beaconGeometry,beaconMaterial);scene.add(cityBeacons);

    const trafficCount=sceneData.traffic.length,trafficPositions=new Float32Array(trafficCount*3),trafficSpeed=new Float32Array(trafficCount),trafficPhase=new Float32Array(trafficCount);
    for(let i=0;i<trafficCount;i++){const point=sceneData.traffic[i];trafficPositions.set([0,point.y,point.z],i*3);trafficSpeed[i]=point.speed;trafficPhase[i]=point.phase}
    const trafficGeometry=new THREE.BufferGeometry();trafficGeometry.setAttribute('position',new THREE.BufferAttribute(trafficPositions,3));trafficGeometry.setAttribute('aSpeed',new THREE.BufferAttribute(trafficSpeed,1));trafficGeometry.setAttribute('aPhase',new THREE.BufferAttribute(trafficPhase,1));geometries.push(trafficGeometry);
    const trafficMaterial=new THREE.ShaderMaterial({transparent:true,depthWrite:false,blending:THREE.AdditiveBlending,uniforms:{uTime:{value:0},uPixel:{value:renderer.getPixelRatio()}},vertexShader:'uniform float uTime;uniform float uPixel;attribute float aSpeed;attribute float aPhase;varying float vAlpha;void main(){vec3 p=position;p.x=mod(aPhase+uTime*aSpeed+4.2,8.4)-4.2;vAlpha=.48+.35*sin(uTime*1.7+aPhase);vec4 mv=modelViewMatrix*vec4(p,1.);gl_PointSize=2.5*uPixel*(4.5/-mv.z);gl_Position=projectionMatrix*mv;}',fragmentShader:'varying float vAlpha;void main(){float d=length(gl_PointCoord-.5);if(d>.5)discard;gl_FragColor=vec4(.42,.9,1.,(1.-d*2.)*vAlpha);}'});
    materials.push(trafficMaterial);const trafficLights=new THREE.Points(trafficGeometry,trafficMaterial);scene.add(trafficLights);

    const skyCount=sceneData.sky.length,skyPositions=new Float32Array(skyCount*3),skyPhases=new Float32Array(skyCount),skySizes=new Float32Array(skyCount);
    for(let i=0;i<skyCount;i++){const point=sceneData.sky[i];skyPositions.set([point.x,point.y,point.z],i*3);skyPhases[i]=point.phase;skySizes[i]=point.size}
    const skyGeometry=new THREE.BufferGeometry();skyGeometry.setAttribute('position',new THREE.BufferAttribute(skyPositions,3));skyGeometry.setAttribute('aPhase',new THREE.BufferAttribute(skyPhases,1));skyGeometry.setAttribute('aSize',new THREE.BufferAttribute(skySizes,1));geometries.push(skyGeometry);
    const skyMaterial=new THREE.ShaderMaterial({transparent:true,depthWrite:false,blending:THREE.AdditiveBlending,uniforms:{uTime:{value:0},uPixel:{value:renderer.getPixelRatio()}},vertexShader:'uniform float uTime;uniform float uPixel;attribute float aPhase;attribute float aSize;varying float vAlpha;void main(){float wave=.5+.5*sin(uTime*(1.05+aSize*.72)+aPhase);float twinkle=pow(wave,3.2);vAlpha=.16+twinkle*.98;vec4 mv=modelViewMatrix*vec4(position,1.);gl_PointSize=(.9+aSize*1.55+twinkle*1.75)*uPixel*(4.5/-mv.z);gl_Position=projectionMatrix*mv;}',fragmentShader:'varying float vAlpha;void main(){float d=length(gl_PointCoord-.5);if(d>.5)discard;gl_FragColor=vec4(.52,.84,1.,pow(1.-d*2.,1.35)*vAlpha);}'});
    materials.push(skyMaterial);const skyStars=new THREE.Points(skyGeometry,skyMaterial);scene.add(skyStars);

    // Infrequent light trails cross at different depths to add quiet spatial movement.
    const starCount=sceneData.shootingStars.length;
    const createStarTexture=(reverse=false)=>{
      const texture=new THREE.CanvasTexture(createShootingStarCanvas(reverse));
      texture.colorSpace=THREE.SRGBColorSpace;
      materials.push(texture);
      return texture;
    };
    const starTextureLtr=createStarTexture(false),starTextureRtl=createStarTexture(true);
    const shootingStars=[];
    for(let s=0;s<starCount;s++){
      const spec=sceneData.shootingStars[s],direction=spec.direction,material=new THREE.SpriteMaterial({map:direction>0?starTextureLtr:starTextureRtl,transparent:true,opacity:0,depthTest:true,depthWrite:false,blending:THREE.AdditiveBlending,rotation:direction>0?-.22:.22});
      const sprite=new THREE.Sprite(material);sprite.visible=false;sprite.scale.set(.58,.032,1);materials.push(material);shootingStars.push(sprite);scene.add(sprite);
    }
    const updateShootingStars=()=>{
      for(let s=0;s<starCount;s++){
        const spec=sceneData.shootingStars[s],direction=spec.direction,activeTime=elapsed-spec.offset,local=activeTime>=0?activeTime%spec.period:-1,active=local>=0&&local<3.45,progress=active?local/3.45:0;
        const startX=direction>0?-3.25:3.25;
        const star=shootingStars[s];star.visible=active;
        if(active){star.position.set(startX+direction*progress*4.75-smoothPointerX*.035,spec.y-progress*.76,spec.z);star.material.opacity=Math.sin(progress*Math.PI)*spec.opacity;star.scale.set(.72+progress*.48+spec.scaleBias,.026+progress*.022,1)}
      }
    };
    function render(time=0){
      const dt=Math.min((time-lastTime)/1000,.05);lastTime=time;
      {elapsed+=Math.max(0,dt);
        const inputFollow=3.15;
        smoothPointerX+=(mouseX-smoothPointerX)*Math.min(1,dt*inputFollow);
        smoothPointerY+=(mouseY-smoothPointerY)*Math.min(1,dt*inputFollow);
        const targetX=edition==='free'?-.22:edition==='pro'?.22:smoothPointerX*.3;
        const rotationFollow=3;
        group.rotation.y+=(targetX-group.rotation.y)*Math.min(1,dt*rotationFollow);
        group.rotation.x+=(smoothPointerY*.18-group.rotation.x)*Math.min(1,dt*rotationFollow);
        group.position.y=Math.sin(elapsed*.42)*.008;
        pointMaterial.uniforms.uTime.value=elapsed;
        landscapeMaterial.uniforms.uTime.value=elapsed;
        blendMaterial.uniforms.uTime.value=elapsed;beaconMaterial.uniforms.uTime.value=elapsed;trafficMaterial.uniforms.uTime.value=elapsed;skyMaterial.uniforms.uTime.value=elapsed;
        landscapeLights.position.x=-smoothPointerX*.075;landscapeLights.position.y=smoothPointerY*.018;
        landscapeBlend.position.x=landscapeLights.position.x;cityBeacons.position.x=landscapeLights.position.x;trafficLights.position.x=landscapeLights.position.x;skyStars.position.x=-smoothPointerX*.025;
        updateShootingStars();
        cursorEnergy=Math.max(0,cursorEnergy-dt*.75);
        const dissolveTarget=Math.min(.58,Math.max(edition?.42:.055,cursorEnergy*.5));
        const dissolveSpeed=dissolveTarget<dissolve?6:1.75;
        dissolve+=(dissolveTarget-dissolve)*Math.min(1,dt*dissolveSpeed);
        pointMaterial.uniforms.uDissolve.value=dissolve;
        const power=edition==='pro'?1.28:edition==='free'?.7:1;
        pointMaterial.uniforms.uPower.value+=(power-pointMaterial.uniforms.uPower.value)*Math.min(1,dt*3);
        topologyMaterial.uniforms.uPower.value+=(power-topologyMaterial.uniforms.uPower.value)*Math.min(1,dt*3);
        const eyePulse=1+Math.sin(elapsed*1.8)*.025+(edition==='pro'?.055:0);
        eyes.children.forEach(eye=>eye.scale.setScalar(eye.userData.baseSize*eyePulse));
        dust.position.x=-smoothPointerX*.06;
        dust.position.y=smoothPointerY*.03;
      }
      renderer.render(scene,camera);
    }
    function syncLoop(){renderer.setAnimationLoop(!paused&&visible&&!document.hidden?render:null);render(lastTime)}
    const onReduced=()=>{paused=reduced.matches;syncLoop()};reduced.addEventListener('change',onReduced);
    const onVisibility=()=>syncLoop();document.addEventListener('visibilitychange',onVisibility);
    const onPointer=e=>{const nextX=Math.max(-1,Math.min(1,e.clientX/innerWidth*2-1));const nextY=Math.max(-1,Math.min(1,e.clientY/innerHeight*2-1));if(hasPointer)cursorEnergy=Math.min(1,cursorEnergy+Math.hypot(nextX-lastPointerX,nextY-lastPointerY)*.34);else hasPointer=true;lastPointerX=nextX;lastPointerY=nextY;mouseX=nextX;mouseY=nextY};
    window.addEventListener('pointermove',onPointer,{passive:true});
    const controls=new AbortController();
    document.querySelectorAll('[data-edition]').forEach(card=>{for(const event of ['pointerenter','focusin'])card.addEventListener(event,()=>{edition=card.dataset.edition},{signal:controls.signal});for(const event of ['pointerleave','focusout'])card.addEventListener(event,()=>{edition=''},{signal:controls.signal})});
    const observer=new IntersectionObserver(([entry])=>{visible=entry.isIntersecting;syncLoop()},{rootMargin:'80px'});observer.observe(canvas);
    const onLost=e=>{e.preventDefault();renderer.setAnimationLoop(null);void initCanvasHead({sourceCanvas:canvas,stage,fallback})};canvas.addEventListener('webglcontextlost',onLost);
    resize();syncLoop();
    stage.dataset.headRenderer='webgl';
    stage.dataset.eyeContract='edge-shared-webgl';
    stage.dataset.headReady='1';
    const cleanup=()=>{if(disposed)return;disposed=true;renderer.setAnimationLoop(null);observer.disconnect();ro.disconnect();controls.abort();window.removeEventListener('pointermove',onPointer);document.removeEventListener('visibilitychange',onVisibility);reduced.removeEventListener('change',onReduced);geometries.forEach(g=>g.dispose());materials.forEach(m=>m.dispose());renderer.dispose()};
    window.addEventListener('pagehide',cleanup,{once:true});
    if(import.meta.hot)import.meta.hot.dispose(cleanup);
  }catch(error){ro.disconnect();renderer.dispose();console.warn('WebGL-Kopf nicht verfügbar – Canvas2D-Kopf wird verwendet.',error);await initCanvasHead({sourceCanvas:canvas,stage,fallback})}
}