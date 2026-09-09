const $ = (selector, root = document) => root.querySelector(selector);
const esc = (value) => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const paths = {
  plus:'M12 5v14M5 12h14', grid:'M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h7v7h-7z',
  clock:'M12 8v5l3 2M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0',
  book:'M12 5C9 3 5 3 3 4v15c3-1 6-1 9 1m0-15c3-2 7-2 9-1v15c-3-1-6-1-9 1V5',
  shield:'M12 3l8 3v6c0 5-8 9-8 9s-8-4-8-9V6l8-3M8 12l3 3 5-6',
  settings:'M4 7h16M4 17h16M8 4v6M16 14v6',
  file:'M14 3H5v18h14V8l-5-5v5h5M8 12h8M8 16h6',
  upload:'M12 16V3M7 8l5-5 5 5M4 15v5h16v-5',
  arrow:'M4 12h16M14 6l6 6-6 6', check:'M5 12l4 4L19 6', close:'M6 6l12 12M6 18L18 6',
  download:'M12 3v12M7 10l5 5 5-5M4 16v5h16v-5', layers:'M3 7l9-4 9 4-9 4-9-4M3 12l9 4 9-4M3 17l9 4 9-4',
  link:'M10 14l4-4M8 16l-1 1a4 4 0 0 1-6-6l5-5a4 4 0 0 1 6 0m0 12a4 4 0 0 0 6 0l5-5a4 4 0 0 0-6-6l-1 1',
  search:'M10 3a7 7 0 1 0 0 14 7 7 0 0 0 0-14M15 15l6 6',
  external:'M14 3h7v7M21 3l-11 11M10 4H4v16h16v-6',
  alert:'M12 3L2 21h20L12 3M12 9v5M12 17v1',
};
function icon(name) { return `<svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><path d="${paths[name] || paths.file}"/></svg>`; }
for (const node of document.querySelectorAll('[data-icon]')) node.innerHTML = icon(node.dataset.icon);
const statusNames = {running:'正在运行',completed:'生成完成',dry_run:'离线检查完成',failed:'运行失败',interrupted:'运行已中断',incomplete:'产物不完整'};
const stages = [
  ['literature_manager','文献整理','去重、归一化与固定论文集'],
  ['paper_reader','论文阅读','逐篇提取方法、发现与证据'],
  ['knowledge_organizer','知识组织','构建跨论文的研究脉络'],
  ['outline_planner','大纲规划','关联章节目的与核心文献'],
  ['survey_writer','综述写作','基于本节证据生成内容'],
  ['citation_verifier','引用核验','验证论断与原文是否一致'],
  ['finalize','产物导出','保存 Survey 与证据映射'],
];
const state = {
  runs:[], settings:null, detail:null, tab:'survey', evidenceFilter:'all', selectedPaper:null,
  draft:{topic:'',questions:'',file:null,mode:'generate'}, historySearch:'',historyStatus:'all',
  submitting:false, lastDetail:'', epoch:0,
};
function announce(message) { $('#announcement').textContent = message; }
async function api(path, options = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 20000);
  try {
    const response = await fetch(path, {...options, signal:controller.signal});
    const data = await response.json();
    if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : '请求未完成，请检查输入后重试。');
    return data;
  } catch (error) {
    if (error.name === 'AbortError') throw new Error('连接超时，请检查本地服务并重试。');
    if (error instanceof TypeError) throw new Error('无法连接本地服务，请确认工作台仍在运行。');
    throw error;
  } finally { clearTimeout(timeout); }
}
function badge(status) { return `<span class="badge ${esc(status)}">${icon(status==='completed'?'check':status==='failed'?'alert':'clock')}${esc(statusNames[status] || status)}</span>`; }
function date(value) { if (!value) return '日期未记录'; const parsed = new Date(value); return Number.isNaN(+parsed) ? '日期未记录' : parsed.toLocaleString('zh-CN',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'}); }
function routeInfo() {
  const parts = location.hash.slice(1).split('/');
  if(parts[0] === 'run' && parts[1]) return {page:'run',id:parts[1],tab:parts[2] || 'survey'};
  return {page:['new','history','settings'].includes(parts[0]) ? parts[0] : 'new'};
}
function sidebar() {
  $('#run-count').textContent = state.runs.length;
  $('#recent-runs').innerHTML = state.runs.length ? state.runs.slice(0,5).map(run=>`<a class="recent-link ${routeInfo().id===run.id?'active':''}" href="#run/${encodeURIComponent(run.id)}/survey" title="${esc(run.topic)}">${icon('file')}<span>${esc(run.topic)}</span></a>`).join('') : '<p class="small muted">你的第一份 Survey，<br>从一个研究问题开始。</p>';
  for(const link of document.querySelectorAll('[data-nav]')) {
    const active = link.dataset.nav === routeInfo().page;
    link.classList.toggle('active',active);
    if(active) link.setAttribute('aria-current','page'); else link.removeAttribute('aria-current');
  }
}
function connection(offline = false) {
  const node = $('#connection');
  node.textContent = offline ? '服务连接已断开' : state.settings?.configured ? `${state.settings.model} · 已配置` : '模型待配置 · 可离线检查';
  node.classList.toggle('warning',offline || !state.settings?.configured);
}
function stageRail(run = null) {
  const logs = run?.stages || [];
  const next = stages.findIndex(([id]) => !logs.some(log => log.stage === id));
  return `<section class="panel rail-panel"><div class="rail-title"><h2>${run?'执行进度':'Agent 工作流'}</h2>${icon('layers')}</div><p class="rail-subtitle">${run ? '按实际阶段日志更新，无模拟进度' : '七个阶段，串联一次完整研究'}</p><ol class="stage-list">${stages.map(([id,title,desc],i)=>{
    const log = logs.find(log=>log.stage===id);
    const stageStatus = log ? log.error ? 'failed' : 'done' : run?.status === 'running' && next === i ? 'current' : '';
    const label = log ? log.error ? '阶段失败' : `${run?.status==='dry_run'?'离线检查':'已结束'} · ${(Number(log.latency_ms)/1000).toFixed(1)}s` : stageStatus==='current'?'执行中…':run?'等待产物':desc;
    return `<li class="${stageStatus}"><span class="stage-node">${stageStatus==='done'?icon('check'):stageStatus==='failed'?icon('alert'):String(i+1).padStart(2,'0')}</span><div class="stage-copy"><strong>${title}</strong><small>${esc(label)}</small></div></li>`;
  }).join('')}</ol></section>`;
}
function outputNote() { return `<section class="output-note"><p class="eyebrow">BUILT ON EVIDENCE</p><h2>好的综述，<br>始于可追溯的证据。</h2><p>每个论断关联来源文献，每条引用经过证据核验。让理解与判断有据可依。</p><div class="output-tags"><span>Survey.md</span><span>Claims</span><span>Evidence Map</span></div></section>`; }
function runCard(run) { return `<a href="#run/${encodeURIComponent(run.id)}/survey" class="panel run-card"><span class="document-icon">${icon('file')}</span><div class="run-info"><h3>${esc(run.topic)}</h3><p><span>${esc(date(run.created_at))}</span><span>${run.paper_count} 篇文献</span><span class="mono">${esc(run.id)}</span></p></div>${badge(run.status)}</a>`; }
function renderNew() {
  $('#main').innerHTML = `<div class="page-heading"><div><p class="eyebrow">FROM PAPERS TO PERSPECTIVE</p><h1>让研究，从这里展开。</h1><p>带上你的研究主题与文献，让 Agent 梳理脉络、撰写综述、核验引用。</p></div><span class="edition mono">RESEARCH / 01</span></div>
  <div class="work-grid"><div><form id="new-form" class="panel"><div class="panel-head"><div class="label-row"><span class="step-number">01 /</span><h2>定义你的研究</h2></div><span class="badge">固定文献集</span></div><div class="form-body">
  <div id="form-error" hidden class="error-message" role="alert" tabindex="-1"></div>
  <div class="field"><label for="topic">研究主题<span class="required">*</span></label><textarea id="topic" name="topic" required maxlength="1000" rows="3" placeholder="例如：视觉语言模型在自动驾驶中的应用" aria-describedby="topic-hint">${esc(state.draft.topic)}</textarea><span class="hint" id="topic-hint">聚焦一个研究方向、技术问题或应用领域。</span></div>
  <div class="divider"></div><div class="field"><label for="paper-file">来源文献<span class="required">*</span></label><div id="upload-area" class="upload-area"><div id="upload-content"></div></div><input type="file" id="paper-file" accept=".json,.jsonl,.yaml,.yml" class="sr-only" aria-describedby="file-hint"><div class="upload-actions"><button type="button" class="button text-button" id="use-example">${icon('file')}试用合成示例文献${icon('arrow')}</button><span id="file-hint">支持 JSON / JSONL / YAML<br>最大 10 MB，最多 200 篇</span></div></div>
  <details class="advanced" ${state.draft.questions?'open':''}><summary>补充研究问题（可选）</summary><div class="field"><label for="questions">你希望综述回答哪些问题？</label><textarea id="questions" rows="3" maxlength="40000" placeholder="每行填写一个问题，例如：现有方法有哪些主要类别？" aria-describedby="questions-hint">${esc(state.draft.questions)}</textarea><span class="hint" id="questions-hint">最多 20 个问题，每个不超过 2000 字。</span></div></details>
  </div><div class="form-footer"><div class="mode-select"><label for="mode">运行方式</label><select id="mode"><option value="generate" ${state.draft.mode==='generate'?'selected':''}>生成 Survey · 调用模型</option><option value="dry_run" ${state.draft.mode==='dry_run'?'selected':''}>离线检查 · 不调用模型</option></select></div><button class="button primary" id="submit-run" type="submit">开始研究${icon('arrow')}</button></div></form>
  <div class="trust-row"><span>${icon('shield')}引用可追溯</span><span>${icon('layers')}全流程产物保留</span><span>${icon('book')}固定文献，可复现</span></div>
  <div class="section-title"><h2>最近的研究</h2><a href="#history">查看全部 ${icon('arrow')}</a></div><div id="home-recent" class="run-list">${homeRecent()}</div></div><aside class="rail" aria-label="研究流程说明">${stageRail()}${outputNote()}</aside></div>`;
  $('#topic').addEventListener('input',e=>{state.draft.topic=e.target.value;});
  $('#questions').addEventListener('input',e=>{state.draft.questions=e.target.value;});
  $('#mode').addEventListener('change',e=>{state.draft.mode=e.target.value; updateSubmit();});
  $('#paper-file').addEventListener('change',e=>loadFile(e.target.files[0]));
  $('#use-example').addEventListener('click',useExample);
  $('#new-form').addEventListener('submit',submit);
  const zone = $('#upload-area');
  zone.addEventListener('dragover',e=>{e.preventDefault();zone.classList.add('dragging');});
  zone.addEventListener('dragleave',()=>zone.classList.remove('dragging'));
  zone.addEventListener('drop',e=>{e.preventDefault();zone.classList.remove('dragging');loadFile(e.dataTransfer.files[0]);});
  renderUpload(); updateSubmit();
}
function homeRecent() { return state.runs.length ? state.runs.slice(0,2).map(runCard).join('') : `<div class="empty-inline">${icon('book')}<div><strong>还没有研究任务</strong><p>创建第一份 Survey，研究过程和结果会保存在这里。</p></div></div>`; }
function updateSubmit() {
  const button = $('#submit-run'); if(!button) return;
  button.disabled=state.submitting;
  button.innerHTML=state.submitting ? '正在创建任务…' : `${state.draft.mode==='dry_run'?'开始离线检查':'开始研究'}${icon('arrow')}`;
}
function renderUpload() {
  const file = state.draft.file;
  const node = $('#upload-content'); if(!node) return;
  if(!file) node.innerHTML=`<span class="upload-icon">${icon('upload')}</span><h3>将论文集拖放到这里</h3><p>包含论文标题、摘要或正文的结构化文献集</p><button type="button" id="choose-file" class="button">选择文件</button>`;
  else {
    let records=[];
    try { const parsed=JSON.parse(file.content); records=Array.isArray(parsed)?parsed:parsed.papers || []; } catch { /* YAML / JSONL 交由后端统一校验。 */ }
    const validRecords=Array.isArray(records)?records.filter(row=>row && typeof row==='object'):[];
    node.innerHTML=`<div class="file-selected">${icon('file')}<div class="file-info"><strong>${esc(file.name)}</strong><p>${(new TextEncoder().encode(file.content).length/1024).toFixed(1)} KB · ${validRecords.length?`${validRecords.length} 条记录，提交时去重校验`:'提交时校验论文集'}</p></div><button type="button" id="remove-file" class="button text-button" aria-label="移除论文文件">${icon('close')}</button></div>${validRecords.length?`<div class="preview-list">${validRecords.slice(0,3).map((p,i)=>`<p><span class="mono">${String(i+1).padStart(2,'0')}</span> &nbsp; ${esc(p.title || '缺少标题')}</p>`).join('')}${validRecords.length>3?`<p>另有 ${validRecords.length-3} 条记录</p>`:''}</div>`:''}${file.example?'<p class="hint">合成示例，仅用于离线调试，不是真实文献。</p>':''}`;
    $('#remove-file').onclick=()=>{state.draft.file=null;$('#paper-file').value='';renderUpload();$('#choose-file').focus();};
  }
  if($('#choose-file')) $('#choose-file').onclick=()=>$('#paper-file').click();
}
function formError(message) {
  const node=$('#form-error'); if(!node) { announce(message); return; }
  node.textContent=message;node.hidden=false;node.focus();
}
async function loadFile(file) {
  if(!file) return;
  if(file.size>10_000_000) return formError('文件超过 10 MB，请拆分论文集后重新上传。');
  if(!/\.(json|jsonl|ya?ml)$/i.test(file.name)) return formError('请选择 JSON、JSONL 或 YAML 论文集。当前不直接解析 PDF。');
  try { state.draft.file={name:file.name,content:await file.text()};renderUpload();announce(`已选择论文集 ${file.name}`); }
  catch { formError('无法读取文件，请重新选择。'); }
}
async function useExample() {
  const button=$('#use-example');button.disabled=true;
  try {
    const example=await api('/api/example');
    state.draft.file={name:example.filename,content:example.content,example:true};
    if(!state.draft.topic) state.draft.topic='Vision-Language Models for Autonomous Driving';
    state.draft.mode='dry_run';
    if(routeInfo().page==='new') { $('#topic').value=state.draft.topic;$('#mode').value='dry_run';renderUpload();updateSubmit(); }
    announce('已加载合成示例，并切换为不调用模型的离线检查。');
  } catch(error) { formError(error.message); } finally { button.disabled=false; }
}
async function submit(event) {
  event.preventDefault(); if(state.submitting) return;
  if(!state.draft.topic.trim()) return formError('请填写研究主题。');
  if(!state.draft.file) return formError('请选择来源文献文件，或使用合成示例进行离线检查。');
  const questions=state.draft.questions.split('\n').map(q=>q.trim()).filter(Boolean);
  if(questions.length>20 || questions.some(q=>q.length>2000)) return formError('最多支持 20 个研究问题，每个不超过 2000 字。');
  state.submitting=true;updateSubmit();$('#form-error').hidden=true;
  try {
    const result=await api('/api/runs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({topic:state.draft.topic,research_questions:questions,filename:state.draft.file.name,content:state.draft.file.content,mode:state.draft.mode})});
    location.hash=`run/${encodeURIComponent(result.id)}/survey`;announce('研究任务已创建，后台开始执行。');
  } catch(error) { formError(error.message); } finally {state.submitting=false;updateSubmit();}
}
function renderHistory() {
  $('#main').innerHTML=`<div class="page-heading"><div><p class="eyebrow">YOUR RESEARCH LIBRARY</p><h1>每次探索，都有迹可循。</h1><p>回到已有研究，查看生成结果、执行记录与引用证据。</p></div><a class="button primary" href="#new">${icon('plus')}新建 Survey</a></div><div class="history-tools"><label class="sr-only" for="history-search">搜索主题或任务 ID</label><input class="text-input" id="history-search" placeholder="搜索研究主题或任务 ID…" value="${esc(state.historySearch)}"><label class="sr-only" for="history-status">筛选运行状态</label><select id="history-status"><option value="all">全部状态</option>${Object.entries(statusNames).map(([value,label])=>`<option value="${value}" ${state.historyStatus===value?'selected':''}>${label}</option>`).join('')}</select></div><div class="run-list" id="history-list"></div>`;
  $('#history-search').oninput=e=>{state.historySearch=e.target.value;renderHistoryList();};
  $('#history-status').onchange=e=>{state.historyStatus=e.target.value;renderHistoryList();};
  renderHistoryList();
}
function renderHistoryList() {
  const runs=state.runs.filter(run=>(run.topic+' '+run.id).toLowerCase().includes(state.historySearch.toLowerCase()) && (state.historyStatus==='all'||run.status===state.historyStatus));
  $('#history-list').innerHTML=runs.length?runs.map(runCard).join(''):`<div class="panel empty-state">${icon('search')}<h2>${state.runs.length?'没有匹配的研究':'你的研究档案，等待开启'}</h2><p>${state.runs.length?'尝试更换关键词或运行状态。':'创建任务后，你可以随时回到这里查看结果。'}</p>${state.runs.length?'':'<a class="button primary" href="#new">创建第一份 Survey</a>'}</div>`;
}
function downloadUrl(name) { return `/api/runs/${encodeURIComponent(state.detail.id)}/files/${encodeURIComponent(name)}`; }
function renderDetail() {
  const run=state.detail,a=run.artifacts,summary=run.verification || {};
  const total=summary.total_claims || 0;
  const duration=run.stages.reduce((sum,row)=>sum+Number(row.latency_ms || 0),0)/1000;
  let notice='';
  if(run.status==='dry_run') notice='离线检查已完成：仅校验输入和渲染 Prompt，未调用模型，也未生成 Survey 或进行真实引用核验。';
  if(run.status==='running') notice='研究正在后台执行。你可以切换页面；关闭或停止服务会中断当前运行。';
  if(['failed','interrupted','incomplete'].includes(run.status)) notice='本次运行未完成。已保存的阶段产物仍可查看；请检查运行配置和本地阶段日志，修正后创建新任务。';
  if(run.status==='completed' && (!total || summary.unsupported || summary.unverifiable)) notice='Survey 已生成，部分论断缺少支持或尚无法核验。请在「证据核验」中查看，再用于研究写作。';
  $('#main').innerHTML=`<div class="page-heading run-heading"><div><p class="eyebrow mono">${esc(run.id)}</p><h1>${esc(run.topic)}</h1><div class="run-subtitle">${badge(run.status)}<span class="muted small">${esc(date(run.created_at))}</span></div></div><div class="detail-actions">${a['final.md']?`<a class="button primary" href="${downloadUrl('final.md')}">${icon('download')}导出 Markdown</a>`:''}<a class="button" href="#new">${icon('plus')}新建研究</a></div></div>${notice?`<div class="notice" role="status">${esc(notice)}</div>`:''}
  <div class="work-grid"><div><div class="metrics"><div class="metric"><label>来源文献</label><strong>${run.paper_count}<small> 篇</small></strong><small>固定 Source Paper Set</small></div><div class="metric"><label>论断获得支持</label><strong>${total?`${summary.supported || 0}<small> / ${total}</small>`:'—'}</strong><small>${total?'按 Claim 聚合核验结果':'尚无核验结果'}</small></div><div class="metric"><label>阶段累计耗时</label><strong>${duration.toFixed(1)}<small> s</small></strong><small>仅统计已落盘的阶段</small></div></div>
  <section class="panel"><div class="tabs" role="tablist" aria-label="研究产物">${[['survey','综述正文'],['outline','研究大纲'],['papers','来源文献'],['evidence','证据核验'],['artifacts','运行产物']].map(([id,label])=>`<button type="button" role="tab" id="tab-${id}" aria-controls="tab-content" aria-selected="${state.tab===id}" tabindex="${state.tab===id?0:-1}" data-tab="${id}" class="${state.tab===id?'active':''}">${label}</button>`).join('')}</div><div id="tab-content" class="tab-content" role="tabpanel" aria-labelledby="tab-${state.tab}" tabindex="0"></div></section></div><aside class="rail" aria-label="执行与引用证据">${stageRail(run)}<section class="panel rail-panel evidence-rail" id="evidence-rail" tabindex="-1"></section></aside></div>`;
  for(const button of document.querySelectorAll('[data-tab]')) {
    button.onclick=()=>{location.hash=`run/${encodeURIComponent(run.id)}/${button.dataset.tab}`;};
    button.onkeydown=e=>{
      const buttons=[...document.querySelectorAll('[data-tab]')];let index=buttons.indexOf(button);
      if(e.key==='ArrowRight') index=(index+1)%buttons.length;
      else if(e.key==='ArrowLeft') index=(index-1+buttons.length)%buttons.length;
      else if(e.key==='Home') index=0; else if(e.key==='End') index=buttons.length-1; else return;
      e.preventDefault();buttons[index].focus();buttons[index].click();
    };
  }
  renderTab();renderEvidenceRail();
}
function emptyContent(title,description) { return `<div class="empty-state">${icon('book')}<h2>${title}</h2><p>${description}</p></div>`; }
function papersList() { const raw=state.detail.artifacts['papers.json'] || [];return Array.isArray(raw)?raw:raw.papers || []; }
function citationMap() { const a=state.detail.artifacts;return a['claims.json']?.citation_map || a['result.json']?.citations || []; }
function citationLabel(paperId) { const hit=citationMap().find(c=>c.paper_id===paperId);return hit?.citation_id || paperId || '无引用'; }
function renderTab() {
  const run=state.detail,a=run.artifacts,node=$('#tab-content');
  if(state.tab==='survey') {
    node.innerHTML=run.survey_html ? `<article class="prose">${run.survey_html}</article>` : emptyContent(run.status==='dry_run'?'离线检查不生成正文':'Survey 正在等待生成',run.status==='running'?'完成综述写作后，正文会自动显示在这里。':'你可以查看已有运行产物，或新建任务生成 Survey。');
    for(const link of node.querySelectorAll('.prose a')) {link.target='_blank';link.rel='noopener noreferrer';}
    const citations=citationMap();
    if(run.survey_html) {
      const walker=document.createTreeWalker($('.prose',node),NodeFilter.SHOW_TEXT);
      const texts=[];while(walker.nextNode()) if(!walker.currentNode.parentElement.closest('a,button,code,pre')) texts.push(walker.currentNode);
      for(const text of texts) {
        if(!/\[\d+\]/.test(text.textContent)) continue;
        const fragment=document.createDocumentFragment();let offset=0;
        for(const match of text.textContent.matchAll(/\[\d+\]/g)) {
          fragment.append(document.createTextNode(text.textContent.slice(offset,match.index)));
          const citation=citations.find(c=>c.citation_id===match[0]);
          if(citation) { const button=document.createElement('button');button.type='button';button.className='citation-link';button.textContent=match[0];button.setAttribute('aria-label',`查看引用 ${match[0]}：${citation.title || citation.paper_id}`);button.onclick=()=>selectPaper(citation.paper_id);fragment.append(button); }
          else fragment.append(document.createTextNode(match[0]));
          offset=match.index+match[0].length;
        }
        fragment.append(document.createTextNode(text.textContent.slice(offset)));text.replaceWith(fragment);
      }
    }
  } else if(state.tab==='outline') {
    const sections=a['outline.json']?.sections || [];
    node.innerHTML=sections.length?sections.map((section,i)=>`<div class="outline-row"><span class="step-number">${String(i+1).padStart(2,'0')}</span><div><h3>${esc(section.title)}</h3><p>${esc(section.purpose)}</p><div>${(section.papers || []).map(id=>`<span class="paper-chip mono">${esc(id)}</span>`).join('')}</div></div></div>`).join(''):emptyContent('大纲尚未生成','知识组织完成后，Agent 会规划章节并关联证据。');
  } else if(state.tab==='papers') {
    node.innerHTML=papersList().map(p=>`<section class="paper-row"><span class="badge mono">${esc(p.paper_id)}</span><h3>${esc(p.title)}</h3><p>${esc((p.authors || []).join(' · '))} ${p.year?`/ ${esc(p.year)}`:''}</p><p class="paper-abstract">${esc(p.abstract || '未提供摘要；可在运行产物中下载完整论文数据。')}</p><button class="button text-button" data-paper="${esc(p.paper_id)}">${icon('link')}查看相关证据</button></section>`).join('') || emptyContent('暂无来源文献','论文集会在文献整理阶段保存。');
    for(const button of node.querySelectorAll('[data-paper]')) button.onclick=()=>selectPaper(button.dataset.paper);
  } else if(state.tab==='evidence') {
    node.innerHTML=`<div class="evidence-filter"><label for="evidence-filter">Claim → Paper → Evidence</label><select id="evidence-filter"><option value="all">全部核验结果</option><option value="supported">证据支持</option><option value="unsupported">证据不支持</option><option value="unknown">无法核验</option></select></div><div id="evidence-list"></div>`;
    $('#evidence-filter').value=state.evidenceFilter;
    $('#evidence-filter').onchange=e=>{state.evidenceFilter=e.target.value;renderEvidenceList();};renderEvidenceList();
  } else {
    const labels={'task.json':'研究任务','papers.json':'来源文献','analyses.json':'逐篇分析','knowledge.json':'研究知识结构','outline.json':'章节规划','draft.md':'综述草稿','claims.json':'论断与引用映射','verification.json':'证据核验结果','final.md':'最终综述','result.json':'评测接口结果'};
    node.innerHTML=Object.entries(labels).filter(([name])=>name in a).map(([name,label])=>`<div class="artifact-row"><div><strong>${label}</strong><small class="mono">${name}</small></div><a class="button" href="${downloadUrl(name)}" aria-label="下载${label}">${icon('download')}下载</a></div>`).join('') || emptyContent('尚无运行产物','阶段完成后会自动保存并显示在这里。');
  }
}
function verificationRows() { return state.detail.artifacts['verification.json']?.results || []; }
function supportLabel(value) { return value===true?'证据支持':value===false?'证据不支持':'无法核验'; }
function evidenceCard(row) {
  const claims=state.detail.artifacts['claims.json']?.claims || [];
  const claim=claims.find(c=>c.claim_id===row.claim_id);
  return `<section class="evidence-card"><div class="evidence-head"><span class="mono">${esc(row.claim_id)} → ${esc(row.citation?citationLabel(row.citation):'无引用')}</span><span class="badge ${row.support===true?'completed':row.support===false?'failed':'incomplete'}">${supportLabel(row.support)}</span></div><p>${esc(claim?.text || '未找到对应论断文本')}</p>${row.evidence?`<blockquote>${esc(row.evidence)}</blockquote>`:'<p class="muted">缺少可核验的原文证据。</p>'}<small class="muted">置信度：${Number.isFinite(row.confidence)?`${Math.round(row.confidence*100)}%`:'未记录'}</small></section>`;
}
function renderEvidenceList() {
  const rows=verificationRows().filter(row=>state.evidenceFilter==='all'||(state.evidenceFilter==='supported'?row.support===true:state.evidenceFilter==='unsupported'?row.support===false:row.support==null));
  $('#evidence-list').innerHTML=rows.length?rows.map(evidenceCard).join(''):emptyContent('暂无匹配的核验结果',state.detail.status==='dry_run'?'离线检查不会执行真实引用核验。':'待核验完成后查看，或切换结果筛选。');
}
function selectPaper(id) { state.selectedPaper=id;renderEvidenceRail();$('#evidence-rail').focus(); }
function renderEvidenceRail() {
  const node=$('#evidence-rail');if(!node) return;
  const paper=papersList().find(p=>p.paper_id===state.selectedPaper);
  if(!paper) { node.innerHTML=`<div class="rail-title"><h2>引用溯源</h2>${icon('link')}</div><p class="rail-subtitle">阅读时，点击正文中的引用编号。</p><p class="small muted">对应论文、论断与原文证据将在这里展开，帮助你验证每一次引用。</p>`;return; }
  const rows=verificationRows().filter(row=>row.citation===paper.paper_id);
  const url=typeof paper.source==='string' && /^https?:\/\//i.test(paper.source)?paper.source:null;
  node.innerHTML=`<div class="rail-title"><h2>引用溯源</h2><span class="badge mono">${esc(citationLabel(paper.paper_id))}</span></div><h3>${esc(paper.title)}</h3><p>${esc((paper.authors || []).join(' · '))}${paper.year?` · ${esc(paper.year)}`:''}</p>${url?`<a class="button" href="${esc(url)}" target="_blank" rel="noopener noreferrer">打开论文来源${icon('external')}</a>`:''}${rows.length?rows.map(row=>`<div class="divider"></div><div class="evidence-head"><span class="mono">${esc(row.claim_id)}</span><span>${supportLabel(row.support)}</span></div>${row.evidence?`<blockquote>${esc(row.evidence)}</blockquote>`:'<p>缺少可核验的原文证据。</p>'}`).join(''):'<div class="divider"></div><p>该论文尚无引用核验记录。</p>'}`;
}
function renderSettings() {
  const s=state.settings;
  $('#main').innerHTML=`<div class="page-heading"><div><p class="eyebrow">WORKSPACE PREFERENCES</p><h1>为专注的研究做好准备。</h1><p>查看当前运行参数，了解文献格式与本地工作台的使用方式。</p></div></div><div class="settings-grid"><section class="panel settings-card"><h2>当前运行配置</h2>${[['模型',s?.model || '未读取'],['论文阅读并发',s?.concurrency ?? '—'],['模型凭据',s?.configured?'已配置':'待配置'],['引用核验','生成模式强制启用'],['论文来源','固定上传文献集']].map(([key,value])=>`<div class="setting-row"><span>${key}</span><strong>${esc(value)}</strong></div>`).join('')}<div class="help-block"><h3>修改配置</h3><p>在本地编辑运行配置后重启 Web 服务。密钥只由后端读取，页面不显示或保存密钥。</p><code>configs/config.yaml</code></div><div class="help-block"><h3>首次配置模型</h3><p>复制模板后填写真实密钥与服务地址。</p><code>cp API_key.conf.example API_key.conf</code></div></section><section class="panel settings-card"><h2>开始使用</h2><div class="help-block"><h3>01 · 准备文献</h3><p>上传 JSON 数组、JSONL 或 YAML 数组。每篇至少包含 title，建议提供 abstract、content、authors、year、source。paper_id 可省略，由后端分配。</p><p>当前不直接解析 PDF，也不联网检索论文。</p></div><div class="help-block"><h3>02 · 选择运行方式</h3><p>「生成 Survey」会调用已配置模型，使用现有超时与重试策略。「离线检查」不调用模型，仅校验输入和渲染 Prompt，不产出研究结论。</p></div><div class="help-block"><h3>03 · 查看与导出</h3><p>任务运行时可切换页面，完成后查看正文、大纲和引用证据。所有产物保存在配置的 runs 目录，也可在页面下载 Markdown 或 JSON。</p><p>本地工作台每次执行一个任务；请在任务完成前保持服务运行。CLI 历史任务会自动读取，CLI 正在进行的任务在结束前显示为产物不完整。</p></div></section></div>`;
}
async function refreshRuns() {
  const runs=await api('/api/runs');
  if(JSON.stringify(runs)===JSON.stringify(state.runs)) return;
  state.runs=runs;sidebar();
  if(routeInfo().page==='history') renderHistoryList();
  if($('#home-recent')) $('#home-recent').innerHTML=homeRecent();
}
async function loadDetail(route,epoch,refocus) {
  const scroll=window.scrollY,focusId=document.activeElement?.id;
  try {
    const detail=await api(`/api/runs/${encodeURIComponent(route.id)}`);
    if(epoch!==state.epoch) return;
    state.detail=detail;state.lastDetail=JSON.stringify(detail);renderDetail();
    if(refocus) $(`#tab-${state.tab}`).focus();
    else {
      if(focusId && document.getElementById(focusId)) document.getElementById(focusId).focus({preventScroll:true});
      window.scrollTo(0,scroll);
    }
  } catch(error) {
    if(epoch!==state.epoch) return;
    $('#main').innerHTML=`<div class="panel empty-state">${icon('alert')}<h1>暂时无法打开研究</h1><p>${esc(error.message)}</p><button id="retry-detail" class="button primary">重新加载</button> <a href="#history" class="button">返回任务历史</a></div>`;
    $('#retry-detail').onclick=navigate;
  }
}
async function navigate() {
  const initial=state.epoch===0;
  const route=routeInfo(),epoch=++state.epoch;
  const sameRun=route.page==='run' && state.detail?.id===route.id;
  $('#page-label').textContent={new:'研究工作台',history:'任务历史',settings:'设置与帮助',run:'研究详情'}[route.page];
  sidebar();
  if(route.page==='new') renderNew();
  else if(route.page==='history') renderHistory();
  else if(route.page==='settings') renderSettings();
  else {
    state.tab=['survey','outline','papers','evidence','artifacts'].includes(route.tab)?route.tab:'survey';
    if(!sameRun) {state.selectedPaper=null;state.evidenceFilter='all';$('#main').innerHTML='<div class="loading"><div class="loading-line"></div>正在读取研究产物…</div>';}
    await loadDetail(route,epoch,sameRun);
  }
  if(!sameRun && !initial) $('#main').focus({preventScroll:true});
}
async function poll() {
  try {
    await refreshRuns();
    connection();
    const route=routeInfo(),epoch=state.epoch;
    if(route.page==='run' && state.detail?.id===route.id && state.detail.status==='running') {
      // 运行中用轻量状态接口轮询，避免每次都传输全部产物全文。
      const summary=await api(`/api/runs/${encodeURIComponent(route.id)}/status`);
      if(epoch!==state.epoch) return;
      const snapshot=JSON.stringify([summary.status,summary.stages,summary.verification]);
      if(snapshot!==JSON.stringify([state.detail.status,state.detail.stages,state.detail.verification])) {
        state.detail={...state.detail,status:summary.status,stages:summary.stages,verification:summary.verification,paper_count:summary.paper_count};
        const focused=document.activeElement;
        // 用户正在读正文或操作产物时仅更新进度，不重建正在交互的节点。
        const interacting=$('#tab-content')?.contains(focused) || $('#evidence-rail')?.contains(focused);
        if(!interacting || summary.status!=='running') await loadDetail(route,epoch,false);
        else { const rail=$('.rail'); if(rail) rail.firstElementChild.outerHTML=stageRail(state.detail); }
        announce(`研究任务${statusNames[summary.status]}，已有 ${summary.stages.length} 个阶段日志。`);
      }
    }
  } catch { connection(true); }
  finally { setTimeout(poll,2500); }
}
window.addEventListener('hashchange',navigate);
async function init() {
  await navigate();
  try { state.settings=await api('/api/settings');connection();if(routeInfo().page==='settings') renderSettings(); }
  catch { connection(true); }
  poll();
}
init();
