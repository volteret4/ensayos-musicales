CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: "Segoe UI", system-ui, sans-serif; background: #0d1117;
       color: #c9d1d9; display: flex; height: 100vh; overflow: hidden; }

/* ── Sidebar ── */
#sidebar { width: 280px; min-width: 280px; background: #161b22;
           border-right: 1px solid #30363d; display: flex;
           flex-direction: column; flex-shrink: 0; overflow: hidden; }

#sb-header { display: flex; align-items: center; justify-content: space-between;
             padding: 10px 12px; border-bottom: 1px solid #30363d; gap: 8px; flex-shrink: 0; }
#sb-header h1 { font-size: 0.82rem; color: #e94560; letter-spacing: 0.06em;
                text-transform: uppercase; white-space: nowrap; }

#btn-rebuild { background: #238636; color: #fff; border: none; border-radius: 5px;
               padding: 5px 10px; font-size: 0.75rem; cursor: pointer; white-space: nowrap;
               flex-shrink: 0; }
#btn-rebuild:hover    { background: #2ea043; }
#btn-rebuild.spinning { background: #555; cursor: wait; pointer-events: none; }

/* ── Tab bar ── */
#tab-bar { display: flex; flex-shrink: 0; border-bottom: 1px solid #30363d; background: #0d1117; }
.tab-btn { flex: 1; padding: 8px 2px; background: none; border: none;
           border-bottom: 2px solid transparent; color: #484f58; cursor: pointer;
           font-size: 0.82rem; transition: color 0.1s; }
