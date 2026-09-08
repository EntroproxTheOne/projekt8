from fastapi.responses import HTMLResponse

ICONS = {
    'media': '<rect x="3" y="4" width="18" height="16" rx="3"/><circle cx="8" cy="9" r="1.5"/><path d="m3 17 5-5 4 4 3-3 6 5"/>',
    '3d': '<path d="m12 2 9 5v10l-9 5-9-5V7l9-5Zm0 10 9-5M12 12 3 7m9 5v10"/>',
    'presentation': '<rect x="3" y="3" width="18" height="14" rx="2"/><path d="M12 17v5m-5 0 5-5 5 5M7 8h10M7 12h6"/>',
    'markup': '<path d="m8 6-6 6 6 6m8-12 6 6-6 6m-3-15-2 18"/>',
    'gallery': '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
    'spark': '<path d="m12 3 1.5 5.5L19 10l-5.5 1.5L12 17l-1.5-5.5L5 10l5.5-1.5L12 3Z"/><path d="m19 16 .7 2.3L22 19l-2.3.7L19 22l-.7-2.3L16 19l2.3-.7L19 16Z"/>',
    'play': '<path d="m8 5 11 7-11 7V5Z"/>',
    'image': '<rect x="3" y="4" width="18" height="16" rx="3"/><circle cx="8.5" cy="9" r="1.5"/><path d="m4 17 5-5 3 3 2-2 6 5"/>',
    'audio': '<path d="M9 18V5l10-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="16" cy="16" r="3"/>',
}
def icon(name):
    return f'<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{ICONS[name]}</svg>'

def page(content: str, head_extra: str = '') -> HTMLResponse:
    nav = ''.join(f'<a href="{url}">{icon(key)}<span>{label}</span></a>' for key, label, url in [
        ('media', 'Create', '/'), ('3d', '3D Studio', '/studios/3d'),
        ('presentation', 'Presentation Studio', '/studios/presentation'), ('markup', 'Markup Studio', '/studios/markup')])
    return HTMLResponse(f'''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Projekt8 · Creative workspace</title>
<link rel="stylesheet" href="/static/studio.css">{head_extra}<script src="/static/studio.js" defer></script></head>
<body><a class="skip" href="#workspace">Skip to workspace</a><aside class="sidebar">
<a class="brand" href="/" aria-label="Projekt8 home"><span class="brand-mark">P8</span><span>projekt8<small>Creative OS</small></span></a>
<p class="nav-label">WORKSPACE</p><nav aria-label="Studios">{nav}</nav>
<p class="nav-label">LIBRARY</p><nav aria-label="Library"><a href="/gallery">{icon('gallery')}My creations</a><a href="/prompt-packs">{icon('markup')}Prompt Packs</a></nav>
<details class="more"><summary>More tools</summary><nav><a href="/builder">Pipeline Builder</a><a href="/privacy">Privacy Tools</a></nav></details>
<div class="sidebar-bottom"><a href="/settings">Provider settings <span>↗</span></a><div class="profile"><span class="avatar">P</span><div>Personal workspace<small>Private · local</small></div></div></div>
</aside><div class="app"><header class="topbar"><span>Personal workspace <span class="slash">/</span> Create</span><span class="local"><i></i> Local storage · online AI processing</span></header><main id="workspace">{content}</main><footer>Projekt8 <span>Make something worth sharing.</span></footer></div></body></html>''')

STUDIOS = {
 '3d': ('3D Studio', 'Give your images another dimension.', 'Turn a reference image into a 3D asset using your custom model.', 'Image → Custom model → 3D asset', 'The custom model is not connected yet. Generation needs a model endpoint, input format, and supported output format.', 'Describe the object, materials, and details you want to preserve…'),
 'presentation': ('Presentation Studio', 'From a rough idea to a clear story.', 'Bring your text and images together in a presentation.', 'Text + images → Slide layout → PowerPoint', 'Presentation generation and PowerPoint export are not connected yet.', 'What is your presentation about? Include your audience and key points…'),
 'markup': ('Markup Studio', 'Turn a screenshot into a starting point.', 'Recreate a chat, social post, or interface as editable HTML.', 'Screenshot → Layout extraction → HTML + CSS', 'Screenshot interpretation and HTML generation are not connected yet.', 'Describe the screenshot and what you would like to recreate…'),
}

