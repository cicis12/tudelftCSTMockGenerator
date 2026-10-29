'use strict';
const $ = (s, root = document) => root.querySelector(s);
const main = $('#main');
const modal = $('#modal');
const state = { config: null, section: 'both', mode: 'timed', attempt: null, index: 0, choice: null, busy: false, formula: false, offset: 0, admin: null, account: null, progress: null };
const sectionName = s => s === 'math' ? 'Mathematics' : 'Logic & reasoning';
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function math(root = main) { if (window.renderMathInElement) renderMathInElement(root, {delimiters: [{left:'\\(',right:'\\)',display:false},{left:'\\[',right:'\\]',display:true}], throwOnError:false, trust:false}); }
function toast(message) { $('#toast').textContent = message; $('#toast').classList.remove('hidden'); clearTimeout(toast.timeout); toast.timeout = setTimeout(() => $('#toast').classList.add('hidden'), 6500); }
async function api(path, method = 'GET', data) {
  const isFile = data instanceof Blob;
  const response = await fetch(`/api${path}`, { method, headers: {'Content-Type': isFile ? 'application/zip' : 'application/json', 'X-CST-Request': '1'}, ...(data !== undefined ? {body: isFile ? data : JSON.stringify(data)} : {}) });
  let body; try { body = response.ok && response.headers.get('content-type')?.startsWith('application/zip') ? await response.blob() : await response.json(); } catch { throw new Error('The server did not respond. Please try again.'); }
  if (!response.ok) { const e = new Error(Array.isArray(body.detail) ? body.detail.map(x => x.msg).join(' · ') : (body.detail || 'Something went wrong.')); e.status = response.status; throw e; }
  return body;
}
function openModal(content) {
  const active = state.attempt?.status === 'active' && state.attempt.mode === 'timed';
  $('#modal-content').innerHTML = (active ? `<div class="sticky top-0 z-10 bg-white pb-3 mb-4 border-b border-slate-100 flex items-center justify-between gap-3"><span class="text-xs text-slate-500">${sectionName(state.attempt.section)} · Time remaining</span><span id="modal-timer" class="timer" role="timer" aria-label="Time remaining in dialog">--:--</span></div>` : '') + content;
  modal.showModal(); math(modal); if(active) updateTimer();
}
function closeModal() { modal.close(); }
function takeAttempt(attempt, reset = false) {
  const previous = state.attempt;
  if (previous && (previous.section !== attempt.section || previous.block !== attempt.block || previous.status !== attempt.status)) closeModal();
  state.attempt = attempt;
  state.offset = attempt.server_time * 1000 - Date.now();
  if (reset || !previous || previous.section !== attempt.section || previous.block !== attempt.block) state.index = 0;
  if (attempt.mode === 'infinite') state.index = Math.max(0, attempt.items.length - 1);
  state.choice = null;
  if(attempt.progress) state.progress=attempt.progress;
  renderAccountNav();
  location.hash = `session/${attempt.id}`;
  renderAttempt();
}
function selectedSections() { return state.section === 'both' ? ['math','logic'] : [state.section]; }
function configSummary() {
  const sections = selectedSections();
  return {minutes: sections.reduce((n,s)=>n+state.config.durations[s]/60,0), count: sections.reduce((n,s)=>n+state.config.question_counts[s],0)};
}

