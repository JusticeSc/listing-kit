/* NOT-AUTHORITY: temporary R2.2 layout prototype. Loaded only by the offline
   browser launcher; no domain writes, adapter substitution or default data. */
if (new URL(location.href).searchParams.get('prototype') !== 'workbench') {
  throw new Error('This prototype requires its explicit isolated launcher.');
}

const link = document.createElement('link');
link.rel = 'stylesheet';
link.href = '/harness/workbench-prototype.css';
document.head.append(link);
document.body.classList.add('workbench-prototype');
const banner = document.createElement('aside');
banner.id = 'prototype-banner';
banner.textContent = '临时交互原型 · 独立本地测试资料 · 复用真实保存/确认/核对处理器 · 不代表真人验收';
document.body.prepend(banner);

const review = document.querySelector('[data-stage-panel="review"]');
const task = document.createElement('div');
task.id = 'prototype-task';
const compare = document.querySelector('#compare-panel');
review.querySelector('.stage-head').after(task);
task.append(compare, document.querySelector('#rework-panel'), document.querySelector('#adopt-panel'));
const imagePlane = document.createElement('div');
imagePlane.id = 'prototype-image-plane';
compare.querySelector('.compare-head').after(imagePlane);
imagePlane.append(compare.querySelector('.compare-basis'), compare.querySelector('.compare-body > .compare-column'));

// Native dialogs preserve visible image context; the existing app remains the
// only business writer, including cancellation, confirmation and submission.
for (const [panelId, titleId, cancelId] of [
  ['rework-panel', 'rework-title', 'rework-cancel'],
  ['adopt-panel', 'adopt-title', 'adopt-cancel'],
]) {
  const panel = document.getElementById(panelId);
  const dialog = document.createElement('dialog');
  dialog.className = 'prototype-action-dialog';
  dialog.setAttribute('aria-labelledby', titleId);
  const pictures = document.createElement('div');
  pictures.className = 'prototype-dialog-context';
  dialog.append(pictures, panel);
  document.body.append(dialog);
  new MutationObserver(() => {
    if (!panel.hidden && !dialog.open) {
      pictures.replaceChildren(...[...compare.querySelectorAll('#compare-references img, .compare-card img')].map(source => {
        const figure = document.createElement('figure');
        const image = source.cloneNode();
        image.removeAttribute('id');
        const caption = document.createElement('figcaption');
        caption.textContent = source.alt || '当前 Shot 的参考与候选';
        figure.append(image, caption);
        return figure;
      }));
      dialog.showModal();
      if (panelId === 'rework-panel') document.getElementById('rework-direction').focus();
    } else if (panel.hidden && dialog.open) dialog.close();
  }).observe(panel, { attributes: true, attributeFilter: ['hidden'] });
  dialog.addEventListener('cancel', event => {
    event.preventDefault();
    document.getElementById(cancelId).click();
  });
}

// The source images and persisted identities still belong to the existing app.
const facts = document.querySelector('[data-stage-panel="understand"]');
const factContext = document.createElement('aside');
factContext.id = 'prototype-fact-context';
const heading = document.createElement('h4');
heading.textContent = '对照原始资料，再确认事实';
const help = document.createElement('p');
help.textContent = '模型提议不是事实。确认改变后，查看受影响的图片与发送摘要；不会自动生成。';
const gallery = document.createElement('div');
gallery.id = 'prototype-source-images';
factContext.append(heading, help, gallery);
const factWorkbench = document.createElement('div');
factWorkbench.id = 'prototype-fact-workbench';
facts.querySelector('.stage-head').after(factWorkbench);
factWorkbench.append(factContext, facts.querySelector('[aria-labelledby="slots-title"]'));
const impact = document.createElement('p');
impact.id = 'prototype-fact-impact';
impact.setAttribute('role', 'status');
const inspect = document.createElement('button');
inspect.type = 'button';
inspect.textContent = '检查受影响图片与发送摘要';
inspect.addEventListener('click', () => document.querySelector('[data-stage-nav="generate"]').click());
factContext.append(impact, inspect);
function renderImpact() {
  const stale = [...document.querySelectorAll('#prompt-list [data-prompt-state="stale"]')];
  const names = stale.map(row => row.querySelector('.name').textContent);
  impact.textContent = stale.length
    ? `发送摘要已失效：${names.join('、')}。重新编译并人工确认后才能生成；已有候选与人工采用记录保留。`
    : '当前没有失效的发送摘要；修改事实后在这里查看影响范围。';
}
new MutationObserver(renderImpact).observe(document.querySelector('#prompt-list'), { childList: true, subtree: true });
renderImpact();
function renderSources() {
  const images = [...document.querySelectorAll('#ref-list img')];
  gallery.replaceChildren(...images.map(source => {
    const figure = document.createElement('figure');
    const image = document.createElement('img');
    image.src = source.src;
    image.alt = source.alt || '用于事实核对的原始参考图';
    image.width = 240;
    image.height = 240;
    const caption = document.createElement('figcaption');
    caption.textContent = source.alt || '原始参考图';
    figure.append(image, caption);
    return figure;
  }));
}
new MutationObserver(renderSources).observe(document.querySelector('#ref-list'), { childList: true, subtree: true });
renderSources();

