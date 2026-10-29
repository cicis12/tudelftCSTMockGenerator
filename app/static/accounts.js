'use strict';
function setLearnerState(data) {
  state.account = data.account;
  state.progress = data.progress;
  renderAccountNav();
}
function renderAccountNav() {
  const button = document.querySelector('#account-button');
  if (!button) return;
  button.disabled = state.attempt?.status === 'active';
  button.title = button.disabled ? 'Finish your session to manage your account.' : 'Your progress and account';
  button.innerHTML = state.account ? `<span class="account-avatar">${esc(state.account.username[0].toUpperCase())}</span><span class="account-nav-label">${esc(state.account.username)}</span>` : '<span aria-hidden="true">↗</span><span>Sign in</span>';
  button.setAttribute('aria-label', state.account ? `Account: ${state.account.username}` : 'Sign in to sync progress');
}
function nextReview(timestamp) {
  return timestamp ? new Date(timestamp * 1000).toLocaleDateString(undefined, {month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'}) : 'when new questions are added';
}
function progressPanel() {
  const p=state.progress;
  if(!p) return '';
  const resting=Object.values(p.sections).reduce((n,s)=>n+s.resting,0);
  const ready=Object.values(p.sections).reduce((n,s)=>n+s.available,0);
  return `<section id="learning-progress" class="progress-panel mb-7" aria-labelledby="progress-title">
    <div class="flex flex-wrap items-center justify-between gap-4 mb-6"><div class="flex items-center gap-3 min-w-0"><span class="progress-mark" aria-hidden="true">↗</span><div class="min-w-0"><p class="eyebrow !text-[#628884]">Your practice, remembered</p><h2 id="progress-title" class="text-lg font-semibold mt-1 break-words">${state.account?`Keep going, ${esc(state.account.username)}.`:'A little progress stays with you.'}</h2></div></div><span class="pill !bg-white/80 !text-teal">${state.account?'✓ Account sync on':'◉ Saved in this browser'}</span></div>
    <div class="grid grid-cols-3 gap-3 sm:gap-6"><div><p class="progress-number" data-progress="answered">${p.answered}</p><p class="progress-caption">answers checked</p></div><div><p class="progress-number text-teal" data-progress="resting">${resting}</p><p class="progress-caption">resting for ${p.cooldown_days} days</p></div><div><p class="progress-number" data-progress="ready">${ready}</p><p class="progress-caption">ready to practise</p></div></div>
    <div class="flex flex-wrap items-center justify-between gap-3 mt-6 pt-4 border-t border-teal/10"><p class="text-xs text-slate-600 max-w-xl leading-relaxed">Correct answers get a ${p.cooldown_days}-day break. Spend your energy on what still needs practice.</p>${state.account?'<button class="text-xs font-semibold text-teal" data-action="account">Manage account →</button>':'<button class="text-xs font-semibold text-teal" data-action="account">Take your progress to another device →</button>'}</div>
  </section>`;
}
function readinessPanel() {
  const p=state.progress;
  if(!p) return '';
  return `<section class="card p-6"><div class="flex items-center justify-between"><h2 class="font-semibold">Your next steps</h2><span class="text-teal text-xl" aria-hidden="true">◎</span></div><p class="text-xs text-slate-500 leading-relaxed mt-2">A fresh mix, with room to revisit what you’ve learned.</p><div class="mt-5 space-y-6">${Object.entries(p.sections).map(([s,v])=>`<div><div class="flex justify-between gap-2 text-sm"><span class="font-medium">${sectionName(s)}</span><span class="text-teal">${v.available} ready</span></div><progress class="readiness-progress w-full h-1.5 mt-3" max="${v.total||1}" value="${v.resting}" aria-label="${sectionName(s)} questions resting"></progress><div class="flex justify-between text-xs text-slate-400 mt-2"><span>${v.resting} resting</span><span>${v.total} in the bank</span></div>${v.next_review_at?`<p class="text-xs text-slate-500 mt-2">Next return: ${nextReview(v.next_review_at)}</p>`:''}</div>`).join('')}</div><p class="text-xs text-slate-500 mt-5 pt-4 border-t border-slate-100">${p.answered?`${p.correct_answers} correct out of ${p.answered} checked answers. Your next session builds on that.`:'Your first correct answer starts the cycle. No account needed.'}</p></section>`;
}
function accountDialog(mode='login') {
  if(state.attempt?.status==='active') { toast('Finish your session to manage your account.'); return; }
  if(state.account) {
    const p=state.progress;
    openModal(`<div class="flex justify-between items-start gap-3"><div class="account-avatar !w-14 !h-14 !text-xl">${esc(state.account.username[0].toUpperCase())}</div><button class="btn-quiet !px-2 !py-1" data-action="close" aria-label="Close account">×</button></div><p class="eyebrow mt-6">Your learning account</p><h2 class="text-2xl font-semibold mt-2 break-words">${esc(state.account.username)}</h2><p class="text-sm text-slate-500 mt-3 leading-relaxed">Sign in with this username on another device to carry your question progress and ${p.cooldown_days}-day cooldowns with you.</p><div class="rounded-xl bg-[#eef7f5] p-5 my-6 flex justify-between gap-4"><div><strong class="block text-2xl text-teal">${p.correct_questions}</strong><span class="text-xs text-slate-500">questions answered correctly</span></div><span class="pill self-start !bg-white !text-teal">✓ Sync on</span></div><p class="text-xs text-slate-500 leading-relaxed">Your progress syncs automatically when you practise. Test sessions and their reviews stay in the browser where they started. Signing out opens a fresh guest workspace here.</p><div class="flex justify-between gap-3 mt-6"><button class="btn-quiet !px-0" data-action="learner-signout">Sign out</button><button class="btn-primary" data-action="close">Back to practice →</button></div>`);
    return;
  }
  const register=mode==='register';
  openModal(`<div class="flex justify-between items-start gap-4"><span class="progress-mark !w-12 !h-12 !text-2xl" aria-hidden="true">↗</span><button class="btn-quiet !px-2 !py-1" data-action="close" aria-label="Close account">×</button></div><p class="eyebrow mt-5">Optional account · Same momentum</p><h2 class="text-2xl sm:text-3xl font-semibold mt-2">Your progress travels with you.</h2><p class="text-sm text-slate-500 leading-relaxed mt-3">Keep recently solved questions out of the way, whether you practise on your laptop or your phone.</p><div class="account-tabs mt-6" role="group" aria-label="Account action"><button type="button" data-action="account-login" class="${register?'':'active'}" aria-pressed="${!register}">Sign in</button><button type="button" data-action="account-register" class="${register?'active':''}" aria-pressed="${register}">Create account</button></div><form id="learner-form" class="space-y-4 mt-5"><div><label for="learner-username">Username</label><input id="learner-username" name="username" required minlength="3" maxlength="24" pattern="[A-Za-z0-9_]+" autocomplete="username" autocapitalize="none" spellcheck="false" placeholder="Your practice name" class="mt-1"><p class="text-xs text-slate-400 mt-1">3–24 letters, numbers or underscores. No email needed.</p></div><div><label for="learner-password">Password</label><input id="learner-password" name="password" type="password" required minlength="12" maxlength="128" autocomplete="${register?'new-password':'current-password'}" placeholder="At least 12 characters" class="mt-1"></div>${register?'<div><label for="learner-confirm">Confirm password</label><input id="learner-confirm" type="password" autocomplete="new-password" required minlength="12" maxlength="128" class="mt-1"></div>':''}<p id="learner-error" role="alert" class="text-sm text-rose-700"></p><button id="learner-submit" class="btn-primary w-full">${register?'Create account & sync':'Sign in & sync'} →</button><p class="text-xs text-slate-500 leading-relaxed">Your guest progress in this browser will be added to your account. Only question progress syncs; test sessions stay on this device.</p></form><button class="text-sm text-slate-500 hover:text-teal w-full mt-5 py-2" data-action="close">Continue without an account</button>`);
  $('#learner-form').addEventListener('input',()=>{ $('#learner-error').textContent=''; });
  $('#learner-form').addEventListener('submit',async e=>{
    e.preventDefault();const button=$('#learner-submit'), error=$('#learner-error');error.textContent='';
    if(register && $('#learner-password').value!==$('#learner-confirm').value) {error.textContent='The passwords don’t match.';return;}
    button.disabled=true;
    try {
      const data=await api(`/account/${mode}`,'POST',{username:$('#learner-username').value.trim(),password:$('#learner-password').value});
      setLearnerState(data);closeModal();
      if(location.pathname!=='/admin') {history.replaceState(null,'','/');await home();} else renderAccountNav();
      toast(register?'Account created. Your progress is ready to travel.':'Signed in. Your question progress is synced.');
    } catch(err) {error.textContent=err.message;button.disabled=false;}
  });
}