async function home() {
  state.attempt = null;
  state.config = await api('/config');
  setLearnerState(state.config);
  renderHome();
}
function renderHome() {
  const summary = configSummary();
  const unavailable = selectedSections().filter(s=>!state.progress.sections[s].available);
  main.innerHTML = `
    <section class="pt-12 sm:pt-16 pb-10 grid md:grid-cols-[1.4fr_1fr] gap-8 items-center">
      <div><div class="eyebrow mb-5 flex items-center gap-2"><span class="w-1.5 h-1.5 bg-teal rounded-full"></span> Your next chapter starts here</div>
        <h1 class="text-4xl sm:text-5xl font-semibold leading-[1.13] tracking-[-0.045em]">A little practice.<br>A lot more <span class="text-teal">confidence.</span></h1>
        <p class="mt-5 text-slate-500 max-w-lg leading-relaxed">Your space to prepare for the TU Delft Cognitive Skills Test. Find your rhythm, sharpen your thinking, and make progress one question at a time.</p>
        <div class="flex flex-wrap gap-5 mt-6 text-xs text-slate-500"><span>✓ Syllabus-based practice</span><span>✓ Worked solutions</span><span>✓ Your pace</span></div>
      </div>
      <div class="hidden md:block relative h-56 rounded-3xl bg-[#e9f3f1] grid-art overflow-hidden" aria-hidden="true">
        <svg viewBox="0 0 390 224" class="w-full h-full"><path d="M40 180H350M80 200V25" stroke="#a1c6c3" stroke-width="1.5"/><path d="M55 160C125 185 165 167 204 117S268 39 342 42" fill="none" stroke="#087e8b" stroke-width="3"/><circle cx="204" cy="117" r="6" fill="#087e8b" stroke="#fff" stroke-width="3"/><path d="M204 117V180" stroke="#087e8b" stroke-dasharray="4 5" opacity=".4"/><rect x="222" y="134" width="150" height="48" rx="10" fill="white" stroke="#d7e7e5"/><text x="238" y="164" fill="#326563" font-family="Georgia,serif" font-size="15">progress ≠ perfect</text><text x="100" y="65" fill="#54817d" font-family="Georgia,serif" font-style="italic" font-size="24">f(x) = possibility</text></svg>
      </div>
    </section>
    ${progressPanel()}
    ${state.config.active_attempt ? `<div class="card px-5 py-4 mb-6 flex flex-wrap items-center justify-between gap-3 border-teal/30"><p class="text-sm">You have a session in progress. <span class="text-slate-500">Your progress is saved.</span></p><button data-action="resume" data-id="${state.config.active_attempt}" class="text-sm font-semibold text-teal">Resume session →</button></div>` : ''}
    <div class="grid lg:grid-cols-[1fr_310px] gap-6 items-start" id="practice">
      <section class="card p-6 sm:p-8">
        <div class="flex items-start justify-between gap-3 mb-7"><div><h2 class="text-xl font-semibold">Make this session yours</h2><p class="text-sm text-slate-500 mt-1">Choose your focus. We’ll take it from here.</p></div><span class="pill hidden sm:inline-flex">CST practice</span></div>
        <h3 class="step-title"><span class="step-dot">1</span> What would you like to work on?</h3>
        <div class="grid grid-cols-1 sm:grid-cols-3 gap-3" role="group" aria-label="Test section">
          ${[['math','ƒ','Mathematics','Functions, calculus & more','60 min'],['logic','∴','Logic & reasoning','Think clearly. Connect ideas.','45 min'],['both','⊞','Both sections','The complete practice run','105 min']].map(([id,icon,title,desc,time])=>`<button class="choice-card ${state.section===id?'selected':''}" data-action="section-choice" data-value="${id}" aria-pressed="${state.section===id}"><span class="radio-dot"></span><span class="tile-icon">${icon}</span><span class="block text-sm font-semibold mb-1">${title}</span><span class="block text-xs text-slate-500 leading-relaxed min-h-9">${desc}</span><span class="block mt-4 text-xs font-medium text-slate-600">${time}</span></button>`).join('')}
        </div>
        <h3 class="step-title mt-8"><span class="step-dot">2</span> How do you want to practise?</h3>
        <div class="grid sm:grid-cols-2 gap-3" role="group" aria-label="Practice mode">
          ${[['timed','◷','Timed mock','A focused exam-style session. Get your full review when you finish.'],['infinite','∞','Infinite practice','One question at a time, with immediate feedback. Keep going for as long as you like.']].map(([id,icon,title,desc])=>`<button class="choice-card ${state.mode===id?'selected':''}" data-action="mode-choice" data-value="${id}" aria-pressed="${state.mode===id}"><span class="radio-dot"></span><span class="text-teal text-2xl block mb-2">${icon}</span><span class="text-sm font-semibold">${title}</span><span class="block text-xs text-slate-500 leading-relaxed mt-2 pr-1">${desc}</span></button>`).join('')}
        </div>
        <div class="border-t border-slate-100 mt-7 pt-6 flex flex-wrap items-center justify-between gap-4"><div><p class="text-sm font-medium">${state.mode==='timed'?`${summary.count} questions · ${summary.minutes} minutes`:'Unlimited questions · Instant feedback'}</p><p class="text-xs text-slate-500 mt-1">${state.mode==='timed'?'Your rules and checklist are up next.':'Repeating timed blocks. Stop whenever you like.'}</p></div><button class="btn-primary" data-action="rules" ${unavailable.length?'disabled':''}>Let’s get started <span aria-hidden="true">→</span></button></div>
      ${unavailable.length?`<div class="rounded-xl bg-amber-50 text-amber-900 p-4 mt-5 text-sm leading-relaxed"><strong>You’re caught up.</strong> ${unavailable.map(s=>`${sectionName(s)} has no questions ready. Return ${nextReview(state.progress.sections[s].next_review_at)}.`).join(' ')} Choose another section for now.</div>`:''}
      </section>
      <aside class="space-y-5">
        ${readinessPanel()}
        <section class="rounded-2xl p-6 bg-[#eef3f4]"><p class="eyebrow mb-2">A quick heads-up</p><p class="text-sm leading-relaxed text-slate-600">Bring a pen and paper, leave the calculator behind. You’ll have the supplied formula sheet beside you during maths.</p></section>
      </aside>
    </div>
    <section id="resources" class="grid md:grid-cols-2 gap-8 mt-12"><div><h2 class="font-semibold text-lg">Start with the foundations</h2><p class="text-sm text-slate-500 mt-2">The official preparation resources behind your practice.</p><a class="resource-link" href="https://ocw.tudelft.nl/courses/pre-university-calculus/" target="_blank" rel="noopener">TU Delft · Pre-University Calculus <span>↗</span></a><a class="resource-link" href="https://www.edx.org/learn/calculus/delft-university-of-technology-pre-university-calculus" target="_blank" rel="noopener">DelftX · Calculus on edX <span>↗</span></a><a class="resource-link" href="/formula-sheet.pdf" target="_blank" rel="noopener">Supplied mathematics formula sheet <span>↗</span></a></div><div><h2 class="font-semibold text-lg">Your recent sessions</h2><p class="text-sm text-slate-500 mt-2">Saved in this browser. Come back to your worked solutions.</p><div id="history" class="mt-3 text-sm text-slate-500">Loading sessions…</div></div></section>
    <p class="text-xs leading-relaxed text-slate-400 mt-8">Original practice questions based on the supplied syllabus. Mock lengths and multiple-choice format are app settings, not a claim about the official exam. Practice scores are not admissions predictions.</p>`;
  api('/history').then(rows => { const target = $('#history'); if(target) target.innerHTML = rows.length ? rows.slice(0,5).map(r=>`<button class="resource-link w-full text-left" data-action="resume" data-id="${r.id}"><span>${r.sections.map(sectionName).join(' + ')} <span class="text-xs text-slate-400">· ${r.mode==='timed'?'Mock':'Practice'}</span></span><span class="text-xs">${new Date(r.created_at*1000).toLocaleDateString()} ↗</span></button>`).join('') : '<p class="py-5">A fresh start. Your completed sessions will appear here.</p>'; }).catch(()=>{});
}
function showRules() {
  const summary = configSummary();
  openModal(`<div class="eyebrow">Before you begin</div><h2 class="text-2xl font-semibold mt-3">Clear desk. Clear mind.</h2><p class="text-sm text-slate-500 mt-2">${selectedSections().map(sectionName).join(' + ')} · ${state.mode==='timed'?`${summary.minutes} minutes`:'Infinite practice'}</p>
    <ul class="space-y-4 text-sm text-slate-600 my-6 list-disc pl-5">
      <li>Work independently, without a calculator, search engines, AI tools, or extra reference materials. Use exact values, not rounded approximations.</li>
      <li>The maths formula sheet is available in the side panel. The official test also restricts phones, second devices and headphones; this practice app works on your chosen phone or computer.</li>
      ${state.mode==='timed'?`<li>Maths lasts 60 minutes; logic lasts 45 minutes. When both are selected, maths comes first and logic starts immediately when maths ends. There is no pause between sections.</li><li>Move between questions and change answers within the current section. A submitted or expired section is locked. Feedback appears after the entire mock ends.</li><li>The clock keeps running through refreshes, closed tabs and lost connections. Only answers successfully saved before the deadline count.</li>`:`<li>Receive the correct answer and explanation after every submitted question. Submitted answers cannot be changed.</li><li>Practice continues in 60-minute maths and 45-minute logic blocks without a visible countdown. With both selected, blocks alternate. A timeout closes the current question and starts the next block.</li><li>Questions answered correctly rest for ${state.progress.cooldown_days} days. Other questions may repeat after you exhaust the eligible bank. You can stop at any time and review your whole session.</li>`}
      <li>Correct answers are remembered for ${state.progress.cooldown_days} days before being offered again. Timed mocks update your progress only after the whole mock ends. Mock lengths may be shorter when questions are resting.</li>
      <li>This mock uses four-option questions: one point for a correct answer, zero for an incorrect or unanswered question. This is a practice scoring choice.</li>
    </ul><label class="flex gap-3 items-start p-4 rounded-xl bg-slate-50"><input id="accept-rules" type="checkbox" class="w-4 h-4 mt-0.5"><span>I’ve read the rules and I’m ready to begin.</span></label><div class="flex justify-between mt-6"><button class="btn-quiet" data-action="close">Go back</button><button class="btn-primary" data-action="start" id="start-button" disabled>Start ${state.mode==='timed'?'mock':'practice'} →</button></div>`);
  $('#accept-rules').addEventListener('change', e=>$('#start-button').disabled=!e.target.checked);
}
function formulaContent() {
  return `<div class="flex items-start justify-between gap-2"><div><p class="eyebrow">Your reference</p><h2 class="font-semibold mt-2">Formula sheet</h2></div><span class="text-teal text-xl">ƒ</span></div><p class="text-xs text-slate-500 mt-2 mb-4">Mathematics · supplied v2019.1</p><a class="text-xs font-semibold text-teal" href="/formula-sheet.pdf" target="_blank" rel="noopener">Open original PDF ↗</a><h3 class="text-xs font-semibold uppercase tracking-wider text-slate-500 mt-6 mb-1">Trigonometry</h3>
    ${['\\cos^2x+\\sin^2x=1','\\cos(\\alpha\\mp\\beta)=\\cos\\alpha\\cos\\beta\\pm\\sin\\alpha\\sin\\beta','\\sin(\\alpha\\pm\\beta)=\\sin\\alpha\\cos\\beta\\pm\\cos\\alpha\\sin\\beta','\\tan(\\alpha\\pm\\beta)=\\frac{\\tan\\alpha\\pm\\tan\\beta}{1\\mp\\tan\\alpha\\tan\\beta}','\\cos(2x)=\\cos^2x-\\sin^2x','\\cos(2x)=2\\cos^2x-1=1-2\\sin^2x','\\sin(2x)=2\\sin x\\cos x','\\tan(2x)=\\frac{2\\tan x}{1-\\tan^2x}'].map(f=>`<div class="formula-row">\\(${f}\\)</div>`).join('')}
    <h3 class="text-xs font-semibold uppercase tracking-wider text-slate-500 mt-6 mb-1">Integrals</h3>
    ${['\\int x^a dx=\\frac{x^{a+1}}{a+1}+C,\\quad a\\ne-1','\\int a^x dx=\\frac{a^x}{\\ln a}+C,\\quad a>0,\\ a\\ne1','\\int\\frac1x dx=\\ln|x|+C','\\int e^x dx=e^x+C','\\int\\ln x\\,dx=x\\ln x-x+C','\\int\\log_a x\\,dx=\\frac{x\\ln x-x}{\\ln a}+C','\\int\\sin x\\,dx=-\\cos x+C','\\int\\cos x\\,dx=\\sin x+C'].map(f=>`<div class="formula-row">\\(${f}\\)</div>`).join('')}<p class="text-xs text-slate-400 mt-4">Real-valued domains apply; logarithm bases satisfy a &gt; 0, a ≠ 1. The original PDF is available above.</p>`;
}
function renderAttempt() {
  const a=state.attempt;
  if(a.status==='finished') { renderResults(); return; }
  const item = a.items[state.index];
  if(!item) { toast('No question is available. Please return home and try again.'); return; }
  const timed=a.mode==='timed', answered=a.items.filter(i=>i.answer!==null).length;
  main.innerHTML = `<div class="timer-bar"><div><p class="eyebrow">${timed?'Timed mock':`Infinite practice · Block ${a.block+1}`}</p><h1 class="text-lg font-semibold mt-1">${sectionName(a.section)}</h1></div><div class="flex gap-3 items-center">${timed?'<div class="text-right hidden sm:block text-xs text-slate-500">Section ends in<br><span id="save-status" class="text-teal">Answers saved on this device’s session</span></div><div class="timer" id="timer" role="timer" aria-label="Time remaining">--:--</div>':''}<button class="btn-quiet !px-2 text-xs" data-action="end">${timed?'End mock':'Finish practice'}</button></div></div>
    <div class="flex flex-wrap items-center justify-between gap-2 my-5"><a class="text-xs text-slate-500" href="/">← Workspace ${timed?'<span class="hidden sm:inline">(timer continues)</span>':''}</a>${a.section==='math'?'<button class="text-sm text-teal font-semibold lg:hidden" data-action="formulas">ƒ Formula sheet</button>':''}<span class="pill">${timed?`${answered} of ${a.items.length} answered`:`Question ${item.position+1}`}</span></div>
    <div class="grid ${a.section==='math'?'lg:grid-cols-[1fr_330px]':''} gap-6 items-start">
      <div class="min-w-0"><section class="card p-6 sm:p-8"><div class="flex justify-between gap-2 items-start mb-7"><div><p class="eyebrow">Question ${timed?state.index+1:item.position+1}${timed?` / ${a.items.length}`:''}</p><p class="text-xs text-slate-500 mt-2">${esc(item.topic)} <span class="mx-1">·</span> ${esc(item.difficulty)}</p></div>${timed?`<button class="text-xs ${item.flagged?'text-amber-700':'text-slate-400'}" data-action="flag">⚑ ${item.flagged?'Flagged':'Flag for review'}</button>`:''}</div>
      <div class="question-copy mb-7">${esc(item.prompt)}</div><div class="space-y-3" role="group" aria-label="Answer options">${item.options.map((option,i)=>`<button data-action="answer-choice" data-index="${i}" ${item.submitted?'disabled':''} aria-pressed="${item.answer===i}" class="option ${item.answer===i?'selected':''} ${item.submitted && i===item.correct_index?'correct':''} ${item.submitted && item.answer===i && !item.correct?'incorrect':''}"><span class="option-key">${String.fromCharCode(65+i)}</span><span class="flex-1">${esc(option)}</span>${item.submitted && i===item.correct_index?'<span class="text-emerald-700 text-xs">✓ Correct</span>':''}</button>`).join('')}</div>
      ${item.submitted?feedback(item):''}
      <div class="mt-8 pt-5 border-t border-slate-100 flex flex-wrap justify-between gap-3">${timed?`<button class="btn-quiet !px-0" data-action="previous" ${state.index===0?'disabled':''}>← Previous</button><div class="flex gap-2"><button class="btn-quiet" data-action="clear" ${item.answer===null?'disabled':''}>Clear</button>${state.index<a.items.length-1?'<button class="btn-primary" data-action="next-local">Next question →</button>':'<button class="btn-primary" data-action="submit-section">Finish section →</button>'}</div>`:item.submitted?'<span class="text-xs text-slate-400 self-center">One step further.</span><button class="btn-primary" data-action="next-practice">Next question →</button>':'<span class="text-xs text-slate-400 self-center">Choose an answer, then check it.</span><button class="btn-primary" data-action="check" id="check-answer" disabled>Check answer →</button>'}</div></section>
      ${timed?`<section class="card mt-5 p-5"><div class="flex flex-wrap justify-between gap-2 text-xs text-slate-500 mb-4"><span>Question navigator</span><span>Teal = answered · Amber border = flagged</span></div><div class="flex flex-wrap gap-2.5">${a.items.map((q,i)=>`<button class="question-nav ${q.answer!==null?'answered':''} ${q.flagged?'flagged':''} ${i===state.index?'current':''}" data-action="jump" data-index="${i}" aria-label="Question ${i+1}${q.answer!==null?', answered':''}${q.flagged?', flagged':''}" ${i===state.index?'aria-current="step"':''}>${i+1}</button>`).join('')}</div><button class="mt-5 text-xs font-semibold text-teal" data-action="submit-section">Finish this section →</button></section>`:`<p class="text-xs text-slate-500 mt-5">${Object.entries(a.scores).map(([s,v])=>`${sectionName(s)}: ${v.correct}/${v.total} correct`).join(' · ')} · Finish any time to review every question.</p>`}</div>
      ${a.section==='math'?`<aside class="formula-panel hidden lg:block">${formulaContent()}</aside>`:''}</div>`;
  math(); updateTimer();
}
function feedback(item) {
  const cooldownNotice=item.correct&&state.attempt?.mode==='infinite'?`<p class="text-xs text-teal font-medium mt-3">✓ Remembered. This question will rest for ${state.progress?.cooldown_days||7} days.</p>`:'';
  return `<div class="mt-6 rounded-xl p-5 ${item.correct?'bg-emerald-50':'bg-amber-50'}"><h3 class="font-semibold text-sm ${item.correct?'text-emerald-800':'text-amber-900'}">${item.correct?'✓ That’s correct.':item.answer===null?'Unanswered — here’s the solution.':'Not quite. Let’s work through it.'}</h3><p class="text-sm mt-2"><strong>Correct answer: ${String.fromCharCode(65+item.correct_index)}.</strong> ${esc(item.options[item.correct_index])}</p><p class="text-sm leading-relaxed mt-3 text-slate-600">${esc(item.explanation)}</p>${cooldownNotice}<p class="text-xs text-slate-400 mt-3">Scope: ${esc(item.source_ref)}</p></div>`;
}
function updateTimer() {
  const a = state.attempt, target=$('#timer');
  if(!a || a.status!=='active') return;
  const seconds = Math.max(0, Math.ceil(a.deadline-(Date.now()+state.offset)/1000));
  for (const display of [target, $('#modal-timer')]) {
    if (!display) continue;
    display.textContent = `${String(Math.floor(seconds/60)).padStart(2,'0')}:${String(seconds%60).padStart(2,'0')}`;
    display.classList.toggle('urgent', seconds<300);
  }
  if(seconds===0 && !state.busy && !updateTimer.refreshing) {
    updateTimer.refreshing=true;
    api(`/attempts/${a.id}`).then(next=>{ takeAttempt(next); toast(a.mode==='timed'?'Time is up. Your session has moved on.':'A new practice block has started.'); }).catch(()=>toast('Connection lost. Reconnect to continue.')).finally(()=>setTimeout(()=>updateTimer.refreshing=false,3000));
  }
}
setInterval(updateTimer, 1000);
setInterval(async()=>{
  if(state.attempt?.status!=='active' || state.busy || modal.open) return;
  try {
    const a=await api(`/attempts/${state.attempt.id}`);
    state.offset=a.server_time*1000-Date.now();
    if(a.status!==state.attempt.status || a.section!==state.attempt.section || a.block!==state.attempt.block) { takeAttempt(a); toast('Your section has ended.'); }
  } catch { /* Saved answers remain intact; mutations show connection errors. */ }
}, 15000);
function renderResults() {
  const a=state.attempt, scores=Object.values(a.scores), total=scores.reduce((n,v)=>n+v.total,0), correct=scores.reduce((n,v)=>n+v.correct,0);
  const caughtUp=a.mode==='infinite' && a.progress && a.sections.every(s=>a.progress.sections[s].available===0);
  main.innerHTML = `<div class="pt-12 pb-8"><p class="eyebrow">Session complete</p><h1 class="text-3xl sm:text-4xl font-semibold mt-3">Good work showing up.</h1><p class="text-slate-500 mt-3">Take a breath. Then turn what you’ve learned into your next step.</p>${caughtUp?`<div class="mt-5 rounded-xl bg-[#e8f4ef] border border-teal/15 p-4 text-sm text-teal"><strong>You’re caught up.</strong> All available questions in this session are resting. ${a.sections.map(s=>`${sectionName(s)} returns ${nextReview(a.progress.sections[s].next_review_at)}.`).join(' ')}</div>`:''}</div><div class="grid md:grid-cols-[1fr_2fr] gap-5"><section class="card p-7"><p class="text-sm text-slate-500">Your practice score</p><p class="text-5xl font-semibold text-teal mt-3">${total?Math.round(100*correct/total):0}<span class="text-2xl">%</span></p><p class="text-sm text-slate-500 mt-3">${correct} correct out of ${total} questions</p><p class="text-xs text-slate-400 mt-4">Raw practice accuracy, not an official CST score.</p></section><section class="card p-7"><h2 class="font-semibold mb-5">Your section breakdown</h2>${Object.entries(a.scores).map(([s,v])=>`<div class="mb-5"><div class="flex justify-between text-sm mb-2"><span>${sectionName(s)}</span><span class="font-semibold">${v.correct} / ${v.total}</span></div><progress class="w-full h-2 accent-teal" max="${v.total||1}" value="${v.correct}" aria-label="${sectionName(s)} accuracy"></progress></div>`).join('')}<a href="/" class="text-sm text-teal font-semibold">Start another session →</a></section></div><div class="mt-6">${progressPanel()}</div><div class="flex flex-wrap items-center justify-between gap-4 mt-10 mb-5"><div><h2 class="text-xl font-semibold">Every question, explained.</h2><p class="text-sm text-slate-500 mt-1">Your answers, the correct choices, and the thinking behind them.</p></div><select id="review-filter" class="!w-auto" aria-label="Filter question review"><option value="all">All questions</option><option value="incorrect">Incorrect & unanswered</option><option value="correct">Correct answers</option></select></div><div id="review-list" class="space-y-5"></div>`;
  renderReview('all');
  $('#review-filter').addEventListener('change', e=>renderReview(e.target.value));
}
function renderReview(filter) {
  const items=state.attempt.items.filter(i=>filter==='all'||(filter==='correct'?i.correct:!i.correct));
  $('#review-list').innerHTML = items.length?items.map(i=>`<article class="review-question"><div class="flex flex-wrap justify-between gap-2 mb-4"><p class="text-xs text-slate-500">${sectionName(i.section)} · Question ${i.position+1} · ${esc(i.topic)}</p><span class="pill ${i.correct?'!bg-emerald-50 !text-emerald-700':'!bg-rose-50 !text-rose-700'}">${i.correct?'✓ Correct':i.answer===null?'— Unanswered':'× Incorrect'}</span></div><p class="question-copy">${esc(i.prompt)}</p><div class="grid sm:grid-cols-2 gap-3 mt-5">${i.options.map((o,n)=>`<div class="rounded-lg border p-3 text-sm ${n===i.correct_index?'border-emerald-400 bg-emerald-50':n===i.answer?'border-rose-300 bg-rose-50':'border-slate-200'}"><strong class="mr-2">${String.fromCharCode(65+n)}.</strong>${esc(o)} ${n===i.answer?'<span class="text-xs font-semibold">(your answer)</span>':''} ${n===i.correct_index?'<span class="text-xs text-emerald-700">✓ Correct</span>':''}</div>`).join('')}</div>${feedback(i)}</article>`).join(''):'<p class="card p-8 text-slate-500">No questions in this category.</p>';
  math($('#review-list'));
}

