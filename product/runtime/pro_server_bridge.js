/* PromptMaster Pro runtime bridge.
 * The byte-exact Golden Master remains untouched. This bridge is appended to a
 * derived runtime asset. At runtime it replaces the embedded catalog with the
 * authoritative published PromptDomain catalog, then routes composition and
 * ratings through the reviewed server domain. __PM_CSRF_TOKEN__ is replaced
 * per response by Django.
 */
(function(){
  'use strict';
  const PM_CSRF='__PM_CSRF_TOKEN__';
  const GROUP_META={
    m365:{title:'Microsoft 365 Anwendungen',copy:'Microsoft-365-Apps und direkte Copilot-Oberflächen'},
    power:{title:'Power Platform & Data',copy:'Power Platform, Power BI, Fabric und Copilot Studio'},
    business:{title:'Business, Security & Development',copy:'Dynamics, Security, Azure, GitHub und Viva'}
  };
  let centralCatalogReady=false;
  let centralCatalogError='';
  let requestSeq=0;
  let requestTimer=null;
  let lastComposedTask='';
  let lastRatingStars=0;

  function setProgress(pct){
    pct=Math.max(0,Math.min(100,Number(pct)||0));
    $('progressBar').style.width=pct+'%';
    $('progressText').textContent=pct+' %';
    $('bottomProgressBar').style.width=pct+'%';
    $('bottomProgressText').textContent=pct+' %';
  }

  function setCatalogMessage(title,copy){
    const catalog=$('catalog');
    if(!catalog)return;
    catalog.innerHTML=`<div class="notice"><strong>${esc(title)}</strong>${copy?`<div style="margin-top:5px">${esc(copy)}</div>`:''}</div>`;
  }

  function localProgress(){
    const t=taskObj();
    const steps=[!!selectedApp,!!selectedTask];
    if(t){
      (t.required||[]).forEach((label,i)=>steps.push(!!(inputValues[key('r',i)]||'').trim()));
      if(!taskHasOwnAudience(t))steps.push(!!audience());
      steps.push(focuses().length>0);
      steps.push(!!$('detailSelect').value);
      steps.push(!!$('formatSelect').value);
      steps.push(!!$('toneSelect').value);
    }
    return steps.length?Math.round((steps.filter(Boolean).length/steps.length)*100):0;
  }

  function inputPayload(){
    const t=taskObj();
    collect();
    const fields={};
    if(t){
      (t.required||[]).forEach((label,i)=>{ const v=(inputValues[key('r',i)]||'').trim(); if(v)fields[label]=v; });
      (t.optional||[]).forEach((label,i)=>{ const v=(inputValues[key('o',i)]||'').trim(); if(v)fields[label]=v; });
    }
    return {
      fields,
      audience: audience(),
      focus: focuses(),
      output: $('formatSelect').value,
      source: $('sourceSelect').value,
      tone: $('toneSelect').value,
      detail: $('detailSelect').value
    };
  }

  async function jsonRequest(url, options){
    const response=await fetch(url,{
      credentials:'same-origin',
      cache:'no-store',
      ...(options||{})
    });
    let data={};
    try{ data=await response.json(); }catch(_e){ /* handled below */ }
    if(!response.ok || !data.ok){
      const message=data?.error?.message || `Serverfehler (${response.status})`;
      const error=new Error(message);
      error.status=response.status;
      error.code=data?.error?.code || 'server_error';
      throw error;
    }
    return data;
  }

  async function jsonPost(url, body){
    return jsonRequest(url,{
      method:'POST',
      headers:{
        'Content-Type':'application/json',
        'X-CSRFToken':PM_CSRF,
        'X-Requested-With':'XMLHttpRequest'
      },
      body:JSON.stringify(body)
    });
  }

  function clearObject(obj){
    Object.keys(obj).forEach(key=>delete obj[key]);
  }

  function applyCentralCatalog(catalog){
    const applications=Array.isArray(catalog?.applications)?catalog.applications:[];
    const declaredApps=Number(catalog?.application_count||0);
    const declaredTasks=Number(catalog?.task_count||0);
    const actualTasks=applications.reduce((sum,a)=>sum+(Array.isArray(a.tasks)?a.tasks.length:0),0);
    if(!applications.length || declaredApps!==applications.length || declaredTasks!==actualTasks){
      throw new Error('Zentraler Prompt-Katalog ist unvollständig.');
    }

    clearObject(APP);
    clearObject(ACCESS_RULES);
    clearObject(TASK_ACCESS_RULES);
    if(typeof SRC_LABEL==='object' && catalog.source_labels){
      clearObject(SRC_LABEL);
      Object.assign(SRC_LABEL,catalog.source_labels);
    }

    for(const sourceApp of applications){
      if(!sourceApp?.code || !Array.isArray(sourceApp.tasks))continue;
      const tasks=sourceApp.tasks.filter(task=>task?.promptmaster_entitled!==false).map(task=>({
        id:String(task.id||''),
        title:String(task.title||task.id||''),
        intent:String(task.intent||''),
        required:Array.isArray(task.required)?task.required:[],
        optional:Array.isArray(task.optional)?task.optional:[],
        area:String(task.area||''),
        family:String(task.family||'analysis'),
        sources:Array.isArray(task.sources)?task.sources:[],
        outputs:Array.isArray(task.outputs)?task.outputs:[],
        access:task.access??null,
        status:task.status??null,
        maxChars:task.maxChars??null,
        focus:Array.isArray(task.focus)?task.focus:[],
        audiences:Array.isArray(task.audiences)?task.audiences:[],
        promptVersion:task.prompt_version??null,
        policyVersion:task.policy_version??null,
        minimumTierRank:Number(task.minimum_tier_rank||0)
      })).filter(task=>task.id);
      if(!tasks.length)continue;

      APP[sourceApp.code]={
        name:String(sourceApp.name||sourceApp.code),
        group:String(sourceApp.group||'m365'),
        icon:String(sourceApp.icon||''),
        color:String(sourceApp.color||'#0c71c3'),
        copy:String(sourceApp.copy||''),
        access:String(sourceApp.access||''),
        status:String(sourceApp.status||''),
        target:String(sourceApp.target||sourceApp.name||sourceApp.code),
        rule:String(sourceApp.rule||''),
        evidence:Array.isArray(sourceApp.evidence)?sourceApp.evidence:[],
        sortOrder:Number(sourceApp.sort_order||0),
        tasks
      };
      const appRank=Number(sourceApp.minimum_tier_rank||0);
      if(appRank>0)ACCESS_RULES[sourceApp.code]={tier:appRank};
      for(const task of tasks){
        if(task.minimumTierRank>0)TASK_ACCESS_RULES[task.id]={tier:task.minimumTierRank};
      }
    }

    const loadedApps=Object.keys(APP).length;
    const loadedTasks=Object.values(APP).reduce((sum,a)=>sum+a.tasks.length,0);
    if(loadedApps!==declaredApps || loadedTasks!==declaredTasks){
      throw new Error(`Produktentitlements ergaben nur ${loadedApps}/${loadedTasks} statt ${declaredApps}/${declaredTasks}.`);
    }
  }

  function dynamicCatalogBlock(title,copy,entries){
    return `<div class="catalog-block"><div class="catalog-title"><div><h3>${esc(title)}</h3>${copy?`<p>${esc(copy)}</p>`:''}</div></div><div class="apps">${entries.map(([id,a])=>appCardHtml(id,a)).join('')}</div></div>`;
  }

  function centralRenderCatalog(){
    if(!centralCatalogReady){
      setCatalogMessage(
        centralCatalogError?'Prompt-Katalog nicht verfügbar':'Prompt-Katalog wird geladen …',
        centralCatalogError||'Die freigegebenen Apps und Aufgaben werden serverseitig geladen.'
      );
      return;
    }
    const groups=new Map();
    for(const [id,a] of Object.entries(APP).sort((left,right)=>(left[1].sortOrder||0)-(right[1].sortOrder||0))){
      const code=a.group||'other';
      if(!groups.has(code))groups.set(code,[]);
      groups.get(code).push([id,a]);
    }
    let out='';
    for(const [code,entries] of groups){
      const meta=GROUP_META[code]||{title:code==='other'?'Weitere Anwendungen':code,copy:''};
      out+=dynamicCatalogBlock(meta.title,meta.copy,entries);
    }
    $('catalog').innerHTML=out || '<div class="notice"><strong>Keine freigeschalteten Anwendungen.</strong></div>';
  }

  async function hydrateCentralCatalog(){
    centralCatalogReady=false;
    centralCatalogError='';
    renderCatalog=centralRenderCatalog;
    renderCatalog();
    try{
      const data=await jsonRequest('/api/v1/prompts/?product=PRO');
      applyCentralCatalog(data.catalog);
      centralCatalogReady=true;
      centralCatalogError='';
      selectedApp='';
      selectedTask='';
      Object.keys(inputValues).forEach(key=>delete inputValues[key]);
      ['taskSection','inputSection','audienceSection','focusSection','outputSection'].forEach(id=>show(id,false));
      renderCatalog();
      update();
    }catch(error){
      centralCatalogReady=false;
      centralCatalogError=error.message||'Unbekannter Fehler';
      selectedApp='';
      selectedTask='';
      renderCatalog();
      $('promptOutput').value='';
      $('promptStatus').textContent='KATALOG NICHT VERFÜGBAR';
      $('promptStatus').className='status wait';
      $('copyBtn').disabled=true;
      $('charInfo').textContent=centralCatalogError;
    }
  }

  function ensureRatingUi(){
    if(document.getElementById('pmRatingButton'))return;
    const actions=document.querySelector('.actions');
    if(!actions)return;
    const wrap=document.createElement('div');
    wrap.id='pmRatingWrap';
    wrap.style.cssText='margin-top:12px;border-top:1px solid #d8dde1;padding-top:12px;font-size:11px;';
    wrap.innerHTML=`
      <button type="button" class="btn secondary" id="pmRatingButton">Prompt bewerten</button>
      <div id="pmRatingPanel" class="hidden" style="margin-top:10px">
        <div style="font-weight:700;margin-bottom:7px">Wie hilfreich war dieser Prompt?</div>
        <div id="pmStars" style="display:flex;gap:6px;flex-wrap:wrap">
          ${[1,2,3,4,5].map(n=>`<button type="button" class="btn secondary" data-pm-stars="${n}" style="min-width:42px">${n} ★</button>`).join('')}
        </div>
        <button type="button" class="btn secondary hidden" id="pmFeedbackReveal" style="margin-top:10px">Feedback ergänzen</button>
        <div id="pmFeedback" class="hidden" style="margin-top:10px">
          <label for="pmFeedbackText" style="display:block;font-weight:700;margin-bottom:5px">Optional: Was sollten wir verbessern?</label>
          <textarea id="pmFeedbackText" rows="4" style="width:100%;border:1px solid #bbc7cf;border-radius:11px;padding:10px"></textarea>
          <button type="button" class="btn secondary" id="pmFeedbackSend" style="margin-top:7px">Feedback senden</button>
        </div>
        <div id="pmRatingState" style="margin-top:8px;color:#68747c"></div>
      </div>`;
    actions.parentNode.insertBefore(wrap,actions.nextSibling);
    document.getElementById('pmRatingButton').addEventListener('click',()=>{
      document.getElementById('pmRatingPanel').classList.toggle('hidden');
    });
    document.getElementById('pmStars').addEventListener('click',async e=>{
      const button=e.target.closest('[data-pm-stars]');
      if(!button || !lastComposedTask)return;
      lastRatingStars=Number(button.dataset.pmStars);
      const state=document.getElementById('pmRatingState');
      state.textContent='Bewertung wird gespeichert …';
      try{
        await jsonPost(`/api/v1/prompts/${encodeURIComponent(lastComposedTask)}/rating/`,{stars:lastRatingStars});
        state.textContent=`${lastRatingStars} ★ gespeichert.`;
        const lowRating=lastRatingStars>=1 && lastRatingStars<=3;
        document.getElementById('pmFeedbackReveal').classList.toggle('hidden',!lowRating);
        document.getElementById('pmFeedback').classList.add('hidden');
      }catch(error){
        state.textContent='Bewertung konnte nicht gespeichert werden: '+error.message;
      }
    });
    document.getElementById('pmFeedbackReveal').addEventListener('click',()=>{
      if(lastRatingStars>=1 && lastRatingStars<=3){
        document.getElementById('pmFeedback').classList.remove('hidden');
        document.getElementById('pmFeedbackText').focus();
      }
    });
    document.getElementById('pmFeedbackSend').addEventListener('click',async()=>{
      if(!lastComposedTask || lastRatingStars<1 || lastRatingStars>3)return;
      const state=document.getElementById('pmRatingState');
      const feedback=document.getElementById('pmFeedbackText').value.trim();
      state.textContent='Feedback wird gespeichert …';
      try{
        await jsonPost(`/api/v1/prompts/${encodeURIComponent(lastComposedTask)}/rating/`,{stars:lastRatingStars,feedback});
        state.textContent='Bewertung und optionales Feedback wurden gespeichert.';
      }catch(error){
        state.textContent='Feedback konnte nicht gespeichert werden: '+error.message;
      }
    });
  }

  function resetRatingState(){
    lastComposedTask='';
    lastRatingStars=0;
    const panel=document.getElementById('pmRatingPanel');
    if(panel)panel.classList.add('hidden');
    const reveal=document.getElementById('pmFeedbackReveal');
    if(reveal)reveal.classList.add('hidden');
    const feedback=document.getElementById('pmFeedback');
    if(feedback)feedback.classList.add('hidden');
    const text=document.getElementById('pmFeedbackText');
    if(text)text.value='';
    const state=document.getElementById('pmRatingState');
    if(state)state.textContent='';
  }

  async function serverCompose(seq, taskId){
    try{
      const data=await jsonPost('/api/v1/prompts/compose/',{
        product:'PRO',
        task_id:taskId,
        microsoft_tier:msLicense(),
        input:inputPayload()
      });
      if(seq!==requestSeq || selectedTask!==taskId)return;
      const result=data.result;
      $('promptOutput').value=result.prompt || '';
      $('promptStatus').textContent=result.ready?'BEREIT ZUM KOPIEREN':'NOCH NICHT VOLLSTÄNDIG';
      $('promptStatus').className='status '+(result.ready?'ready':'wait');
      $('copyBtn').disabled=!result.ready;
      $('charInfo').textContent=result.prompt?`${result.prompt.length} Zeichen · Server v${result.prompt_version} / Policy v${result.policy_version}`:'';
      setProgress(result.progress_percent);
      lastComposedTask=taskId;
      ensureRatingUi();
    }catch(error){
      if(seq!==requestSeq || selectedTask!==taskId)return;
      $('promptOutput').value='';
      $('promptStatus').textContent='SERVER-PRÜFUNG FEHLGESCHLAGEN';
      $('promptStatus').className='status wait';
      $('copyBtn').disabled=true;
      $('charInfo').textContent=error.message;
      resetRatingState();
    }
  }

  update=function(){
    if(!centralCatalogReady){
      setProgress(0);
      $('promptOutput').value='';
      $('promptMeta').textContent='Zentraler Prompt-Katalog wird geladen.';
      $('promptStatus').textContent=centralCatalogError?'KATALOG NICHT VERFÜGBAR':'KATALOG WIRD GELADEN';
      $('promptStatus').className='status wait';
      $('copyBtn').disabled=true;
      $('charInfo').textContent=centralCatalogError;
      return;
    }
    const a=app(),t=taskObj();
    collect();
    $('promptMeta').textContent=t?`${a.name} · ${t.area} · ${t.title} · ${t.id}`:'Noch keine Aufgabe gewählt.';
    $('promptMode').textContent=a?('Für '+a.target+' optimiert'):'Für den ausgewählten Copilot-Bereich optimiert';
    setProgress(localProgress());
    requestSeq+=1;
    const seq=requestSeq;
    if(requestTimer){clearTimeout(requestTimer);requestTimer=null;}
    const ok=ready();
    if(!ok){
      $('promptOutput').value='';
      $('promptStatus').textContent='NOCH NICHT VOLLSTÄNDIG';
      $('promptStatus').className='status wait';
      $('copyBtn').disabled=true;
      $('charInfo').textContent='';
      resetRatingState();
      return;
    }
    const taskId=selectedTask;
    $('promptOutput').value='';
    $('promptStatus').textContent='WIRD SERVERSEITIG ERSTELLT';
    $('promptStatus').className='status wait';
    $('copyBtn').disabled=true;
    $('charInfo').textContent='Eingaben werden ausschließlich zur Prompt-Erzeugung verarbeitet und nicht als Promptinhalt gespeichert.';
    if(lastComposedTask!==taskId)resetRatingState();
    requestTimer=setTimeout(()=>serverCompose(seq,taskId),220);
  };

  // Initial Golden-Master rendering is replaced immediately and fail-closed
  // until the authoritative server catalog has been loaded.
  hydrateCentralCatalog();
})();
