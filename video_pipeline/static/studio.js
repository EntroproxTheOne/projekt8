document.querySelectorAll('nav a').forEach(link => { if(link.getAttribute('href') === location.pathname) link.setAttribute('aria-current', 'page'); });
const prompt = document.querySelector('[data-draft]');
if (prompt) {
  const key = 'projekt8:brief:' + prompt.dataset.draft;
  try { prompt.value = localStorage.getItem(key) || ''; } catch (_) {}
  prompt.addEventListener('input', () => { try { localStorage.setItem(key, prompt.value); } catch (_) {} });
}
document.querySelectorAll('[data-prompt]').forEach(button => button.addEventListener('click', () => {
  prompt.value = button.dataset.prompt; prompt.dispatchEvent(new Event('input')); prompt.focus();
}));
const hints = {video:'Scene images, narration, and a captioned video',image:'Scene images and a thumbnail from your idea',audio:'Narration audio and word timestamps from your idea'};
document.querySelectorAll('[name=output_mode]').forEach(input => input.addEventListener('change', () => {
  document.getElementById('mode-hint').textContent = hints[input.value];
}));
const projectFiles = document.getElementById('project-files');
if (projectFiles) {
  const list = document.getElementById('attachment-list');
  let chosen = [];
  function syncFiles() {
    const transfer = new DataTransfer();
    chosen.forEach(file => transfer.items.add(file));
    projectFiles.files = transfer.files;
    list.replaceChildren(...chosen.map((file, index) => {
      const row = document.createElement('div'); row.className = 'attachment-item';
      const label = document.createElement('span'); label.textContent = `${file.name} · ${(file.size / 1024 / 1024).toFixed(1)} MB`;
      const remove = document.createElement('button'); remove.type = 'button'; remove.textContent = 'Remove';
      remove.addEventListener('click', () => { chosen.splice(index, 1); syncFiles(); });
      row.append(label, remove); return row;
    }));
  }
  projectFiles.addEventListener('change', () => {
    chosen = [...chosen, ...Array.from(projectFiles.files)].filter((file, index, files) =>
      files.findIndex(item => item.name === file.name && item.size === file.size) === index);
    syncFiles();
  });
  document.querySelectorAll('[name=workflow]').forEach(input => input.addEventListener('change', () => {
    projectFiles.required = input.checked && input.value === 'caption_existing';
  }));
}
const projectForm = document.getElementById('project-form');
if (projectForm) projectForm.addEventListener('submit', event => {
  event.preventDefault();
  const progressBox = document.getElementById('upload-progress');
  const progress = progressBox.querySelector('progress');
  const progressLabel = document.getElementById('upload-progress-label');
  const status = document.getElementById('project-form-status');
  const button = projectForm.querySelector('button[type=submit]');
  const request = new XMLHttpRequest();
  progressBox.hidden = false; progress.value = 0; status.textContent = 'Saving project and uploading sources locally…';
  button.disabled = true; button.textContent = 'Uploading…';
  request.upload.addEventListener('progress', upload => {
    if (!upload.lengthComputable) return;
    const percent = Math.round(upload.loaded / upload.total * 100);
    progress.value = percent; progressLabel.textContent = `Uploading sources · ${percent}%`;
  });
  request.addEventListener('load', () => {
    if (request.status >= 200 && request.status < 400) {
      status.textContent = 'Upload complete. Opening storyboard…';
      location.href = request.responseURL;
      return;
    }
    let message = `Upload failed (${request.status}).`;
    try { message = JSON.parse(request.responseText).detail || message; } catch (_) {}
    status.textContent = message; progressBox.hidden = true; button.disabled = false; button.textContent = 'Analyze & build storyboard ↗';
  });
  request.addEventListener('error', () => {
    status.textContent = 'Upload failed because the local server connection was interrupted.';
    progressBox.hidden = true; button.disabled = false; button.textContent = 'Analyze & build storyboard ↗';
  });
  request.open('POST', projectForm.action); request.send(new FormData(projectForm));
});
document.querySelectorAll('form:not(#markup-form)').forEach(form => form.addEventListener('submit', () => {
  const button = form.querySelector('button[type=submit]');
  if (button) {button.disabled = true;button.textContent = 'Working…';}
}));
const markupForm = document.getElementById('markup-form');
if (markupForm) {
  const picker = document.getElementById('screenshot');
  const status = document.getElementById('markup-status');
  const generate = document.getElementById('generate-markup');
  const result = document.getElementById('markup-result');
  const code = document.getElementById('markup-code');
  let selected = null, imageUrl = null, busy = false;
  function selectImage(file) {
    if (busy) return;
    selected = null; generate.disabled = true; result.hidden = true;
    if (imageUrl) URL.revokeObjectURL(imageUrl);
    document.getElementById('image-selection').hidden = true;
    status.textContent = '';
    if (!file) return;
    if (!['image/png','image/jpeg','image/webp'].includes(file.type) || file.size > 8 * 1024 * 1024) {
      status.textContent = 'Choose a PNG, JPEG or WebP image smaller than 8 MB.'; picker.value = ''; return;
    }
    selected = file;
    imageUrl = URL.createObjectURL(file);
    document.getElementById('source-preview').src = imageUrl;
    document.getElementById('image-name').textContent = file.name;
    document.getElementById('image-selection').hidden = false;
    generate.disabled = false;
  }
  picker.addEventListener('change', () => selectImage(picker.files[0]));
  document.getElementById('remove-image').addEventListener('click', () => {picker.value = '';selectImage(null);});
  const zone = document.getElementById('drop-zone');
  zone.addEventListener('dragover', event => {event.preventDefault();zone.classList.add('dragging');});
  zone.addEventListener('dragleave', () => zone.classList.remove('dragging'));
  zone.addEventListener('drop', event => {
    event.preventDefault(); zone.classList.remove('dragging');
    if (busy) return;
    picker.required = false; selectImage(event.dataTransfer.files[0]);
  });
  function preview() {
    const parsed = new DOMParser().parseFromString(code.value, 'text/html');
    parsed.querySelectorAll('script,iframe,frame,object,embed,base,meta[http-equiv],link').forEach(node => node.remove());
    parsed.querySelectorAll('*').forEach(node => Array.from(node.attributes).forEach(attr => {
      if (/^on/i.test(attr.name) || ['href','action','formaction','srcdoc'].includes(attr.name)) node.removeAttribute(attr.name);
    }));
    const policy = parsed.createElement('meta');
    policy.httpEquiv = 'Content-Security-Policy';
    policy.content = "default-src 'none'; style-src 'unsafe-inline'; img-src data:; font-src data:; form-action 'none'; base-uri 'none'";
    parsed.head.prepend(policy);
    document.getElementById('markup-preview').srcdoc = '<!doctype html>' + parsed.documentElement.outerHTML;
  }
  markupForm.addEventListener('submit', async event => {
    event.preventDefault();
    if (!selected || busy) return;
    busy = true; generate.disabled = true; picker.disabled = true;
    document.getElementById('remove-image').disabled = true;
    generate.textContent = 'Recreating…'; status.textContent = 'Reading the layout and generating HTML. This may take up to two minutes.';
    result.hidden = true;
    const body = new FormData(); body.append('image', selected);
    try {
      const response = await fetch('/api/markup/generate', {method:'POST',body});
      const data = await response.json();
      if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Generation failed. Please retry.');
      code.value = data.html; preview(); result.hidden = false;
      status.textContent = 'Your HTML is ready. Review, edit, and download it below.';
    } catch (error) {status.textContent = error.message || 'Generation failed. Please retry.';}
    finally {
      busy = false;generate.disabled = false;picker.disabled = false;
      document.getElementById('remove-image').disabled = false;generate.textContent = 'Generate HTML ↗';
    }
  });
  document.getElementById('refresh-preview').addEventListener('click', preview);
  document.getElementById('download-html').addEventListener('click', () => {
    const url = URL.createObjectURL(new Blob([code.value], {type:'text/html;charset=utf-8'}));
    const link = document.createElement('a');link.href = url;link.download = 'projekt8-page.html';link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
}