// Keep technical identity available, but put uncertainty and safe recovery first.
function explainUnknown() {
  for (const row of document.querySelectorAll('#attempt-list [data-attempt-state="unknown"]')) {
    if (row.querySelector('.prototype-recovery')) continue;
    const explanation = document.createElement('p');
    explanation.className = 'prototype-recovery';
    const queryVisible = [...row.querySelectorAll('.attempt-actions button')].some(button => button.textContent.trim() === '核对任务');
    explanation.textContent = queryVisible
      ? '结果尚未确定：已有原任务编号，请手动核对原任务；不会自动重提，成功历史与人工采用保留。'
      : '本次提交没有任务编号，不能直接查询，也不能认定失败，可能已经受理。保留未知记录；显式放弃核对后新建任务可能重复生成或计费。';
    const detail = document.createElement('details');
    detail.className = 'prototype-execution-details';
    const summary = document.createElement('summary');
    summary.textContent = '执行身份与错误详情';
    detail.append(summary);
    for (const node of [...row.querySelectorAll(':scope > .attempt-task, :scope > .attempt-error-text')]) detail.append(node);
    row.querySelector('.attempt-head').after(explanation, detail);
  }
}
new MutationObserver(explainUnknown).observe(document.querySelector('#attempt-list'), { childList: true, subtree: true });
explainUnknown();

// Dismissal delegates to actual cancel handlers; closing the action must not
// also bubble into the underlying compare view and discard its context.
const returnTargets = new Map();
document.addEventListener('click', event => {
  const button = event.target.closest('button');
  if (!button) return;
  if (button.id === 'rework-open') returnTargets.set('rework-panel', button);
  if (button.id === 'adopt-open') returnTargets.set('adopt-panel', button);
  const card = button.closest('.review-card');
  if (card) {
    const buttons = [...card.querySelectorAll('button')];
    if (buttons[0] === button) returnTargets.set('compare-panel', { shot: card.dataset.shotId, index: 0 });
    if (buttons[1] === button) returnTargets.set('rework-panel', { shot: card.dataset.shotId, index: 1 });
  }
  const panel = { 'rework-cancel': 'rework-panel', 'adopt-cancel': 'adopt-panel', 'compare-close': 'compare-panel' }[button.id];
  if (!panel) return;
  requestAnimationFrame(() => {
    const target = returnTargets.get(panel);
    const trigger = target?.shot
      ? document.querySelectorAll(`.review-card[data-shot-id="${CSS.escape(target.shot)}"] button`)[target.index]
      : target;
    if (trigger?.isConnected) trigger.focus();
  });
}, true);
document.addEventListener('keydown', event => {
  if (event.key !== 'Escape') return;
  const dialog = document.querySelector('.prototype-action-dialog[open]');
  if (dialog) {
    event.preventDefault();
    event.stopPropagation();
    dialog.querySelector('#rework-cancel, #adopt-cancel').click();
    return;
  }
  if (document.querySelector('dialog[open]')) return;
  if (!compare.hidden) {
    event.preventDefault();
    document.getElementById('compare-close').click();
  }
}, true);
document.body.dataset.prototypeReady = 'true';