def studio_content(studio='media'):
    if studio == 'markup':
        return markup_content()
    if studio != 'media':
        title, heading, description, pipeline, limitation, placeholder = STUDIOS[studio]
        return f'''<div class="eyebrow">{icon(studio)} {title}</div><h1>{heading}</h1><p class="subtitle">{description}</p>
<section class="composer"><div class="composer-heading"><strong>Your brief</strong><span class="badge">Coming soon</span></div>
<label class="sr-only" for="brief">Your brief</label><textarea id="brief" data-draft="{studio}" placeholder="{placeholder}"></textarea>
<div class="composer-bottom"><span class="muted">Brief saved in this browser as you type</span><button disabled>Generate <span>↗</span></button></div></section>
<div class="notice"><strong>Integration needed</strong><p>{limitation}</p></div><section class="workflow"><h2>The workflow</h2><p>{pipeline}</p></section>'''
    return '''<section class="home-hero"><div class="hero-copy"><div class="eyebrow"><span class="eyebrow-dot"></span> AI VIDEO WORKSPACE</div><h1>One brief.<br><em>A real video.</em></h1><p class="subtitle">Bring text, images, footage, audio, and PDFs together. Review every scene before Projekt8 generates a single clip.</p><div class="hero-proof"><span><b>01</b> Add sources</span><span><b>02</b> Approve scenes</span><span><b>03</b> Generate video</span></div></div>
<div class="hero-art" aria-hidden="true"><div class="orbit orbit-one"><span></span></div><div class="orbit orbit-two"><span></span></div><div class="art-core">P8<small>IDEA ENGINE</small></div><span class="art-chip chip-video">VIDEO</span><span class="art-chip chip-image">IMAGE</span><span class="art-chip chip-audio">AUDIO</span></div></section>
<section class="create-section" aria-labelledby="create-title"><div class="create-heading"><div><span class="section-kicker">START A VIDEO PROJECT</span><h2 id="create-title">Give the story everything it needs.</h2></div><p>Files stay in your local project library and are sent to selected online AI providers during analysis and generation.</p></div>
<form id="project-form" class="composer project-composer" method="post" action="/projects" enctype="multipart/form-data">
<div class="workflow-picker" role="group" aria-label="Video workflow"><label><input type="radio" name="workflow" value="generate" checked><span>Generate new video<small>Plan and create new Omni clips</small></span></label><label><input type="radio" name="workflow" value="caption_existing"><span>Caption existing footage<small>Keep footage and add editable captions</small></span></label></div>
<label class="sr-only" for="idea">Describe the video you want to create</label><textarea id="idea" name="brief" required maxlength="24000" placeholder="Describe the story, audience, mood, characters, dialogue, and anything that must be preserved…" data-draft="media"></textarea>
<div class="attachment-picker"><label for="project-files"><span>＋ Add references</span><small>Images, audio, video, or PDFs · multiple files supported</small></label><input id="project-files" name="files" type="file" multiple accept="image/png,image/jpeg,image/webp,audio/*,video/*,application/pdf"><div id="attachment-list" class="attachment-list" aria-live="polite"></div></div>
<div class="project-options"><label>Duration <span><input name="duration_seconds" type="number" min="3" max="3600" value="60" required> seconds</span></label><label>Frame <select name="aspect_ratio"><option value="9:16">Portrait · 9:16</option><option value="16:9">Landscape · 16:9</option></select></label><label>Quality <select name="resolution"><option value="720p">720p</option><option value="1080p">1080p</option><option value="360p">360p</option><option value="4k">4K upscale</option></select></label><label class="check"><input name="tts_override" type="checkbox" value="true"> Replace native speech with Deepgram TTS</label></div>
<div class="upload-progress" id="upload-progress" hidden><span id="upload-progress-label">Uploading sources…</span><progress max="100" value="0"></progress></div>
<div class="composer-bottom"><span class="muted" id="project-form-status" role="status" aria-live="polite">Analysis uses Gemini → Groq → Grok fallback. Video generation only begins after scene approval.</span><button type="submit">Analyze & build storyboard <span>↗</span></button></div>
</form></section>
<section class="studios-section"><div class="section-heading"><div><span class="section-kicker">SPECIALIST TOOLS</span><h2>More ways to make</h2></div><span>One workspace, more possibilities</span></div><div class="studio-grid">''' + ''.join(f'''<a class="studio-card {key}" href="/studios/{key}"><div class="card-top"><span class="studio-icon {key}">{icon(key)}</span><span class="badge">{"READY" if key == "markup" else "SOON"}</span></div><div class="card-number">0{i}</div><h3>{title} <span>↗</span></h3><p>{desc}</p><span class="card-cta">{"Open studio" if key == "markup" else "Explore workflow"}</span></a>''' for i,(key,title,desc) in enumerate([('3d','3D Studio','Transform a reference image into a dimensional asset.'),('presentation','Presentation Studio','Shape raw notes and images into a clear visual story.'),('markup','Markup Studio','Turn any screenshot into editable HTML and CSS.')], 1)) + '''</div></section><section class="workflow"><span class="section-kicker">HOW IT WORKS</span><h2>From first thought to final cut.</h2><div class="workflow-steps"><p><b>01</b><span>Plan</span>Projekt8 structures your idea.</p><i>→</i><p><b>02</b><span>Generate</span>Create visuals, voice, and captions.</p><i>→</i><p><b>03</b><span>Finish</span>Review, render, and download.</p></div></section>'''