async function adminPage() {
  state.attempt=null;
  try { state.admin=await api('/admin/status'); renderAdmin(); await loadAdminQuestions(); await loadJobs(); }
  catch(e) { if(e.status!==401) throw e; renderLogin(); }
}
function renderLogin() {
  main.innerHTML=`<section class="max-w-md mx-auto my-16 card p-8"><p class="eyebrow">Behind the questions</p><h1 class="text-2xl font-semibold mt-3">Admin workspace</h1><p class="text-sm text-slate-500 mt-3 mb-6">Manage your question bank and generate new practice material.</p><form id="login-form"><label for="admin-password">Admin password</label><input type="password" id="admin-password" autocomplete="current-password" required class="mt-2"><p id="login-error" role="alert" class="text-sm text-rose-700 mt-3"></p><button class="btn-primary w-full mt-5">Sign in →</button></form><p class="text-xs text-slate-400 mt-5">Use the password configured in your deployment’s .env file.</p></section>`;
  $('#login-form').addEventListener('submit', async e=>{ e.preventDefault(); const button=$('button',e.target); button.disabled=true; try {await api('/admin/login','POST',{password:$('#admin-password').value}); await adminPage();}catch(error){$('#login-error').textContent=error.message;button.disabled=false;} });
}
function renderAdmin() {
  main.innerHTML=`<div class="pt-10 pb-7 flex justify-between items-start gap-4"><div><p class="eyebrow">Admin workspace</p><h1 class="text-3xl font-semibold mt-3">A better question bank.</h1><p class="text-sm text-slate-500 mt-2">Generate, review, and publish thoughtful practice material.</p></div><button class="btn-secondary" data-action="logout">Sign out</button></div>
    <section class="card p-5 sm:p-6 mb-6" aria-labelledby="archive-heading"><div class="flex flex-wrap items-start justify-between gap-4"><div class="max-w-2xl"><h2 id="archive-heading" class="font-semibold text-lg">Move your question bank</h2><p class="text-sm text-slate-500 mt-2">Export all maths and logic questions, including drafts and rejected questions. Imports preserve publication statuses and add new questions; matching prompts are skipped and existing questions are kept.</p></div><button class="btn-secondary" data-action="export-bank">Export all questions (.zip)</button></div><form id="import-form" class="flex flex-wrap items-end gap-3 mt-5"><div class="flex-1 min-w-0 basis-60"><label for="import-file">Question archive</label><input id="import-file" type="file" accept=".zip,application/zip" required class="mt-1"><p class="text-xs text-slate-400 mt-2">CST Studio ZIP · Maximum 10 MiB</p></div><button id="import-button" class="btn-primary">Import ZIP</button></form><p id="archive-status" class="text-sm text-slate-600 mt-3" role="status" aria-live="polite"></p></section>
    <div class="grid lg:grid-cols-[340px_1fr] gap-6 items-start"><section class="card p-6"><h2 class="font-semibold text-lg">Generate questions</h2><p class="text-xs text-slate-500 leading-relaxed mt-2">The model receives the curated syllabus context for your selected section. Results are saved as drafts for your review.</p><form id="generate-form" class="space-y-4 mt-6"><div><label for="gen-section">Section</label><select id="gen-section" class="mt-1"><option value="math">Mathematics</option><option value="logic">Logic & reasoning</option></select></div><div class="grid grid-cols-2 gap-3"><div><label for="gen-count">Questions</label><input id="gen-count" type="number" min="1" max="${state.admin.generation_limit}" value="5" required class="mt-1"></div><div><label for="gen-difficulty">Difficulty</label><select id="gen-difficulty" class="mt-1"><option value="mixed">Mixed</option><option value="easy">Easy</option><option value="medium">Medium</option><option value="hard">Hard</option></select></div></div><p class="text-xs text-slate-500">Up to ${state.admin.generation_limit} questions per request, generated in batches of 10. Larger requests may take several minutes.</p><div><label for="gen-model">OpenAI model</label><input id="gen-model" value="${esc(state.admin.model)}" required class="mt-1"><p class="text-xs text-slate-400 mt-1">Choose a model with Responses structured-output support.</p></div><div><label for="gen-key">OpenAI API key</label><input id="gen-key" type="password" autocomplete="off" placeholder="${state.admin.has_key?'Server key configured · optional override':'sk-…'}" class="mt-1" ${state.admin.has_key?'':'required'}><p class="text-xs text-slate-400 mt-2">Used for this request only; never saved in the database or browser storage. OpenAI API usage is billed to your key.</p></div><button class="text-xs text-teal font-semibold" type="button" data-action="context">Preview the model context ↗</button><button class="btn-primary w-full" id="generate-button">Generate drafts →</button><p id="generation-error" role="alert" class="text-xs text-rose-700"></p></form><div id="generation-jobs" class="space-y-3 mt-5"></div></section>
    <section class="min-w-0"><div class="card p-5 mb-5"><div id="admin-counts" class="flex flex-wrap gap-2">${state.admin.counts.map(c=>`<span class="pill">${sectionName(c.section)} · ${c.count} ${c.status}</span>`).join('')}</div></div><div class="flex flex-wrap items-center justify-between gap-3 mb-5"><h2 class="font-semibold text-lg">Question library</h2><div class="flex gap-2"><select id="bank-status" class="!w-auto" aria-label="Publication status"><option value="draft">Drafts</option><option value="published">Published</option><option value="rejected">Rejected</option></select><select id="bank-section" class="!w-auto" aria-label="Question section"><option value="all">All sections</option><option value="math">Maths</option><option value="logic">Logic</option></select></div></div><p class="text-xs text-slate-500 mb-5">Check the answer, explanation, scope and difficulty before publishing. AI output can contain mistakes. Published edits return to draft; existing attempts keep their original questions.</p><div id="bulk-actions"></div><div id="admin-questions" class="space-y-4"></div></section></div>`;
  $('#import-form').addEventListener('submit', async e=>{
    e.preventDefault();
    const file=$('#import-file').files[0], button=$('#import-button'), status=$('#archive-status');
    if(!file) return;
    if(file.size>10*1024*1024) { status.textContent='ZIP files must be no larger than 10 MiB.'; return; }
    button.disabled=true; status.textContent='Validating and importing questions…';
    try {
      const result=await api('/admin/questions/import','POST',file);
      status.textContent=`Imported ${result.imported} question${result.imported===1?'':'s'}. Skipped ${result.skipped} duplicates (${result.total} questions in the archive).`;
      $('#import-file').value='';
      await loadAdminQuestions();
    } catch(error) { status.textContent=error.message; }
    finally { button.disabled=false; }
  });
  $('#bank-status').addEventListener('change',()=>loadAdminQuestions().catch(e=>toast(e.message)));
  $('#bank-section').addEventListener('change',()=>loadAdminQuestions().catch(e=>toast(e.message)));
  $('#generate-form').addEventListener('submit',async e=>{
    e.preventDefault(); const button=$('#generate-button'); button.disabled=true; $('#generation-error').textContent='';
    const data={section:$('#gen-section').value,count:Number($('#gen-count').value),difficulty:$('#gen-difficulty').value,model:$('#gen-model').value,api_key:$('#gen-key').value};
    try {await api('/admin/generate','POST',data); $('#gen-key').value=''; toast('Generation started. Your drafts will appear below.'); await loadJobs(); await loadAdminQuestions();}
    catch(error){$('#generation-error').textContent=error.message;}finally{button.disabled=false;}
  });
}
let bank=[], bankLoad=0;
async function loadAdminQuestions() {
  if(!$('#bank-status'))return;
  const status=$('#bank-status').value, section=$('#bank-section').value, load=++bankLoad;
  const [questions, admin]=await Promise.all([api(`/admin/questions?status=${status}&section=${section}`),api('/admin/status')]);
  if(load!==bankLoad || !$('#admin-questions') || $('#bank-status').value!==status || $('#bank-section').value!==section)return;
  bank=questions; state.admin=admin;
  $('#admin-counts').innerHTML=admin.counts.map(c=>`<span class="pill">${sectionName(c.section)} · ${c.count} ${c.status}</span>`).join('');
  const drafts=admin.counts.filter(c=>c.status==='draft' && (section==='all' || c.section===section)).reduce((n,c)=>n+c.count,0);
  $('#bulk-actions').innerHTML=status==='draft'?`<div class="card p-4 mb-5 flex flex-wrap items-center justify-between gap-3"><div><p class="text-sm font-semibold">${drafts} draft${drafts===1?'':'s'} ready for review</p><p class="text-xs text-slate-500 mt-1">Publish every draft in ${section==='all'?'all sections':sectionName(section)}, including those beyond this page.</p></div><button class="btn-primary" data-action="approve-all" data-section="${section}" ${drafts?'':'disabled'}>Approve all</button></div>`:'';
  $('#admin-questions').innerHTML=bank.length?bank.map(q=>`<article class="card p-5"><div class="flex flex-wrap gap-2 mb-4"><span class="pill">${esc(q.topic)}</span><span class="pill">${esc(q.difficulty)}</span><span class="pill">${esc(q.status)}</span></div><p class="leading-relaxed">${esc(q.prompt)}</p><div class="grid sm:grid-cols-2 gap-2 mt-4">${q.options.map((o,i)=>`<div class="text-sm p-3 rounded-lg ${i===q.correct_index?'bg-emerald-50 text-emerald-900':'bg-slate-50'}">${String.fromCharCode(65+i)}. ${esc(o)}${i===q.correct_index?' ✓':''}</div>`).join('')}</div><p class="text-sm text-slate-500 leading-relaxed mt-4">${esc(q.explanation)}</p><p class="text-xs text-slate-400 mt-3">${esc(q.source_ref)} · ${esc(q.origin)}</p><div class="flex flex-wrap gap-2 mt-5"><button class="btn-secondary !py-2" data-action="edit-question" data-id="${q.id}">Edit</button>${q.status!=='published'?`<button class="btn-primary !py-2" data-action="publish" data-id="${q.id}">Approve & publish</button>`:''}${q.status!=='rejected'?`<button class="btn-quiet !py-2" data-action="reject" data-id="${q.id}">${q.status==='published'?'Unpublish':'Reject'}</button>`:''}</div></article>`).join(''):'<div class="card p-10 text-center"><span class="text-teal text-3xl">✓</span><h3 class="font-semibold mt-3">All clear here.</h3><p class="text-sm text-slate-500 mt-2">No questions match this filter. Generate a batch to add new drafts.</p></div>';
  math($('#admin-questions'));
}
async function loadJobs() {
  if(!$('#generation-jobs'))return;
  const jobs=await api('/admin/generations');
  $('#generation-jobs').innerHTML=jobs.slice(0,3).map(j=>`<div class="bg-slate-50 rounded-lg p-3 text-xs"><p class="font-semibold">${sectionName(j.section)} · ${esc(j.status)}</p><p class="text-slate-500 mt-1">${esc(j.message)}</p></div>`).join('');
  clearTimeout(loadJobs.timer);
  if(jobs.some(j=>j.status==='running')) loadJobs.timer=setTimeout(()=>loadJobs().then(()=>loadAdminQuestions()).catch(e=>toast(e.message)),4000);
}
function editQuestion(id) {
  const q=bank.find(q=>q.id===Number(id));
  openModal(`<h2 class="text-xl font-semibold mb-5">Review question #${q.id}</h2><form id="edit-form" class="space-y-4"><label class="block">Topic<select id="edit-topic" class="mt-1">${state.admin.topics[q.section].map(t=>`<option ${t===q.topic?'selected':''}>${esc(t)}</option>`).join('')}</select></label><label class="block">Difficulty<select id="edit-difficulty">${['easy','medium','hard'].map(t=>`<option ${t===q.difficulty?'selected':''}>${t}</option>`).join('')}</select></label><label class="block">Question<textarea id="edit-prompt" rows="4" required>${esc(q.prompt)}</textarea></label>${q.options.map((o,i)=>`<label class="block">Option ${String.fromCharCode(65+i)}<input id="edit-option-${i}" value="${esc(o)}" required></label>`).join('')}<label class="block">Correct answer<select id="edit-correct">${q.options.map((o,i)=>`<option value="${i}" ${i===q.correct_index?'selected':''}>${String.fromCharCode(65+i)}</option>`).join('')}</select></label><label class="block">Worked explanation<textarea id="edit-explanation" rows="5" required>${esc(q.explanation)}</textarea></label><label class="block">Source reference<input id="edit-source" value="${esc(q.source_ref)}" required></label><p id="edit-error" class="text-sm text-rose-700" role="alert"></p><div class="flex justify-end gap-3"><button type="button" class="btn-quiet" data-action="close">Cancel</button><button class="btn-primary">Save as draft</button></div></form>`);
  $('#edit-form').addEventListener('submit',async e=>{e.preventDefault();try{await api(`/admin/questions/${q.id}`,'PUT',{section:q.section,topic:$('#edit-topic').value,difficulty:$('#edit-difficulty').value,prompt:$('#edit-prompt').value,options:[0,1,2,3].map(i=>$(`#edit-option-${i}`).value),correct_index:Number($('#edit-correct').value),explanation:$('#edit-explanation').value,source_ref:$('#edit-source').value});closeModal();await loadAdminQuestions();toast('Saved as draft. Review and publish when ready.');}catch(error){$('#edit-error').textContent=error.message;}});
}

