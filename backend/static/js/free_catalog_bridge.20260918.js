/* PromptMaster Free catalog bridge.
 * The byte-exact FREE 1.2.4 Golden Master remains immutable. This additive
 * bridge updates only catalog visibility: the six reviewed Free apps/tasks
 * keep their existing local logic, while every other application from the
 * authoritative 34-app PromptDomain catalog is shown as a Pro-locked card.
 */
(function(){
  'use strict';

  const LEGACY_APP_IDS=['chat','outlook','teams','word','excel','powerpoint'];
  const CENTRAL_TO_LEGACY={
    copilot_chat:'chat',
    outlook:'outlook',
    teams:'teams',
    word:'word',
    excel:'excel',
    powerpoint:'powerpoint'
  };
  const centralBySyntheticId=new Map();
  let centralApplications=null;

  const html=(value)=>String(value??'')
    .replaceAll('&','&amp;')
    .replaceAll('<','&lt;')
    .replaceAll('>','&gt;')
    .replaceAll('"','&quot;')
    .replaceAll("'","&#39;");
  const safeColor=(value)=>/^#[0-9a-f]{3,8}$/i.test(String(value||''))?String(value):'#5c2d91';

  function syntheticId(code){return 'pmcentral:'+String(code||'');}

  function lockedAppHtml(sourceApp){
    const id=syntheticId(sourceApp.code);
    centralBySyntheticId.set(id,sourceApp);
    const color=safeColor(sourceApp.color);
    return '<div class="app locked" role="button" tabindex="0" data-appwrap="'+html(id)+'" data-central-code="'+html(sourceApp.code)+'" data-prolocked="1" data-licenselocked="0" aria-label="'+html((sourceApp.name||sourceApp.code)+' – PromptMaster Pro')+'">'
      +'<span class="app-card">'
      +'<span class="lock-pill">PRO</span>'
      +'<span class="app-icon" style="background:linear-gradient(180deg,'+color+','+color+'dd)">'+html(sourceApp.icon||String(sourceApp.name||'?').slice(0,1))+'</span>'
      +'<span class="app-name">'+html(sourceApp.name||sourceApp.code)+'</span>'
      +'<span class="app-copy">'+html(sourceApp.copy||'Weitere PromptMaster-Pro-Funktionen für diesen Copilot-Bereich.')+'</span>'
      +'<span class="app-footer"><span class="tag pro">PROMPTMASTER PRO</span></span>'
      +'</span></div>';
  }

  const originalShowProModal=showProModal;
  showProModal=function(appId){
    const sourceApp=centralBySyntheticId.get(appId);
    if(!sourceApp)return originalShowProModal(appId);
    document.getElementById('proModalTitle').textContent='CopilotPromptMaster Pro für '+(sourceApp.name||sourceApp.code);
    document.getElementById('proModalSubtitle').textContent='Dieser Bereich ist im vollständigen PromptMaster-Pro-Katalog enthalten.';
    document.getElementById('proModalList').innerHTML=[
      'aufgabenspezifische Prompt-Assistenten verwenden',
      'professionelle Ausgabeformate und Schwerpunkte nutzen',
      'den vollständigen, laufend weiterentwickelten Pro-Katalog verwenden'
    ].map(item=>'<li>'+html(item)+'</li>').join('');
    openModal('proModal');
  };

  function decorateLicenseLockedCards(){
    freeApps.querySelectorAll('[data-licenselocked="1"]').forEach(card=>{
      const appName=card.querySelector('.app-name')?.textContent?.trim()||'Diese Anwendung';
      card.setAttribute('role','button');
      card.setAttribute('tabindex','0');
      card.setAttribute('aria-label',appName+': erforderliche Microsoft-Copilot-Stufe anzeigen');
    });
  }

  const originalRenderApps=renderApps;
  renderApps=function(){
    if(!centralApplications){
      originalRenderApps();
      decorateLicenseLockedCards();
      return;
    }

    freeApps.innerHTML=LEGACY_APP_IDS.map(id=>appHtml(id,APP[id])).join('');
    decorateLicenseLockedCards();

    centralBySyntheticId.clear();
    const extras=centralApplications.filter(app=>!CENTRAL_TO_LEGACY[app.code]);
    proApps.innerHTML=extras.map(lockedAppHtml).join('');

    const overview=document.getElementById('proOverviewGrid');
    if(overview){
      overview.innerHTML=extras.map(app=>{
        const color=safeColor(app.color);
        return '<div class="pro-app-tile"><div class="pro-app-ico" style="background:'+color+'">'+html(app.icon||String(app.name||'?').slice(0,1))+'</div><div class="pro-app-name">'+html(app.name||app.code)+'</div></div>';
      }).join('');
    }
  };

  proApps.addEventListener('keydown',event=>{
    if(event.key!=='Enter' && event.key!==' ')return;
    const appWrap=event.target.closest('[data-central-code][data-prolocked="1"]');
    if(!appWrap)return;
    event.preventDefault();
    showProModal(appWrap.dataset.appwrap);
  });

  async function hydrateFreeCatalog(){
    try{
      const response=await fetch('/api/v1/prompts/?product=FREE',{credentials:'same-origin',cache:'no-store'});
      const data=await response.json();
      if(!response.ok||!data?.ok)throw new Error(data?.error?.message||'Katalog konnte nicht geladen werden.');
      const catalog=data.catalog||{};
      const apps=Array.isArray(catalog.applications)?catalog.applications:[];
      const count=Number(catalog.application_count||0);
      if(count!==34||apps.length!==34)throw new Error('Erwarteter 34-App-Katalog ist unvollständig.');

      for(const code of Object.keys(CENTRAL_TO_LEGACY)){
        if(!apps.some(app=>app.code===code))throw new Error('Free-Basis-App fehlt im zentralen Katalog: '+code);
      }
      const extras=apps.filter(app=>!CENTRAL_TO_LEGACY[app.code]);
      if(extras.length!==28)throw new Error('Erwartete 28 Pro-gesperrte Zusatzbereiche fehlen.');

      centralApplications=apps;
      renderApps();

      window.dispatchEvent(new CustomEvent('pm-free-catalog-ready',{
        detail:{applicationCount:apps.length,freeApplicationCount:6,lockedApplicationCount:extras.length}
      }));
    }catch(error){
      console.error('PromptMaster Free: zentraler Sichtbarkeitskatalog nicht verfügbar.',error);
      // Fail usable: FREE 1.2.4 remains functional with its immutable local
      // catalog. We never unlock a task because of a catalog fetch failure.
      centralApplications=null;
      originalRenderApps();
    }
  }

  const serverComposeMeta=document.querySelector('meta[name="pm-free-compose"][content="server"]');
  if(serverComposeMeta){
    const csrfToken=serverComposeMeta.dataset.csrf||'';
    let composeSequence=0;
    let composeTimer=null;

    document.body.dataset.pmFreeCompose='server';

    function freeServerInput(){
      return {
        primary:document.getElementById('goalInput')?.value?.trim()||'',
        secondary:document.getElementById('sourceContextInput')?.value?.trim()||'',
        audience:getAudience()?.[0]||'',
        focus:focusSelected(),
        output:document.getElementById('formatSelect')?.value||'',
        detail:document.getElementById('detailSelect')?.value||'',
        tone:document.getElementById('toneSelect')?.value||''
      };
    }

    function freeServerReady(_input){
      // Match the reviewed Free 1.2.4 interaction contract: the prompt grows
      // incrementally as soon as a task is selected. The server remains the
      // authoritative composer; result.ready controls whether copying is
      // enabled once every required selection is complete.
      const currentSpec=spec();
      const task=getTask();
      return Boolean(task&&currentSpec);
    }

    function showServerPending(){
      const output=document.getElementById('promptOutput');
      if(output){
        output.value='';
        output.dataset.source='database';
      }
      const state=document.getElementById('promptStatus');
      if(state){
        state.textContent='WIRD AUS DER PROMPT-DATENBANK ERSTELLT';
        state.className='status wait';
      }
      const copy=document.getElementById('copyBtn');
      if(copy)copy.disabled=true;
    }

    function showServerIncomplete(){
      const output=document.getElementById('promptOutput');
      if(output){
        output.value='';
        output.dataset.source='database';
      }
      const state=document.getElementById('promptStatus');
      if(state){
        state.textContent='NOCH NICHT VOLLSTÄNDIG';
        state.className='status wait';
      }
      const copy=document.getElementById('copyBtn');
      if(copy)copy.disabled=true;
    }

    async function composeFromDatabase(sequence,taskId,input){
      try{
        const response=await fetch('/api/v1/prompts/compose/',{
          method:'POST',
          credentials:'same-origin',
          cache:'no-store',
          headers:{
            'Accept':'application/json',
            'Content-Type':'application/json',
            'X-CSRFToken':csrfToken,
            'X-Requested-With':'XMLHttpRequest'
          },
          body:JSON.stringify({
            product:'FREE',
            task_id:taskId,
            microsoft_tier:msLicense(),
            input
          })
        });
        let data={};
        try{data=await response.json();}catch(_error){}
        if(sequence!==composeSequence||taskId!==selectedTask)return;
        if(!response.ok||!data?.ok){
          throw new Error(data?.error?.message||('Serverfehler ('+response.status+')'));
        }
        const result=data.result||{};
        const output=document.getElementById('promptOutput');
        if(output){
          output.value=result.prompt||'';
          output.dataset.source=result.source==='PromptLegacyContract'?'database':'server';
        }
        const state=document.getElementById('promptStatus');
        if(state){
          state.textContent=result.ready?'PROMPT BEREIT':'NOCH NICHT VOLLSTÄNDIG';
          state.className='status '+(result.ready?'ready':'wait');
        }
        const copy=document.getElementById('copyBtn');
        if(copy)copy.disabled=!result.ready;
      }catch(error){
        if(sequence!==composeSequence||taskId!==selectedTask)return;
        const output=document.getElementById('promptOutput');
        if(output){
          output.value='';
          output.dataset.source='database-error';
        }
        const state=document.getElementById('promptStatus');
        if(state){
          state.textContent='SERVER-PRÜFUNG FEHLGESCHLAGEN';
          state.className='status wait';
        }
        const copy=document.getElementById('copyBtn');
        if(copy)copy.disabled=true;
      }
    }

    function scheduleDatabaseCompose(){
      composeSequence+=1;
      const sequence=composeSequence;
      if(composeTimer){
        clearTimeout(composeTimer);
        composeTimer=null;
      }
      const input=freeServerInput();
      if(!freeServerReady(input)){
        showServerIncomplete();
        return;
      }
      const taskId=selectedTask;
      showServerPending();
      composeTimer=setTimeout(
        ()=>composeFromDatabase(sequence,taskId,input),
        180
      );
    }

    document.addEventListener('input',event=>{
      if(event.target.matches('#goalInput,#sourceContextInput'))scheduleDatabaseCompose();
    });
    document.addEventListener('change',event=>{
      if(event.target.matches(
        'input[name="mslicense"],input[name="app"],input[name="audience"],input[name="focus"],#detailSelect,#formatSelect,#toneSelect'
      )){
        setTimeout(scheduleDatabaseCompose,0);
      }
    });
    document.addEventListener('click',event=>{
      if(event.target.closest('.task,#resetBtn'))setTimeout(scheduleDatabaseCompose,0);
    });

    // The legacy inline composer runs during page parsing. Current Free must
    // never expose that local result as the authoritative V2 output.
    setTimeout(scheduleDatabaseCompose,0);
  }

  void hydrateFreeCatalog();
})();