.tab-btn:hover  { color: #c9d1d9; }
.tab-btn.active { color: #58a6ff; border-bottom-color: #58a6ff; }

/* ── Panels ── */
.panel { display: none; flex-direction: column; flex: 1; min-height: 0; overflow: hidden; }
.panel.active { display: flex; }

.panel-search-wrap { padding: 8px 10px; flex-shrink: 0; border-bottom: 1px solid #21262d; }
.panel-search { width: 100%; padding: 6px 10px; background: #0d1117; color: #c9d1d9;
                border: 1px solid #30363d; border-radius: 6px; font-size: 0.82rem; outline: none; }
.panel-search:focus { border-color: #58a6ff; }
.panel-count { padding: 4px 14px; font-size: 0.68rem; color: #484f58; flex-shrink: 0; }
.panel-list  { flex: 1; overflow-y: auto; padding: 4px 0; }

.list-item { padding: 7px 14px; font-size: 0.84rem; cursor: pointer;
             border-left: 3px solid transparent; color: #8b949e;
             display: flex; align-items: center; justify-content: space-between;
             transition: background 0.1s; }
.list-item:hover  { background: #1c2128; color: #c9d1d9; border-left-color: #30363d; }
.list-item.active { background: #1c2128; color: #58a6ff; border-left-color: #58a6ff; font-weight: 600; }
.list-item mark   { background: none; color: #f0883e; font-weight: bold; }
.list-name { overflow: hidden; text-overflow: ellipsis; flex: 1; min-width: 0; }
.list-del  { opacity: 0; background: none; border: none; color: #da3633;
             cursor: pointer; font-size: 0.85rem; padding: 0 2px; flex-shrink: 0; }
.list-item:hover .list-del { opacity: 1; }
.list-del:hover { color: #f85149; }

/* ── Content area ── */
#content { flex: 1; overflow-y: auto; padding: 32px 40px; }
#placeholder { display: flex; align-items: center; justify-content: center;
               height: 100%; color: #484f58; font-size: 1rem; }
#entity-detail { max-width: 860px; }
#entity-detail h1 { font-size: 2rem; font-weight: 700; color: #e6edf3;
                    margin-bottom: 10px; line-height: 1.2; }

/* ── Entity toolbar ── */
.entity-toolbar { display: flex; align-items: center; gap: 8px; margin-bottom: 20px; flex-wrap: wrap; }
.entity-badge { display: inline-block; font-size: 0.7rem; padding: 2px 10px;
                border-radius: 12px; font-weight: 700; letter-spacing: 0.06em;
                text-transform: uppercase; }
.btn-del-entity { background: #21262d; color: #f85149; border: 1px solid #da3633;
                  border-radius: 5px; padding: 4px 10px; font-size: 0.75rem; cursor: pointer; }
.btn-del-entity:hover { background: #da3633; color: #fff; }

.member-of-line { font-size: 0.85rem; color: #8b949e; margin-bottom: 18px; }
.member-of-line a { color: #58a6ff; text-decoration: none; cursor: pointer; }
.member-of-line a:hover { text-decoration: underline; }

/* ── Sections ── */
.section { margin-bottom: 26px; }
.section-header { display: flex; align-items: center; justify-content: space-between;
                  padding-bottom: 6px; border-bottom: 1px solid #21262d; margin-bottom: 10px; }
.section-title { font-size: 0.7rem; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; }
.btn-del-section { background: none; border: 1px solid #30363d; color: #8b949e;
                   border-radius: 4px; padding: 2px 8px; font-size: 0.7rem; cursor: pointer; }
.btn-del-section:hover { background: #da3633; color: #fff; border-color: #da3633; }

/* ── Tag list (members, genres…) ── */
.tag-list { display: flex; flex-wrap: wrap; gap: 6px; }
.tag { display: inline-flex; align-items: center; gap: 4px; padding: 3px 8px 3px 10px;
       border-radius: 20px; font-size: 0.78rem; border: 1px solid; }
.tag-name { cursor: default; }
.tag-name.linked { cursor: pointer; }
.tag-name.linked:hover { text-decoration: underline; }
.tag-del { background: none; border: none; cursor: pointer; font-size: 0.7rem;
           opacity: 0.4; padding: 0; line-height: 1; }
.tag-del:hover { opacity: 1; color: #f85149; }

/* ── Entry cards ── */
.card { background: #161b22; border: 1px solid #21262d; border-radius: 8px;
        padding: 12px 14px; margin-bottom: 8px; border-left: 3px solid; }
.card-header { display: flex; align-items: flex-start; justify-content: space-between;
               gap: 8px; margin-bottom: 4px; }
.card-title { font-size: 0.9rem; font-weight: 600; color: #e6edf3; flex: 1; }
.card-actions { display: flex; gap: 4px; flex-shrink: 0; opacity: 0; transition: opacity 0.15s; }
.card:hover .card-actions { opacity: 1; }
.btn-edit, .btn-del { background: none; border: 1px solid #30363d; border-radius: 4px;
                      padding: 2px 7px; font-size: 0.72rem; cursor: pointer; color: #8b949e; }
.btn-edit:hover { background: #1f6feb; color: #fff; border-color: #1f6feb; }
.btn-del:hover  { background: #da3633; color: #fff; border-color: #da3633; }
.card-body { font-size: 0.85rem; line-height: 1.6; color: #8b949e; }
.card-source { margin-top: 6px; font-size: 0.72rem; }
.card-source a     { color: #388bfd; text-decoration: none; }
.card-source a:hover { text-decoration: underline; }
.card-source span  { color: #484f58; }

/* ── Inline edit form ── */
.edit-form { display: none; flex-direction: column; gap: 7px; margin-top: 8px; }
.edit-form.open { display: flex; }
.edit-title { width: 100%; background: #0d1117; color: #e6edf3; border: 1px solid #30363d;
              border-radius: 5px; padding: 5px 8px; font-size: 0.88rem; font-family: inherit; outline: none; }
.edit-desc  { width: 100%; background: #0d1117; color: #c9d1d9; border: 1px solid #30363d;
              border-radius: 5px; padding: 5px 8px; font-size: 0.84rem; font-family: inherit;
              resize: vertical; min-height: 80px; outline: none; }
.edit-title:focus, .edit-desc:focus { border-color: #58a6ff; }
.edit-btns { display: flex; gap: 6px; }
.btn-save   { background: #238636; color: #fff; border: none; border-radius: 5px;
              padding: 5px 14px; font-size: 0.78rem; cursor: pointer; }
.btn-save:hover   { background: #2ea043; }
.btn-cancel { background: #21262d; color: #8b949e; border: 1px solid #30363d;
              border-radius: 5px; padding: 5px 14px; font-size: 0.78rem; cursor: pointer; }
.btn-cancel:hover { color: #c9d1d9; background: #30363d; }

/* ── Toast ── */
#toast { position: fixed; bottom: 18px; right: 18px; background: #161b22;
         border: 1px solid #30363d; border-radius: 8px; padding: 12px 16px;
         font-size: 0.82rem; max-width: 420px; display: none; z-index: 200; }
#toast.show { display: block; }
#toast.ok  { border-color: #238636; color: #3fb950; }
#toast.err { border-color: #da3633; color: #f85149; }
#toast pre { font-size: 0.72rem; color: #8b949e; margin-top: 6px;
             white-space: pre-wrap; max-height: 130px; overflow-y: auto; }

/* ── Transition helpers ── */
.removing { opacity: 0; transform: translateX(14px);
            transition: opacity 0.2s, transform 0.2s; pointer-events: none; }

::-webkit-scrollbar { width: 5px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: #30363d; border-radius: 3px; }
"""

_BODY = """
<div id="sidebar">
  <div id="sb-header">
    <h1>🎵 Music Editor</h1>
    <button id="btn-rebuild">⚙ Rebuild DB</button>
  </div>
  <div id="tab-bar">
    <button class="tab-btn active" data-tab="artists">🎤 Art.</button>
    <button class="tab-btn" data-tab="genres">🎵 Gén.</button>
    <button class="tab-btn" data-tab="labels">💿 Sell.</button>
    <button class="tab-btn" data-tab="concerts">🎪 Conc.</button>
    <button class="tab-btn" data-tab="instruments">🎸 Inst.</button>
    <button class="tab-btn" data-tab="curiosities">✨ Gen.</button>
  </div>

  <div id="panel-artists" class="panel active">
    <div class="panel-search-wrap">
      <input id="search-artists" class="panel-search" type="text"
             placeholder="Buscar artista…" autocomplete="off">
    </div>
    <div id="artist-count" class="panel-count"></div>
    <div id="artist-list"  class="panel-list"></div>
  </div>

  <div id="panel-genres" class="panel">
    <div class="panel-search-wrap">
      <input id="search-genres" class="panel-search" type="text"
             placeholder="Buscar género…" autocomplete="off">
    </div>
    <div id="genre-count" class="panel-count"></div>
    <div id="genre-list"  class="panel-list"></div>
  </div>

  <div id="panel-labels" class="panel">
    <div class="panel-search-wrap">
      <input id="search-labels" class="panel-search" type="text"
             placeholder="Buscar sello…" autocomplete="off">
    </div>
    <div id="label-count" class="panel-count"></div>
    <div id="label-list"  class="panel-list"></div>
  </div>

  <div id="panel-concerts" class="panel">
    <div class="panel-search-wrap">
      <input id="search-concerts" class="panel-search" type="text"
             placeholder="Buscar concierto…" autocomplete="off">
    </div>
    <div id="concert-count" class="panel-count"></div>
    <div id="concert-list"  class="panel-list"></div>
  </div>

  <div id="panel-instruments" class="panel">
    <div class="panel-search-wrap">
      <input id="search-instruments" class="panel-search" type="text"
             placeholder="Buscar instrumento…" autocomplete="off">
    </div>
    <div id="instrument-count" class="panel-count"></div>
    <div id="instrument-list"  class="panel-list"></div>
  </div>

  <div id="panel-curiosities" class="panel">
    <div class="panel-search-wrap">
      <input id="search-curiosities" class="panel-search" type="text"
             placeholder="Buscar curiosidad…" autocomplete="off">
    </div>
    <div id="curiosity-count" class="panel-count"></div>
    <div id="curiosity-list"  class="panel-list"></div>
  </div>
</div>

<div id="content">
  <div id="placeholder">← Selecciona un elemento para editar</div>
</div>

<div id="toast"></div>
"""

_JS = r"""
// ── Store: avoids escaping values inside HTML attributes ──────────────────────
const _S = new Map(); let _sid = 0;
function store(d) { const id = ++_sid; _S.set(id, d); return id; }
function get(id)  { return _S.get(+id); }

// ── Constants ─────────────────────────────────────────────────────────────────
const SEC_COLORS = {
  members:'#e67e22', member_of:'#e67e22', genres:'#2ecc71', labels:'#f39c12',
  concerts:'#1abc9c', instruments:'#9b59b6', albums:'#3498db', songs:'#5dade2',
  curiosities:'#95a5a6',
};
const SEC_LABELS = {
  members:'Miembros', member_of:'Miembro de', genres:'Géneros', labels:'Sellos',
  concerts:'Conciertos', instruments:'Instrumentos', albums:'Álbumes',
  songs:'Canciones', curiosities:'Curiosidades',
};
const E_COLORS = {genre:'#2ecc71', label:'#f39c12', concert:'#1abc9c', instrument:'#9b59b6'};
const E_LABEL  = {genre:'Género',  label:'Sello',   concert:'Concierto', instrument:'Instrumento'};

let DATA = null;
const byId = {};           // artist id → artist object
let activeEntity = null;   // {type, name} currently displayed

// ── API ───────────────────────────────────────────────────────────────────────
async function api(ep, body) {
  const r = await fetch(ep, {method:'POST',
    headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)});
  return r.json();
}

// ── Toast ─────────────────────────────────────────────────────────────────────
let _tt;
function toast(msg, type='ok', detail='') {
  const el = document.getElementById('toast');
  el.className = 'show ' + type;
  el.innerHTML = msg + (detail ? `<pre>${detail}</pre>` : '');
  clearTimeout(_tt);
  if (type === 'ok') _tt = setTimeout(() => { el.className = ''; }, 4000);
}

// ── Data loading ──────────────────────────────────────────────────────────────
async function loadData() {
  const r = await fetch('/api/data');
  DATA = await r.json();
  if (DATA.error) { toast(DATA.error, 'err'); return; }
  for (const a of DATA.artists) byId[a.id] = a;
  renderAllLists();
}

// ── Tabs ──────────────────────────────────────────────────────────────────────
document.querySelectorAll('.tab-btn').forEach(b =>
  b.addEventListener('click', () => {
    document.querySelectorAll('.tab-btn').forEach(x => x.classList.toggle('active', x === b));
    document.querySelectorAll('.panel').forEach(p =>
      p.classList.toggle('active', p.id === 'panel-' + b.dataset.tab));
  })
);

// ── Sidebar lists ─────────────────────────────────────────────────────────────
function hl(text, q) {
  if (!q) return text;
  const i = text.toLowerCase().indexOf(q.toLowerCase());
  if (i < 0) return text;
  return text.slice(0,i)+'<mark>'+text.slice(i,i+q.length)+'</mark>'+text.slice(i+q.length);
}

function renderList(items, listId, countId, q, etype, clickFn) {
  const listEl = document.getElementById(listId);
  const cntEl  = document.getElementById(countId);
  listEl.innerHTML = '';
  let n = 0;
  for (const item of items) {
    const name = item.name ?? item;
    if (q && !name.toLowerCase().includes(q.toLowerCase())) continue;
    n++;
    const sid = store({action:'delete-entity', type:etype, name});
    const div = document.createElement('div');
    div.className = 'list-item';
    div.innerHTML = `<span class="list-name">${hl(name, q)}</span>
      <button class="list-del" data-sid="${sid}" title="Eliminar">✕</button>`;
    div.querySelector('.list-name').addEventListener('click', () => {
      document.querySelectorAll('.list-item').forEach(el => el.classList.remove('active'));
      div.classList.add('active');
      clickFn(item);
    });
    listEl.appendChild(div);
  }
  cntEl.textContent = `${n} elemento${n!==1?'s':''}`;
}

function renderCuriosityList(items, q) {
  const listEl = document.getElementById('curiosity-list');
  const cntEl  = document.getElementById('curiosity-count');
  listEl.innerHTML = ''; let n = 0;
  for (const c of items) {
    if (q && !c.title.toLowerCase().includes(q.toLowerCase())) continue;
    n++;
    const div = document.createElement('div');
    div.className = 'list-item';
    div.innerHTML = `<span class="list-name">${hl(c.title, q)}</span>`;
    div.querySelector('.list-name').addEventListener('click', () => {
      document.querySelectorAll('.list-item').forEach(el => el.classList.remove('active'));
      div.classList.add('active');
      showGenCuriosity(c);
    });
    listEl.appendChild(div);
  }
  cntEl.textContent = `${n} elemento${n!==1?'s':''}`;
}

function renderAllLists(q={}) {
  if (!DATA) return;
  renderList(DATA.artists,     'artist-list',     'artist-count',     q.artists||'',     'artist',     a=>showArtist(a));
  renderList(DATA.genres,      'genre-list',      'genre-count',      q.genres||'',      'genre',      e=>showEntity('genre',e));
  renderList(DATA.labels,      'label-list',      'label-count',      q.labels||'',      'label',      e=>showEntity('label',e));
  renderList(DATA.concerts,    'concert-list',    'concert-count',    q.concerts||'',    'concert',    e=>showEntity('concert',e));
  renderList(DATA.instruments, 'instrument-list', 'instrument-count', q.instruments||'', 'instrument', e=>showEntity('instrument',e));
  renderCuriosityList(DATA.gen_curiosities, q.curiosities||'');
}

['artists','genres','labels','concerts','instruments'].forEach(type => {
  document.getElementById('search-'+type).addEventListener('input', e => {
    const q = e.target.value.trim();
    const m = {
      artists:    ['artist-list',    'artist-count',    'artist',    a=>showArtist(a)],
      genres:     ['genre-list',     'genre-count',     'genre',     x=>showEntity('genre',x)],
      labels:     ['label-list',     'label-count',     'label',     x=>showEntity('label',x)],
      concerts:   ['concert-list',   'concert-count',   'concert',   x=>showEntity('concert',x)],
      instruments:['instrument-list','instrument-count','instrument',x=>showEntity('instrument',x)],
    };
    renderList(DATA[type], m[type][0], m[type][1], q, m[type][2], m[type][3]);
  });
});
document.getElementById('search-curiosities').addEventListener('input', e =>
  renderCuriosityList(DATA.gen_curiosities, e.target.value.trim()));

// ── HTML builders ─────────────────────────────────────────────────────────────
function srcHtml(sf) {
  if (!sf) return '';
  const p = sf.indexOf('|');
  if (p > -1) {
    const nm = sf.slice(0,p).trim(), url = sf.slice(p+1).trim();
    if (url.startsWith('http'))
      return `<div class="card-source"><a href="${url}" target="_blank">📺 ${nm||'Fuente'}</a></div>`;
  }
  return `<div class="card-source"><span>📂 ${sf}</span></div>`;
}

function makeCard(etype, ename, section, item, color) {
  const title     = item.name || item.title || '';
  const facts     = item.facts ||
    (item.description ? [{description:item.description, source_file:item.source_file||''}] : []);
  const firstDesc = facts[0]?.description || '';
  const editSid   = store({action:'open-edit',    type:etype, name:ename, section, key:title, desc:firstDesc});
  const delSid    = store({action:'delete-entry', type:etype, name:ename, section, key:title, is_list:false});
  const body      = facts.map(f=>`<div class="card-body">${f.description}</div>${srcHtml(f.source_file)}`).join('');
  return `<div class="card" style="border-left-color:${color}">
    <div class="card-header">
      <span class="card-title">${title}</span>
      <div class="card-actions">
        <button class="btn-edit" data-sid="${editSid}">✏</button>
        <button class="btn-del"  data-sid="${delSid}">🗑</button>
      </div>
    </div>
    <div class="card-content">${body}</div>
    <div class="edit-form">
      <input  class="edit-title" value="" placeholder="Título">
      <textarea class="edit-desc" rows="5" placeholder="Descripción"></textarea>
      <div class="edit-btns">
        <button class="btn-save" data-sid="${editSid}">Guardar</button>
        <button class="btn-cancel">Cancelar</button>
      </div>
    </div>
  </div>`;
}

function makeTagSection(etype, ename, skey, items, color) {
  const secDelSid = store({action:'delete-section', type:etype, name:ename, section:skey});
  const tags = items.map(item => {
    const nm      = item.name ?? item;
    const linked  = item.id != null;
    const delSid  = store({action:'delete-entry',  type:etype, name:ename, section:skey, key:nm, is_list:true});
    const goSid   = linked ? store({action:'go-artist', id:item.id}) : null;
    return `<span class="tag" style="color:${color};border-color:${color};background:${color}22">
      <span class="tag-name ${linked?'linked':''}" ${goSid?`data-sid="${goSid}"`:''}>
        ${nm}
      </span>
      <button class="tag-del" data-sid="${delSid}">✕</button>
    </span>`;
  }).join('');
  return `<div class="section">
    <div class="section-header">
      <span class="section-title" style="color:${color}">${SEC_LABELS[skey]||skey} (${items.length})</span>
      <button class="btn-del-section" data-sid="${secDelSid}">✕ Sección</button>
    </div>
    <div class="tag-list">${tags}</div>
  </div>`;
}

function makeEntrySection(etype, ename, skey, items, color) {
  const secDelSid = store({action:'delete-section', type:etype, name:ename, section:skey});
  return `<div class="section">
    <div class="section-header">
      <span class="section-title" style="color:${color}">${SEC_LABELS[skey]||skey} (${items.length})</span>
      <button class="btn-del-section" data-sid="${secDelSid}">✕ Sección</button>
    </div>
    ${items.map(item => makeCard(etype, ename, skey, item, color)).join('')}
  </div>`;
}

// ── Show artist ───────────────────────────────────────────────────────────────
function showArtist(artist) {
  activeEntity = {type:'artist', name:artist.name};
  const delSid = store({action:'delete-entity', type:'artist', name:artist.name});

  let html = `<div id="entity-detail">
    <h1>${artist.name}</h1>
    <div class="entity-toolbar">
      <div class="entity-badge" style="background:#e9456022;color:#e94560;border:1px solid #e94560">Artista</div>
      <button class="btn-del-entity" data-sid="${delSid}">🗑 Eliminar artista</button>
    </div>`;

  if (artist.member_of?.length) {
    const links = artist.member_of.map(b => {
      const sid = store({action:'go-artist', id:b.id});
      return `<a data-sid="${sid}">${b.name}</a>`;
    }).join(', ');
    html += `<div class="member-of-line">Miembro de: ${links}</div>`;
  }

  for (const key of ['members','member_of','genres','labels','concerts','instruments']) {
    if (artist[key]?.length)
      html += makeTagSection('artist', artist.name, key, artist[key], SEC_COLORS[key]);
  }
  for (const key of ['albums','songs','curiosities']) {
    if (artist[key]?.length)
      html += makeEntrySection('artist', artist.name, key, artist[key], SEC_COLORS[key]);
  }
  html += '</div>';
  document.getElementById('content').innerHTML = html;
}

// ── Show named entity ─────────────────────────────────────────────────────────
function showEntity(etype, entity) {
  activeEntity = {type:etype, name:entity.name};
  const color  = E_COLORS[etype] || '#888';
  const delSid = store({action:'delete-entity', type:etype, name:entity.name});

  let html = `<div id="entity-detail">
    <h1>${entity.name}</h1>
    <div class="entity-toolbar">
      <div class="entity-badge" style="background:${color}22;color:${color};border:1px solid ${color}">${E_LABEL[etype]||etype}</div>
      <button class="btn-del-entity" data-sid="${delSid}">🗑 Eliminar</button>
    </div>`;

  if (entity.curiosities?.length) {
    const items = entity.curiosities.map(c => ({
      name: c.title,
      facts: [{description:c.description, source_file:c.source_file}],
    }));
    html += makeEntrySection(etype, entity.name, 'curiosities', items, color);
  } else {
    html += `<p style="color:#484f58;font-size:0.85rem">Sin datos detallados.</p>`;
  }
  html += '</div>';
  document.getElementById('content').innerHTML = html;
}

// ── Show general curiosity ────────────────────────────────────────────────────
function showGenCuriosity(c) {
  const color = SEC_COLORS.curiosities;
  document.getElementById('content').innerHTML = `<div id="entity-detail">
    <h1>${c.title}</h1>
    <div class="entity-badge" style="background:${color}22;color:${color};border:1px solid ${color};margin-bottom:16px;display:inline-block">Curiosidad</div>
    <div class="card" style="border-left-color:${color}">
      <div class="card-body">${c.description}</div>${srcHtml(c.source_file)}
    </div>
  </div>`;
}

// ── Animate remove ────────────────────────────────────────────────────────────
function fadeOut(el) {
  el.classList.add('removing');
  setTimeout(() => el.remove(), 230);
}

// ── Delete operations ─────────────────────────────────────────────────────────
async function doDeleteEntity(etype, name, listItemEl) {
  const noun = etype === 'artist' ? 'artista' : E_LABEL[etype]?.toLowerCase() || etype;
  if (!confirm(`¿Eliminar ${noun} "${name}"?\nSe borrará el archivo .md permanentemente.`)) return;
  const r = await api('/api/delete/entity', {type:etype, name});
  if (!r.ok) { toast('Error al eliminar', 'err'); return; }
  const key = etype === 'artist' ? 'artists' : etype + 's';
  if (DATA[key]) DATA[key] = DATA[key].filter(e => e.name !== name);
  if (listItemEl) fadeOut(listItemEl);
  if (activeEntity?.type === etype && activeEntity?.name === name) {
    document.getElementById('content').innerHTML =
      '<div id="placeholder">← Elemento eliminado. Selecciona otro.</div>';
    activeEntity = null;
  }
  toast(`"${name}" eliminado`);
}

async function doDeleteSection(etype, name, section, sectionEl) {
  const label = SEC_LABELS[section] || section;
  if (!confirm(`¿Eliminar toda la sección "${label}" de "${name}"?`)) return;
  const r = await api('/api/delete/section', {type:etype, name, section});
  if (!r.ok) { toast('Error', 'err'); return; }
  if (sectionEl) fadeOut(sectionEl);
  toast(`Sección "${label}" eliminada`);
}

async function doDeleteEntry(etype, name, section, key, is_list, el) {
  const r = await api('/api/delete/entry', {type:etype, name, section, key, is_list});
  if (!r.ok) { toast('Error', 'err'); return; }
  fadeOut(el);
}

// ── Edit operations ───────────────────────────────────────────────────────────
function openEdit(card, key, desc) {
  card.querySelector('.edit-title').value = key;
  card.querySelector('.edit-desc').value  = desc;
  card.querySelector('.edit-form').classList.add('open');
  card.querySelector('.card-content').style.display = 'none';
  // store original key on save button for retrieval
  card.querySelector('.btn-save').dataset.origKey = key;
  card.querySelector('.edit-desc').focus();
}

function closeEdit(card) {
  card.querySelector('.edit-form').classList.remove('open');
  card.querySelector('.card-content').style.display = '';
}

async function saveEdit(card, etype, ename, section, origKey) {
  const newTitle = card.querySelector('.edit-title').value.trim();
  const newDesc  = card.querySelector('.edit-desc').value.trim();
  if (!newTitle) return;
  const r = await api('/api/edit/entry', {type:etype, name:ename, section, key:origKey, new_title:newTitle, new_desc:newDesc});
  if (!r.ok) { toast('Error al guardar', 'err'); return; }
  card.querySelector('.card-title').textContent = newTitle;
  const bodyEl = card.querySelector('.card-body');
  if (bodyEl) bodyEl.textContent = newDesc;
  closeEdit(card);
  // update store entries so future edits use new key
  _S.forEach(v => {
    if (v.key === origKey && v.name === ename && v.section === section) {
      v.key = newTitle; if (v.desc !== undefined) v.desc = newDesc;
    }
  });
  toast('Guardado ✓');
}

// ── Rebuild DB ────────────────────────────────────────────────────────────────
async function rebuildDB() {
  const btn = document.getElementById('btn-rebuild');
  btn.textContent = '⏳…'; btn.classList.add('spinning');
  toast('Reconstruyendo BD…');
  const r = await api('/api/rebuild', {});
  btn.textContent = '⚙ Rebuild DB'; btn.classList.remove('spinning');
  if (r.ok) {
    toast('✓ BD reconstruida', 'ok', r.out);
    await loadData();
  } else {
    toast('✗ Error en rebuild', 'err', r.err || r.out);
  }
}
document.getElementById('btn-rebuild').addEventListener('click', rebuildDB);

// ── Unified event delegation on #content ─────────────────────────────────────
document.getElementById('content').addEventListener('click', e => {
  // Cancel has no data-sid — handle first
  if (e.target.classList.contains('btn-cancel')) {
    closeEdit(e.target.closest('.card')); return;
  }

  const btn = e.target.closest('[data-sid]');
  if (!btn) return;
  e.stopPropagation();
  const d = get(btn.dataset.sid);
  if (!d) return;

  // btn-save shares data-sid with open-edit, so check class before action
  if (btn.classList.contains('btn-save')) {
    saveEdit(btn.closest('.card'), d.type, d.name, d.section, btn.dataset.origKey || d.key);
    return;
  }

  if (d.action === 'go-artist') {
    const a = byId[d.id]; if (a) showArtist(a);
  } else if (d.action === 'delete-entity') {
    doDeleteEntity(d.type, d.name, null);
  } else if (d.action === 'delete-section') {
    doDeleteSection(d.type, d.name, d.section, btn.closest('.section'));
  } else if (d.action === 'delete-entry') {
    const parent = d.is_list ? btn.closest('.tag') : btn.closest('.card');
    doDeleteEntry(d.type, d.name, d.section, d.key, d.is_list, parent);
  } else if (d.action === 'open-edit') {
    openEdit(btn.closest('.card'), d.key, d.desc);
  }
});

// Sidebar list-del via delegation
document.getElementById('sidebar').addEventListener('click', e => {
  const btn = e.target.closest('.list-del[data-sid]');
  if (!btn) return;
  e.stopPropagation();
  const d = get(btn.dataset.sid);
  if (d) doDeleteEntity(d.type, d.name, btn.closest('.list-item'));
});

// Escape closes open edit forms
document.addEventListener('keydown', e => {
  if (e.key === 'Escape')
    document.querySelectorAll('.edit-form.open').forEach(f => closeEdit(f.closest('.card')));
});

// ── Boot ──────────────────────────────────────────────────────────────────────
loadData();
"""

def build_html():
    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Music Editor</title>
<style>{CSS}</style>
</head>
<body>
{_BODY}
<script>
{_JS}
</script>
</body>
</html>"""

HTML = build_html()