def markup_content():
    return f'''<div class="eyebrow">{icon('markup')} Markup Studio</div><h1>A screenshot. A starting point.</h1><p class="subtitle">Turn a chat, social post, or interface into editable HTML and CSS.</p>
<form id="markup-form" class="composer" enctype="multipart/form-data">
<div class="composer-heading"><strong>Your screenshot</strong><span class="badge">Image to HTML</span></div>
<label class="image-picker" id="drop-zone" for="screenshot"><span class="picker-icon">{icon('gallery')}</span><strong>Choose an image</strong><span>Browse your gallery or files, or drop a screenshot here</span><small>PNG, JPEG or WebP · up to 8 MB</small><input id="screenshot" name="image" type="file" accept="image/png,image/jpeg,image/webp" required></label>
<div id="image-selection" hidden><img id="source-preview" alt="Selected screenshot"><p id="image-name"></p><button id="remove-image" type="button" class="secondary">Remove image</button></div>
<div class="composer-bottom"><span class="muted">Generate sends this image to Gemini. Your upload is not saved on the server.</span><button id="generate-markup" type="submit" disabled>Generate HTML ↗</button></div>
</form><p id="markup-status" role="status" aria-live="polite"></p>
<section id="markup-result" hidden><div class="section-heading"><h2>Your page</h2><div class="result-actions"><button type="button" class="secondary" id="refresh-preview">Update preview</button><button type="button" id="download-html">Download HTML ↓</button></div></div><p class="muted">Edit the HTML below, then update the preview. Scripts and external resources are blocked in the preview.</p><div class="markup-output"><iframe title="Generated page preview" id="markup-preview" sandbox="" referrerpolicy="no-referrer"></iframe><div><label for="markup-code">HTML + CSS</label><textarea id="markup-code" spellcheck="false"></textarea></div></div></section>
<section class="workflow"><h2>The workflow</h2><p>01 &nbsp; Choose an image <span>→</span> 02 &nbsp; Recreate the layout <span>→</span> 03 &nbsp; Edit & export</p></section>'''