async function perform(action, el) {
  const a=state.attempt;
  switch(action) {
    case 'account': setLearnerState(await api('/account'));accountDialog();break;
    case 'account-login': accountDialog('login');break;
    case 'account-register': accountDialog('register');break;
    case 'learner-signout': setLearnerState(await api('/account/session','DELETE'));closeModal();state.attempt=null;history.replaceState(null,'',location.pathname);if(location.pathname!=='/admin')await home();toast('Signed out. Your account progress is saved.');break;
    case 'section-choice': state.section=el.dataset.value; renderHome(); break;
    case 'mode-choice': state.mode=el.dataset.value; renderHome(); break;
    case 'rules': showRules(); break;
    case 'close': closeModal(); break;
    case 'start': {if(!$('#accept-rules').checked)return; const data=await api('/attempts','POST',{section:state.section,mode:state.mode,accepted_rules:true});closeModal();takeAttempt(data,true);window.scrollTo(0,0);break;}
    case 'resume': takeAttempt(await api(`/attempts/${el.dataset.id}`),true);window.scrollTo(0,0);break;
    case 'formulas': openModal(`<div class="flex justify-end mb-3"><button class="btn-quiet !py-1" data-action="close">Close ×</button></div>${formulaContent()}`);break;
    case 'previous': state.index--;state.choice=null;renderAttempt();break;
    case 'next-local': state.index++;state.choice=null;renderAttempt();break;
    case 'jump': state.index=Number(el.dataset.index);state.choice=null;renderAttempt();break;
    case 'answer-choice': {
      const item=a.items[state.index], value=Number(el.dataset.index);
      if(a.mode==='timed') {takeAttempt(await api(`/attempts/${a.id}/items/${item.id}`,'PUT',{answer:value,flagged:item.flagged}));}
      else {state.choice=value;document.querySelectorAll('.option').forEach((o,i)=>{o.classList.toggle('selected',i===value);o.setAttribute('aria-pressed',String(i===value));});$('#check-answer').disabled=false;}break;
    }
    case 'clear': case 'flag': {const item=a.items[state.index];takeAttempt(await api(`/attempts/${a.id}/items/${item.id}`,'PUT',{answer:action==='clear'?null:item.answer,flagged:action==='flag'?!item.flagged:item.flagged}));break;}
    case 'check': if(state.choice!==null)takeAttempt(await api(`/attempts/${a.id}/items/${a.items[state.index].id}`,'PUT',{answer:state.choice}));break;
    case 'next-practice': takeAttempt(await api(`/attempts/${a.id}/next`,'POST'));break;
    case 'submit-section': {const unanswered=a.items.filter(i=>i.answer===null).length;openModal(`<h2 class="text-xl font-semibold">Finish ${sectionName(a.section).toLowerCase()}?</h2><p class="text-sm text-slate-500 my-4">${unanswered?`${unanswered} question${unanswered===1?' is':'s are'} unanswered. `:'Every question has an answer. '}You won’t be able to change this section after submitting.${a.sections.length===2&&a.section==='math'?' Your 45-minute logic section will start immediately.':''}</p><div class="flex justify-end gap-3"><button class="btn-quiet" data-action="close">Keep working</button><button class="btn-primary" data-action="confirm-section">Finish section</button></div>`);break;}
    case 'confirm-section': closeModal();takeAttempt(await api(`/attempts/${a.id}/section?section=${a.section}`,'POST'),true);window.scrollTo(0,0);break;
    case 'end': openModal(`<h2 class="text-xl font-semibold">Finish this session?</h2><p class="text-sm text-slate-500 my-4">Your saved answers will be graded and you’ll see a full review. Unanswered questions count as zero. You can’t resume this session after finishing.</p><div class="flex justify-end gap-3"><button class="btn-quiet" data-action="close">Keep working</button><button class="btn-primary" data-action="confirm-end">Finish & review</button></div>`);break;
    case 'confirm-end': closeModal();takeAttempt(await api(`/attempts/${a.id}/finish`,'POST'));window.scrollTo(0,0);break;
    case 'export-bank': {
      const blob=await api('/admin/questions/export'), url=URL.createObjectURL(blob), link=document.createElement('a');
      link.href=url;link.download='cst-studio-questions.zip';document.body.appendChild(link);link.click();link.remove();
      setTimeout(()=>URL.revokeObjectURL(url),1000);
      $('#archive-status').textContent='Export downloaded. The ZIP includes all questions and publication statuses.';
      break;
    }
    case 'logout': await api('/admin/logout','POST');renderLogin();break;
    case 'context': {const c=await api(`/admin/context/${$('#gen-section').value}`);openModal(`<h2 class="font-semibold text-xl mb-4">What the model receives</h2><pre class="whitespace-pre-wrap text-xs leading-relaxed max-h-[60vh] overflow-y-auto">${esc(c.system+'\n\n'+c.context)}</pre><button class="btn-secondary mt-5" data-action="close">Close</button>`);break;}
    case 'edit-question': editQuestion(el.dataset.id);break;
    case 'approve-all': {
      const result=await api(`/admin/questions/approve-all?section=${el.dataset.section}`,'POST');
      await loadAdminQuestions();
      toast(`${result.approved} question${result.approved===1?'':'s'} approved and published.`);
      break;
    }
    case 'publish': case 'reject': await api(`/admin/questions/${el.dataset.id}/${action}`,'POST');await loadAdminQuestions();toast(action==='publish'?'Question published to the practice bank.':'Question removed from the practice bank.');break;
  }
}
document.addEventListener('click',async e=>{
  const button=e.target.closest('[data-action]');if(!button||button.disabled||state.busy)return;
  e.preventDefault(); state.busy=true;button.disabled=true;
  try{await perform(button.dataset.action,button);}catch(error){toast(error.message);if(error.status===409&&state.attempt)try{takeAttempt(await api(`/attempts/${state.attempt.id}`));}catch{} }
  finally{state.busy=false;if(button.isConnected)button.disabled=false;}
});
window.addEventListener('online',()=>{if(state.attempt)api(`/attempts/${state.attempt.id}`).then(takeAttempt).catch(e=>toast(e.message));});
async function route() {
  if(location.pathname==='/admin'||location.hash.startsWith('#session/')) setLearnerState(await api('/account'));
  if(location.pathname==='/admin') await adminPage();
  else if(location.hash.startsWith('#session/')) {const id=location.hash.slice(9);takeAttempt(await api(`/attempts/${encodeURIComponent(id)}`),true);}
  else await home();
}
window.addEventListener('hashchange',()=>{
  if(location.hash.startsWith('#session/') && state.attempt?.id===location.hash.slice(9)) return;
  if(location.hash==='#resources'||location.hash==='#practice') {if(state.attempt) home().then(()=>$(location.hash)?.scrollIntoView());return;}
  route().catch(e=>toast(e.message));
});
route().catch(e=>{ main.innerHTML=`<section class="card p-8 my-12"><h1 class="font-semibold text-xl">We couldn’t open this session.</h1><p class="text-slate-500 mt-3">${esc(e.message)}</p><a href="/" class="btn-primary mt-5">Return to workspace</a></section>`; });
