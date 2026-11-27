(() => {
  'use strict';

  const appState = {
    token: localStorage.getItem('mpmb_auth_token') || '',
    sheet: null,
    sheets: [],
    templates: [],
    characters: [],
    git: null,
    page: 0,
    zoom: 1.0,
    pageWidgets: [],
    pageSize: [612, 792],
    pageLoadSeq: 0,
    lastServerInstanceId: null,
    retiredServerInstanceIds: new Set(),
    lastStateSeq: 0,
    sessionFetchSeq: 0,
    appliedSessionFetchSeq: 0,
    libraryFetchSeq: 0,
    appliedLibraryFetchSeq: 0,
    selectedField: null,
    activeInteraction: null,
    retiredInteractionKeys: new Set(),
    inFlightInteractionKey: null,
    suppressNextBlurSubmit: false,
    stepChain: Promise.resolve(),
    ws: null,
    wsConnected: false,
    wsHasConnectedOnce: false,
    offline: !navigator.onLine,
    busy: false,
    modalValues: {},
    modalPopupOptions: {},
  };

  // Capture optional ?token= query parameter once and strip from URL bar.
  const params = new URLSearchParams(location.search);
  if (params.has('token')) {
    appState.token = params.get('token') || '';
    localStorage.setItem('mpmb_auth_token', appState.token);
    params.delete('token');
    const clean = location.pathname + (params.toString() ? '?' + params.toString() : '');
    history.replaceState(null, '', clean);
  }

  const $ = (id) => document.getElementById(id);

  // Theme initialization
  const savedTheme = localStorage.getItem('mpmb_theme') || 'dark';
  applyTheme(savedTheme);
  function applyTheme(mode) {
    document.documentElement.setAttribute('data-theme', mode);
    localStorage.setItem('mpmb_theme', mode);
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.content = mode === 'light' ? '#f4f1ea' : '#111318';
    const btn = $('btn-theme');
    if (btn) btn.textContent = mode === 'light' ? '☾' : '☀';
  }
  $('btn-theme').addEventListener('click', () => {
    const cur = document.documentElement.getAttribute('data-theme');
    applyTheme(cur === 'light' ? 'dark' : 'light');
  });

  // Service Worker registration for offline PWA shell + cached reads
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/sw.js').catch(() => {});
  }

  function showBanner(msg, kind = 'ok', autoClearMs = 4500) {
    const el = $('banner');
    if (!msg) {
      el.className = 'banner hidden';
      el.textContent = '';
      return;
    }
    el.className = `banner ${kind}`;
    el.textContent = msg;
    if (autoClearMs > 0) {
      clearTimeout(showBanner._t);
      showBanner._t = setTimeout(() => {
        if (el.textContent === msg) el.className = 'banner hidden';
      }, autoClearMs);
    }
  }

  function updateConnDot() {
    const dot = $('conn-dot');
    if (appState.offline) {
      dot.className = 'brand-dot err';
      dot.title = 'Offline (cached view)';
    } else if (appState.wsConnected) {
      dot.className = 'brand-dot ok';
      dot.title = 'Connected (live)';
    } else {
      dot.className = 'brand-dot warn';
      dot.title = 'Reconnecting…';
    }
  }

  window.addEventListener('online', () => {
    appState.offline = false;
    updateConnDot();
    showBanner('Back online — refreshing sheet', 'ok', 2500);
    connectWs();
    refreshAll();
  });
  window.addEventListener('offline', () => {
    appState.offline = true;
    appState.wsConnected = false;
    updateConnDot();
    showBanner('Offline — showing cached sheet data', 'warn', 0);
  });

  async function api(path, opts = {}) {
    const headers = Object.assign({}, opts.headers || {});
    if (appState.token) headers['Authorization'] = `Bearer ${appState.token}`;
    if (opts.json !== undefined) {
      headers['Content-Type'] = 'application/json';
      opts.body = JSON.stringify(opts.json);
      delete opts.json;
    }
    const res = await fetch(path, Object.assign({}, opts, { headers }));
    if (res.status === 401) {
      $('auth-modal').classList.remove('hidden');
      throw new Error('Authentication required');
    }
    const ct = res.headers.get('content-type') || '';
    const data = ct.includes('application/json') ? await res.json() : await res.text();
    if (!res.ok) {
      const msg = typeof data === 'object' && data && data.error ? data.error : String(data || res.statusText);
      const err = new Error(msg);
      err.status = res.status;
      err.data = data;
      throw err;
    }
    return data;
  }

  function clearSwApiCache() {
    if ('serviceWorker' in navigator && navigator.serviceWorker.controller) {
      navigator.serviceWorker.controller.postMessage({ type: 'CLEAR_API_CACHE' });
    }
  }

  $('auth-token-save').addEventListener('click', async () => {
    appState.token = $('auth-token-input').value.trim();
    localStorage.setItem('mpmb_auth_token', appState.token);
    clearSwApiCache();
    $('auth-modal').classList.add('hidden');
    if (appState.ws) {
      try { appState.ws.close(); } catch (_) {}
      appState.ws = null;
    }
    connectWs();
    await refreshAll();
  });

  // WebSocket live updates
  function connectWs() {
    if (appState.ws && (appState.ws.readyState === WebSocket.OPEN || appState.ws.readyState === WebSocket.CONNECTING)) {
      return;
    }
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const qs = appState.token ? `?token=${encodeURIComponent(appState.token)}` : '';
    const ws = new WebSocket(`${proto}//${location.host}/ws${qs}`);
    appState.ws = ws;
    ws.onopen = () => {
      if (appState.ws !== ws) return;
      const isReconnect = appState.wsHasConnectedOnce;
      appState.wsHasConnectedOnce = true;
      appState.wsConnected = true;
      appState.offline = false;
      updateConnDot();
      if (isReconnect) {
        refreshSession();
      }
    };
    ws.onclose = () => {
      if (appState.ws !== ws) return;
      appState.wsConnected = false;
      updateConnDot();
      setTimeout(connectWs, 2500);
    };
    ws.onerror = () => {
      if (appState.ws !== ws) return;
      appState.wsConnected = false;
      updateConnDot();
    };
    ws.onmessage = (ev) => {
      if (appState.ws !== ws) return;
      try {
        const msg = JSON.parse(ev.data);
        if (msg.type === 'state_updated' && msg.state) {
          applySessionState(msg.state);
        } else if (msg.type === 'resync_required') {
          refreshSession();
        } else if (msg.type === 'interaction_requested' && msg.interaction) {
          const inter = msg.serverInstanceId && !msg.interaction.serverInstanceId
            ? Object.assign({ serverInstanceId: msg.serverInstanceId }, msg.interaction)
            : msg.interaction;
          openAcrobatInteraction(inter);
        } else if (msg.type === 'interaction_cleared') {
          if (msg.serverInstanceId && appState.retiredServerInstanceIds.has(msg.serverInstanceId)) {
            return;
          }
          closeAcrobatModal(msg.id || null, msg.serverInstanceId || null);
        } else if (msg.type === 'git_status' && msg.git) {
          appState.git = msg.git;
          renderGit();
        } else if (msg.type === 'launch_url' && msg.url) {
          showBanner(`MPMB link: ${msg.url}`, 'ok', 8000);
          window.open(msg.url, '_blank', 'noopener');
        } else if (msg.type === 'error' && msg.message) {
          showBanner(msg.message, 'err', 6000);
        }
      } catch (_) {}
    };
  }

  // Tab Navigation
  document.querySelectorAll('.tab-btn').forEach((btn) => {
    btn.addEventListener('click', () => switchTab(btn.dataset.tab));
  });
  $('btn-go-library').addEventListener('click', () => switchTab('library'));
  $('btn-empty-new-char').addEventListener('click', () => openNewCharModal());
  $('btn-new-char').addEventListener('click', () => openNewCharModal());

  function switchTab(name) {
    document.querySelectorAll('.tab-btn').forEach((b) => b.classList.toggle('active', b.dataset.tab === name));
    document.querySelectorAll('.tab-panel').forEach((p) => p.classList.toggle('active', p.id === `tab-${name}`));
    if (name === 'sheet' && appState.sheet) loadPdfPage();
    if (name === 'library') refreshLibrary();
    if (name === 'tools' && appState.sheet) renderFieldList();
  }

  async function refreshAll() {
    await Promise.all([refreshLibrary(), refreshSession()]);
  }

  async function refreshLibrary() {
    const fetchSeq = ++appState.libraryFetchSeq;
    try {
      const data = await api('/api/sheets');
      if (fetchSeq < appState.appliedLibraryFetchSeq) return;
      appState.appliedLibraryFetchSeq = fetchSeq;
      appState.sheets = data.sheets || [];
      appState.templates = Array.isArray(data.templates)
        ? data.templates
        : appState.sheets.filter((s) => isTemplateSheet(s));
      appState.characters = Array.isArray(data.characters)
        ? data.characters
        : appState.sheets.filter((s) => !isTemplateSheet(s));
      appState.git = data.git || null;
      renderSheets();
      renderGit();
      if (appState.git && appState.git.enabled) {
        const hist = await api('/api/git/history').catch(() => ({ commits: [] }));
        if (fetchSeq < appState.appliedLibraryFetchSeq) return;
        renderHistory(hist.commits || []);
      }
    } catch (err) {
      if (err.message !== 'Authentication required') showBanner(err.message, 'err');
    }
  }

  async function refreshSession() {
    const fetchSeq = ++appState.sessionFetchSeq;
    try {
      const state = await api('/api/session/state');
      if (!state || fetchSeq < appState.appliedSessionFetchSeq) return;
      if (applySessionState(state)) {
        appState.appliedSessionFetchSeq = fetchSeq;
      }
    } catch (err) {
      if (err.message !== 'Authentication required') showBanner(err.message, 'err');
    }
  }

  function applySessionState(state) {
    if (!state) return false;
    if (typeof state.serverInstanceId === 'string' && state.serverInstanceId) {
      if (appState.retiredServerInstanceIds.has(state.serverInstanceId)) {
        return false;
      }
      if (appState.lastServerInstanceId && appState.lastServerInstanceId !== state.serverInstanceId) {
        appState.retiredServerInstanceIds.add(appState.lastServerInstanceId);
        appState.lastStateSeq = 0;
      }
      appState.lastServerInstanceId = state.serverInstanceId;
    }
    if (state.busy && !state.path) {
      if (state.git) {
        appState.git = state.git;
        renderGit();
      }
      if (state.activeInteraction) openAcrobatInteraction(state.activeInteraction);
      return true;
    }
    if (!state.open) {
      if (typeof state.stateSeq === 'number' && state.stateSeq < appState.lastStateSeq) {
        return false;
      }
      if (typeof state.stateSeq === 'number') {
        appState.lastStateSeq = state.stateSeq;
      }
      closeFieldModal();
      appState.sheet = null;
      if (state.git) appState.git = state.git;
      renderTopbar();
      renderPlay();
      renderGit();
      return true;
    }
    const prevRev = appState.sheet ? appState.sheet.revision : -1;
    const prevPath = appState.sheet ? appState.sheet.path : null;
    const prevSessionId = appState.sheet ? (appState.sheet.sessionId || '') : '';
    const nextSessionId = state.sessionId || '';
    const prevLastStateSeq = appState.lastStateSeq;
    const isDuplicateStateSeq =
      typeof state.stateSeq === 'number' && state.stateSeq === prevLastStateSeq;
    if (typeof state.stateSeq === 'number' && state.stateSeq < prevLastStateSeq) {
      return false;
    }
    if (
      typeof state.stateSeq !== 'number' &&
      prevPath === state.path &&
      prevSessionId === nextSessionId &&
      typeof state.revision === 'number' &&
      typeof prevRev === 'number' &&
      state.revision < prevRev
    ) {
      return false;
    }
    if (typeof state.stateSeq === 'number') {
      appState.lastStateSeq = state.stateSeq;
    }
    const sessionChanged = prevPath !== state.path || prevSessionId !== nextSessionId;
    if (sessionChanged) {
      closeFieldModal();
    }
    appState.sheet = state;
    if (state.git) appState.git = state.git;
    if (state.pageCount && appState.page >= state.pageCount) {
      appState.page = Math.max(0, state.pageCount - 1);
    }
    renderTopbar();
    renderPlay();
    renderTools();
    renderGit();
    const forceBtn = $('btn-force-save');
    if (forceBtn) {
      forceBtn.classList.toggle('hidden', !state.saveConflict);
    }
    if (state.saveConflict) {
      showBanner('File changed externally on disk — pull latest or tap Force Save in the Git tab', 'warn', 0);
    }
    if (state.activeInteraction) {
      openAcrobatInteraction(state.activeInteraction);
    } else if (appState.activeInteraction) {
      // Never let a duplicate or earlier-sequenced state reply dismiss an Acrobat
      // prompt that was opened at or after this state snapshot.
      const interSeq =
        typeof appState.activeInteraction.stateSeq === 'number' &&
        appState.activeInteraction.stateSeq > 0
          ? appState.activeInteraction.stateSeq
          : null;
      const stateNewerThanInteraction =
        !isDuplicateStateSeq &&
        (interSeq === null ||
          (typeof state.stateSeq === 'number' && state.stateSeq > interSeq));
      if (stateNewerThanInteraction) {
        closeAcrobatModal();
      }
    }
    const sheetTabActive = $('tab-sheet').classList.contains('active');
    if (sheetTabActive && (prevRev !== state.revision || sessionChanged)) {
      loadPdfPage();
    }
    return true;
  }

  function renderTopbar() {
    const s = appState.sheet;
    const syncBtn = $('btn-top-sync');
    if (!s || !s.open) {
      $('top-char-name').textContent = 'MPMB Sheet';
      $('top-char-sub').textContent = 'No sheet loaded';
      syncBtn.textContent = 'Sync';
      syncBtn.classList.remove('dirty');
      return;
    }
    const ch = s.character || {};
    $('top-char-name').textContent = ch.name || s.path;
    const subParts = [];
    if (ch.classAndLevels) subParts.push(ch.classAndLevels);
    else if (ch.level) subParts.push(`Level ${ch.level}`);
    subParts.push(`Rev ${s.revision}`);
    $('top-char-sub').textContent = subParts.join(' • ');

    const gitDirty = appState.git && appState.git.enabled && (appState.git.dirty || appState.git.ahead > 0);
    if (s.dirtySinceSave || gitDirty) {
      syncBtn.textContent = appState.git && appState.git.enabled ? 'Sync ●' : 'Save ●';
      syncBtn.classList.add('dirty');
    } else {
      syncBtn.textContent = appState.git && appState.git.enabled ? 'Synced ✓' : 'Saved ✓';
      syncBtn.classList.remove('dirty');
    }
  }

  // --- PLAY / TABLE VIEW ---
  function renderPlay() {
    const s = appState.sheet;
    if (!s || !s.open) {
      $('play-empty').classList.remove('hidden');
      $('play-content').classList.add('hidden');
      return;
    }
    $('play-empty').classList.add('hidden');
    $('play-content').classList.remove('hidden');

    const v = s.vitals || {};
    $('v-ac').textContent = v.ac || '—';
    $('v-init').textContent = v.init || '—';
    $('v-speed').textContent = v.speed || '—';
    $('v-prof').textContent = v.proficiency || '—';

    const cur = parseInt(v.hpCurrent, 10);
    const max = parseInt(v.hpMax, 10);
    $('v-hp-cur').textContent = v.hpCurrent || '—';
    $('v-hp-max').textContent = v.hpMax || '—';
    const pct = (!isNaN(cur) && !isNaN(max) && max > 0) ? Math.max(0, Math.min(100, (cur / max) * 100)) : 0;
    const fill = $('hp-bar-fill');
    fill.style.width = `${pct}%`;
    fill.style.background = pct <= 25 ? 'var(--danger)' : pct <= 50 ? 'var(--warn)' : 'var(--success)';

    const tempVal = (v.hpTemp || '').trim();
    if (tempVal && tempVal !== '0') {
      $('v-hp-temp').textContent = tempVal;
      $('v-hp-temp-wrap').classList.remove('hidden');
    } else {
      $('v-hp-temp-wrap').classList.add('hidden');
    }

    // Abilities
    const abGrid = $('abilities-grid');
    abGrid.innerHTML = '';
    (s.abilities || []).forEach((ab) => {
      const div = document.createElement('button');
      div.type = 'button';
      div.className = 'ability-card';
      div.innerHTML = `
        <div class="vital-label">${esc(ab.label)}</div>
        <div class="ability-mod">${esc(ab.modifier || '—')}</div>
        <div class="ability-score">${esc(ab.score || '—')}</div>
        <div class="ability-save">Save ${ab.saveProf ? '● ' : ''}${esc(ab.saveMod || '—')}</div>
      `;
      div.addEventListener('click', () => openFieldEditorByName(ab.scoreField));
      abGrid.appendChild(div);
    });

    // Attacks
    const atkList = $('attacks-list');
    atkList.innerHTML = '';
    const attacks = s.attacks || [];
    $('attacks-card').classList.toggle('hidden', attacks.length === 0);
    attacks.forEach((a) => {
      const row = document.createElement('div');
      row.className = 'row-card';
      row.innerHTML = `
        <div class="row-main">
          <div class="row-title">${esc(a.name)}</div>
          <div class="row-sub">${esc([a.damage, a.damageType, a.range, a.description].filter(Boolean).join(' • '))}</div>
        </div>
        <span class="status-badge ok">${esc(a.toHit || '—')}</span>
      `;
      atkList.appendChild(row);
    });

    // Spell Slots
    const slots = s.spellSlots || [];
    const slotsCard = $('slots-card');
    const slotsList = $('slots-list');
    slotsList.innerHTML = '';
    slotsCard.classList.toggle('hidden', slots.length === 0);
    slots.forEach((sl) => {
      const row = document.createElement('div');
      row.className = 'row-card';
      const left = document.createElement('div');
      left.className = 'row-main';
      left.innerHTML = `<div class="row-title">${esc(sl.label)}</div><div class="row-sub">${sl.used} / ${sl.total} used</div>`;
      const pips = document.createElement('div');
      pips.className = 'slot-pips';
      (sl.boxes || []).forEach((box, idx) => {
        const pip = document.createElement('button');
        pip.type = 'button';
        pip.className = `slot-pip ${box.checked ? 'used' : ''}`;
        pip.textContent = String(idx + 1);
        pip.title = box.field;
        pip.addEventListener('click', () => activateField(box.field, 0));
        pips.appendChild(pip);
      });
      row.appendChild(left);
      row.appendChild(pips);
      slotsList.appendChild(row);
    });

    // Limited Features / Resources
    const resources = s.resources || [];
    const resCard = $('resources-card');
    const resList = $('resources-list');
    resList.innerHTML = '';
    resCard.classList.toggle('hidden', resources.length === 0);
    resources.forEach((r) => {
      const row = document.createElement('div');
      row.className = 'row-card';
      const usedNum = parseInt(r.used || '0', 10) || 0;
      const maxLabel = r.max ? `/ ${r.max}` : '';
      row.innerHTML = `
        <div class="row-main">
          <div class="row-title">${esc(r.name)}</div>
          <div class="row-sub">${esc(r.recovery || 'Resource')} • Used: ${esc(r.used || '0')} ${esc(maxLabel)}</div>
        </div>
      `;
      const ctrls = document.createElement('div');
      ctrls.className = 'seg-group';
      const minus = document.createElement('button');
      minus.type = 'button';
      minus.className = 'btn small';
      minus.textContent = '−';
      minus.addEventListener('click', () => {
        const target = currentSessionRef();
        if (!target) return;
        enqueueStep(target, (ref) => {
          const latest = (appState.sheet?.resources || []).find((x) => x.usedField === r.usedField);
          const curUsed = parseInt((latest ? latest.used : r.used) || '0', 10) || 0;
          return editField(r.usedField, String(Math.max(0, curUsed - 1)), 'user', ref);
        });
      });
      const plus = document.createElement('button');
      plus.type = 'button';
      plus.className = 'btn small accent';
      plus.textContent = '+';
      plus.addEventListener('click', () => {
        const target = currentSessionRef();
        if (!target) return;
        enqueueStep(target, (ref) => {
          const latest = (appState.sheet?.resources || []).find((x) => x.usedField === r.usedField);
          const curUsed = parseInt((latest ? latest.used : r.used) || '0', 10) || 0;
          return editField(r.usedField, String(curUsed + 1), 'user', ref);
        });
      });
      ctrls.appendChild(minus);
      ctrls.appendChild(plus);
      row.appendChild(ctrls);
      resList.appendChild(row);
    });

    // Skills
    const skList = $('skills-list');
    skList.innerHTML = '';
    (s.skills || []).forEach((sk) => {
      const item = document.createElement('div');
      item.className = 'skill-row';
      const mark = sk.expertise ? '◆ ' : sk.proficient ? '● ' : '';
      item.innerHTML = `<span>${mark}${esc(sk.label)}</span><span class="skill-mod">${esc(sk.mod || '—')}</span>`;
      skList.appendChild(item);
    });

    // Notes
    const notesList = $('notes-list');
    notesList.innerHTML = '';
    (s.notes || []).forEach((n) => {
      if (!n.value) return;
      const block = document.createElement('div');
      block.className = 'note-item';
      block.innerHTML = `<div class="vital-label">${esc(n.label)}</div><pre>${esc(n.value)}</pre>`;
      notesList.appendChild(block);
    });
  }

  function enqueueStep(target, fn) {
    if (!target) return appState.stepChain;
    appState.stepChain = appState.stepChain
      .then(() => {
        if (!isCurrentSession(target)) return;
        return fn(target);
      })
      .catch(() => {});
    return appState.stepChain;
  }

  // HP Quick Steppers & Quick Actions
  document.querySelectorAll('[data-hp-delta]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const delta = parseInt(btn.dataset.hpDelta, 10);
      const target = currentSessionRef();
      if (!target) return;
      enqueueStep(target, (ref) => {
        if (!appState.sheet || !appState.sheet.open) return;
        const v = appState.sheet.vitals || {};
        const cur = parseInt(v.hpCurrent, 10);
        const max = parseInt(v.hpMax, 10);
        const base = isNaN(cur) ? (isNaN(max) ? 0 : max) : cur;
        const next = Math.max(0, base + delta);
        return editField('HP Current', String(next), 'user', ref);
      });
    });
  });
  $('btn-hp-full').addEventListener('click', () => {
    const target = currentSessionRef();
    if (!target) return;
    enqueueStep(target, (ref) => {
      const max = appState.sheet?.vitals?.hpMax;
      if (max) return editField('HP Current', String(max), 'user', ref);
    });
  });
  $('btn-hp-edit').addEventListener('click', () => openFieldEditorByName('HP Current'));
  $('btn-hp-temp').addEventListener('click', () => openFieldEditorByName('HP Temp'));
  $('btn-classes').addEventListener('click', () => invokeMenu('ClassesButton'));
  $('btn-short-rest').addEventListener('click', () => runCommand('short_rest'));
  $('btn-long-rest').addEventListener('click', () => runCommand('long_rest'));
  $('btn-spell-sheet').addEventListener('click', () => runCommand('spell_sheet'));
  $('btn-top-sync').addEventListener('click', async () => {
    if (appState.git && appState.git.enabled) {
      await doGitSync('');
    } else {
      await doSaveNow();
    }
  });

  // --- PDF SHEET VIEW ---
  $('btn-prev-page').addEventListener('click', () => {
    if (appState.page > 0) {
      appState.page--;
      loadPdfPage();
    }
  });
  $('btn-next-page').addEventListener('click', () => {
    const maxPages = appState.sheet?.pageCount || 1;
    if (appState.page + 1 < maxPages) {
      appState.page++;
      loadPdfPage();
    }
  });
  $('btn-zoom-out').addEventListener('click', () => {
    appState.zoom = Math.max(0.75, +(appState.zoom - 0.25).toFixed(2));
    applyPdfZoom();
  });
  $('btn-zoom-in').addEventListener('click', () => {
    appState.zoom = Math.min(2.5, +(appState.zoom + 0.25).toFixed(2));
    applyPdfZoom();
  });

  function applyPdfZoom() {
    $('zoom-label').textContent = `${Math.round(appState.zoom * 100)}%`;
    $('pdf-stage').style.width = `${Math.round(appState.zoom * 100)}%`;
  }

  async function loadPdfPage() {
    if (!appState.sheet || !appState.sheet.open) return;
    const seq = ++appState.pageLoadSeq;
    appState.pageWidgets = [];
    renderPdfOverlay();
    const page = appState.page;
    const rev = appState.sheet.revision;
    const sheetPath = appState.sheet.path || '';
    const maxPages = appState.sheet.pageCount || 1;
    $('page-label').textContent = `${page + 1} / ${maxPages}`;
    $('btn-prev-page').disabled = page <= 0;
    $('btn-next-page').disabled = page + 1 >= maxPages;
    applyPdfZoom();

    const width = Math.min(1800, Math.max(900, Math.round(window.innerWidth * (window.devicePixelRatio || 2))));
    const tokenQs = appState.token ? `&token=${encodeURIComponent(appState.token)}` : '';
    const sessionId = appState.sheet.sessionId || '';
    const sessionQs = sessionId ? `&session=${encodeURIComponent(sessionId)}` : '';
    const sheetQs = `&sheet=${encodeURIComponent(sheetPath)}${sessionQs}&rev=${encodeURIComponent(String(rev))}`;
    const imgUrl = `/api/session/page/${page}/image?w=${width}${sheetQs}${tokenQs}`;
    $('pdf-img').src = imgUrl;

    try {
      const wdata = await api(`/api/session/page/${page}/widgets?sheet=${encodeURIComponent(sheetPath)}${sessionQs}&rev=${encodeURIComponent(String(rev))}`);
      if (seq !== appState.pageLoadSeq) return;
      appState.pageWidgets = wdata.widgets || [];
      appState.pageSize = wdata.pageSize || [612, 792];
      renderPdfOverlay();
    } catch (_) {}
  }

  function renderPdfOverlay() {
    const overlay = $('pdf-overlay');
    overlay.innerHTML = '';
    const [pw, ph] = appState.pageSize;
    if (!pw || !ph) return;
    appState.pageWidgets.forEach((w) => {
      if (w.type === 'button' && w.readonly) return;
      const r = w.rect;
      if (!Array.isArray(r) || r.length < 4) return;
      const left = (Math.min(r[0], r[2]) / pw) * 100;
      const right = (Math.max(r[0], r[2]) / pw) * 100;
      const top = ((ph - Math.max(r[1], r[3])) / ph) * 100;
      const bottom = ((ph - Math.min(r[1], r[3])) / ph) * 100;
      const box = document.createElement('div');
      box.className = 'widget-box';
      box.style.left = `${left}%`;
      box.style.top = `${top}%`;
      box.style.width = `${Math.max(0.5, right - left)}%`;
      box.style.height = `${Math.max(0.5, bottom - top)}%`;
      box.title = `${w.name} (${w.type})`;
      box.addEventListener('click', async (ev) => {
        ev.stopPropagation();
        const shift = $('chk-shift').checked || ev.shiftKey;
        const modifier = ev.ctrlKey || ev.metaKey;
        if (w.type === 'button' || w.type === 'checkbox' || w.type === 'radiobutton') {
          await activateField(w.name, w.index || 0, shift, modifier);
        } else {
          openFieldEditorByName(w.name);
        }
      });
      overlay.appendChild(box);
    });
  }

  // --- TOOLS TAB ---
  document.querySelectorAll('[data-cmd]').forEach((btn) => {
    btn.addEventListener('click', () => runCommand(btn.dataset.cmd));
  });
  $('field-search').addEventListener('input', renderFieldList);
  $('field-filter').addEventListener('change', renderFieldList);

  function renderTools() {
    const s = appState.sheet;
    if (!s || !s.open) return;

    const menuBox = $('mpmb-menus');
    menuBox.innerHTML = '';
    (s.menus || []).forEach((m) => {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'btn small';
      btn.disabled = !m.enabled;
      btn.textContent = (m.marked ? '✓ ' : '') + (m.label || m.name);
      btn.title = m.tooltip || m.name;
      btn.addEventListener('click', () => invokeMenu(m.name));
      menuBox.appendChild(btn);
    });

    renderFieldList();

    const bmBox = $('bookmarks-tree');
    bmBox.innerHTML = '';
    function renderBm(node, path, depth) {
      if (!node || !Array.isArray(node.children)) return;
      node.children.forEach((child, idx) => {
        const childPath = `${path}.children[${idx}]`;
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'bm-item';
        btn.style.marginLeft = `${depth * 14}px`;
        btn.textContent = child.name || '(Bookmark)';
        btn.addEventListener('click', () => runBookmark(childPath));
        bmBox.appendChild(btn);
        if (child.children && child.children.length) {
          renderBm(child, childPath, depth + 1);
        }
      });
    }
    renderBm(s.bookmarks, 'bookmarkRoot', 0);

    $('diag-output').textContent = JSON.stringify(
      {
        revision: s.revision,
        pageCount: s.pageCount,
        diagnostics: s.diagnostics,
        console: s.console,
      },
      null,
      2
    );
  }

  function renderFieldList() {
    const list = $('field-list');
    list.innerHTML = '';
    const s = appState.sheet;
    if (!s || !s.open) return;
    const q = ($('field-search').value || '').trim().toLowerCase();
    const filter = $('field-filter').value;
    const pageNames = new Set((appState.pageWidgets || []).map((w) => w.name));
    let shown = 0;
    for (const f of s.fields || []) {
      if (filter === 'writable' && (f.readonly || f.type === 'button')) continue;
      if (filter === 'page' && !pageNames.has(f.name)) continue;
      if (q && !f.name.toLowerCase().includes(q)) continue;
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'field-item';
      btn.innerHTML = `<span>${esc(f.name)}</span><span class="ftype">${esc(f.type)}${f.readonly ? ' · RO' : ''}</span>`;
      btn.addEventListener('click', () => openFieldEditorByName(f.name));
      list.appendChild(btn);
      shown++;
      if (shown >= 120) break;
    }
    if (shown === 0) {
      list.innerHTML = '<div class="muted small-text">No matching fields.</div>';
    }
  }

  // --- QUICK FIELD EDITOR MODAL ---
  async function openFieldEditorByName(name) {
    const target = currentSessionRef();
    if (!name || !target) return;
    try {
      const qs = new URLSearchParams({ name, sheet: target.sheet });
      if (target.session) qs.set('session', target.session);
      const info = await api(`/api/session/field?${qs.toString()}`);
      if (!isCurrentSession(target)) return;
      info._target = target;
      appState.selectedField = info;
      $('fm-title').textContent = info.name;
      $('fm-meta').textContent = `${info.type}${info.readonly ? ' • read-only' : ''}`;
      const body = $('fm-body');
      body.innerHTML = '';
      if ((info.type === 'combobox' || info.type === 'listbox') && Array.isArray(info.items) && info.items.length > 0 && !info.editable) {
        const sel = document.createElement('select');
        sel.id = 'fm-input';
        info.items.forEach(([label, val]) => {
          const opt = document.createElement('option');
          opt.value = val;
          opt.textContent = label;
          if (val === info.value || label === info.value) opt.selected = true;
          sel.appendChild(opt);
        });
        sel.disabled = !!info.readonly;
        body.appendChild(sel);
      } else if (info.multiline) {
        const ta = document.createElement('textarea');
        ta.id = 'fm-input';
        ta.value = info.value || '';
        ta.readOnly = !!info.readonly;
        body.appendChild(ta);
      } else {
        const inp = document.createElement('input');
        inp.type = 'text';
        inp.id = 'fm-input';
        inp.value = info.value || '';
        inp.readOnly = !!info.readonly;
        body.appendChild(inp);
        if (Array.isArray(info.items) && info.items.length > 0) {
          const sel = document.createElement('select');
          sel.innerHTML = '<option value="">Choose preset…</option>';
          info.items.forEach(([label, val]) => {
            const opt = document.createElement('option');
            opt.value = val;
            opt.textContent = label;
            sel.appendChild(opt);
          });
          sel.addEventListener('change', () => {
            if (sel.value) inp.value = sel.value;
          });
          body.appendChild(sel);
        }
      }
      $('fm-save').disabled = !!info.readonly || info.type === 'button';
      $('field-modal').classList.remove('hidden');
      setTimeout(() => $('fm-input')?.focus(), 50);
    } catch (err) {
      showBanner(err.message, 'err');
    }
  }

  function closeFieldModal() {
    $('field-modal').classList.add('hidden');
    appState.selectedField = null;
  }
  $('fm-close').addEventListener('click', closeFieldModal);
  $('fm-cancel').addEventListener('click', closeFieldModal);
  $('fm-save').addEventListener('click', async () => {
    const info = appState.selectedField;
    const inp = $('fm-input');
    if (!info || !inp) return;
    const target = info._target;
    if (!isCurrentSession(target)) {
      closeFieldModal();
      showBanner('Active sheet changed; edit was cancelled to avoid modifying the wrong character', 'warn', 5000);
      return;
    }
    const mode = (info.type === 'combobox' || info.type === 'listbox') && !info.editable ? 'choice' : 'user';
    closeFieldModal();
    await editField(info.name, inp.value, mode, target);
  });

  // --- SESSION ACTIONS ---
  async function handleActionResponse(res) {
    if (!res) return false;
    if (res.status === 'interaction_required' && res.interaction) {
      return openAcrobatInteraction(res.interaction);
    }
    let applied = true;
    if (res.state) applied = applySessionState(res.state);
    if (applied && res.message) showBanner(res.message, 'ok', 3000);
    return applied;
  }

  function currentSessionRef() {
    if (!appState.sheet || !appState.sheet.open) return null;
    return {
      sheet: appState.sheet.path || '',
      session: appState.sheet.sessionId || '',
    };
  }

  function isCurrentSession(ref) {
    if (!ref) return false;
    const cur = currentSessionRef();
    if (!cur) return false;
    return cur.sheet === ref.sheet && cur.session === ref.session;
  }

  function targetPayload(target) {
    const ref = target || currentSessionRef();
    if (!ref) return {};
    const out = { sheet: ref.sheet };
    if (ref.session) out.session = ref.session;
    return out;
  }

  async function editField(field, value, mode = 'user', target = null) {
    try {
      const res = await api('/api/session/edit', {
        method: 'POST',
        json: Object.assign({ field, value, mode }, targetPayload(target)),
      });
      await handleActionResponse(res);
    } catch (err) {
      showBanner(err.message, 'err');
    }
  }

  async function activateField(field, index = 0, shift = false, modifier = false, target = null) {
    try {
      const res = await api('/api/session/activate', {
        method: 'POST',
        json: Object.assign({ field, index, shift, modifier }, targetPayload(target)),
      });
      await handleActionResponse(res);
    } catch (err) {
      showBanner(err.message, 'err');
    }
  }

  async function invokeMenu(name, target = null) {
    try {
      const res = await api('/api/session/menu', {
        method: 'POST',
        json: Object.assign({ name }, targetPayload(target)),
      });
      await handleActionResponse(res);
    } catch (err) {
      showBanner(err.message, 'err');
    }
  }

  async function runCommand(action, target = null) {
    try {
      const res = await api('/api/session/command', {
        method: 'POST',
        json: Object.assign({ action }, targetPayload(target)),
      });
      await handleActionResponse(res);
    } catch (err) {
      showBanner(err.message, 'err');
    }
  }

  async function runBookmark(path, target = null) {
    try {
      const res = await api('/api/session/bookmark', {
        method: 'POST',
        json: Object.assign({ path }, targetPayload(target)),
      });
      await handleActionResponse(res);
    } catch (err) {
      showBanner(err.message, 'err');
    }
  }

  // --- LIVE ACROBAT MODAL / POPUP MENU / ALERT RENDERER ---
  function optionMinOrder(val) {
    if (typeof val === 'number') return Math.abs(val);
    if (val && typeof val === 'object') {
      let best = Infinity;
      for (const v of Object.values(val)) best = Math.min(best, optionMinOrder(v));
      return best;
    }
    return Infinity;
  }

  function optionLeaves(obj, prefix = [], out = []) {
    if (!obj || typeof obj !== 'object') return out;
    const entries = Object.entries(obj).sort(([ka, va], [kb, vb]) => {
      const d = optionMinOrder(va) - optionMinOrder(vb);
      return d !== 0 ? d : ka.localeCompare(kb);
    });
    for (const [k, v] of entries) {
      const next = prefix.concat([k]);
      if (typeof v === 'number') out.push({ path: next, value: v });
      else if (v && typeof v === 'object') optionLeaves(v, next, out);
    }
    return out;
  }

  function selectOption(tree, targetPath, multiple) {
    function clear(node) {
      if (!node || typeof node !== 'object') return;
      for (const k of Object.keys(node)) {
        if (typeof node[k] === 'number') node[k] = -Math.max(1, Math.abs(node[k]));
        else clear(node[k]);
      }
    }
    if (!multiple) clear(tree);
    let cur = tree;
    for (let i = 0; i < targetPath.length - 1; i++) cur = cur[targetPath[i]];
    const leaf = targetPath[targetPath.length - 1];
    const old = typeof cur[leaf] === 'number' ? cur[leaf] : -1;
    cur[leaf] = multiple && old > 0 ? -old : Math.max(1, Math.abs(old));
  }

  function interactionKey(inter) {
    if (!inter || !inter.id) return '';
    const inst = inter.serverInstanceId || appState.lastServerInstanceId || '';
    return `${inst}:${inter.id}`;
  }

  function retireInteraction(id, serverInstanceId = null) {
    if (!id) return;
    const inst = serverInstanceId || appState.lastServerInstanceId || '';
    appState.retiredInteractionKeys.add(`${inst}:${id}`);
  }

  function openAcrobatInteraction(interaction) {
    if (!interaction || !interaction.id) return false;
    if (
      interaction.serverInstanceId &&
      appState.retiredServerInstanceIds.has(interaction.serverInstanceId)
    ) {
      return false;
    }
    const key = interactionKey(interaction);
    if (appState.retiredInteractionKeys.has(key)) {
      return false;
    }
    // Preserve in-progress user input if a duplicate delivery arrives for the
    // exact same active interaction ID (e.g. HTTP 202 arriving after WS).
    if (appState.activeInteraction && interactionKey(appState.activeInteraction) === key) {
      $('acrobat-modal').classList.remove('hidden');
      return true;
    }
    if (appState.activeInteraction) {
      retireInteraction(appState.activeInteraction.id, appState.activeInteraction.serverInstanceId);
    }
    appState.activeInteraction = interaction;
    const body = $('am-body');
    const footer = $('am-footer');
    body.innerHTML = '';
    footer.innerHTML = '';

    if (interaction.kind === 'alert') {
      const req = interaction.request || {};
      $('am-title').textContent = req.cTitle || 'MPMB Alert';
      const msg = document.createElement('div');
      msg.className = 'ac-static';
      msg.textContent = req.cMsg || '';
      body.appendChild(msg);

      let chkInput = null;
      if (req.oCheckbox) {
        const lbl = document.createElement('label');
        lbl.className = 'ac-check';
        chkInput = document.createElement('input');
        chkInput.type = 'checkbox';
        chkInput.checked = !!req.oCheckbox.bInitialValue;
        lbl.appendChild(chkInput);
        lbl.appendChild(document.createTextNode(req.oCheckbox.cMsg || 'Do not show again'));
        body.appendChild(lbl);
      }

      const nType = Number(req.nType || 0);
      const buttons =
        nType === 1 ? [['Cancel', 2], ['OK', 1]] :
        nType === 2 ? [['No', 3], ['Yes', 4]] :
        nType === 3 ? [['Cancel', 2], ['No', 3], ['Yes', 4]] :
        [['OK', 1]];
      buttons.forEach(([label, code], idx) => {
        const b = document.createElement('button');
        b.type = 'button';
        b.className = idx === buttons.length - 1 ? 'btn primary' : 'btn';
        b.textContent = label;
        b.addEventListener('click', () => submitInteraction({ button: code, checked: !!(chkInput && chkInput.checked) }));
        footer.appendChild(b);
      });
      $('acrobat-modal').classList.remove('hidden');
      return true;
    }

    // Standard Acrobat execDialog / popUpMenuEx
    const req = interaction.request || {};
    const desc = req.description || {};
    $('am-title').textContent = desc.name || 'MPMB Dialog';
    appState.modalValues = JSON.parse(JSON.stringify(req.values || {}));
    appState.modalPopupOptions = {};
    for (const [k, v] of Object.entries(appState.modalValues)) {
      if (v && typeof v === 'object' && !Array.isArray(v) && v.argb === undefined) {
        appState.modalPopupOptions[k] = JSON.parse(JSON.stringify(v));
      }
    }
    const enabled = req.enabled || {};
    const visible = req.visible || {};
    const red = req.red || {};

    function renderNode(el, parentDisabled = false) {
      if (!el) return null;
      const id = el.item_id || '';
      const kind = el.type || 'view';
      if (visible[id] === false || (typeof el.height === 'number' && el.height < 0)) return null;
      const disabled = parentDisabled || enabled[id] === false;

      if (Array.isArray(el.elements)) {
        if (kind === 'cluster') {
          const det = document.createElement('details');
          det.className = 'ac-cluster';
          det.open = true;
          const sum = document.createElement('summary');
          sum.textContent = el.name || 'Options';
          det.appendChild(sum);
          const inner = document.createElement('div');
          inner.className = el.align_children === 'align_row' ? 'ac-row' : 'ac-col';
          el.elements.forEach((c) => {
            const child = renderNode(c, disabled);
            if (child) inner.appendChild(child);
          });
          det.appendChild(inner);
          return det;
        }
        const wrap = document.createElement('div');
        wrap.className = (el.align_children === 'align_row' || el.align_children === 'align_distribute') ? 'ac-row' : 'ac-col';
        el.elements.forEach((c) => {
          const child = renderNode(c, disabled);
          if (child) wrap.appendChild(child);
        });
        return wrap;
      }

      const rawVal = Object.prototype.hasOwnProperty.call(appState.modalValues, id) ? appState.modalValues[id] : undefined;
      const textClass = `ac-static${el.bold ? ' ac-bold' : ''}${red[id] ? ' ac-red' : ''}`;

      if (kind === 'static_text') {
        const div = document.createElement('div');
        div.className = textClass;
        div.textContent = (typeof rawVal === 'string' && rawVal.length > 0) ? rawVal : (el.name || '');
        return div;
      }
      if (kind === 'link_text') {
        const b = document.createElement('button');
        b.type = 'button';
        b.className = `ac-link${el.bold ? ' ac-bold' : ''}${red[id] ? ' ac-red' : ''}`;
        b.disabled = disabled;
        b.textContent = (typeof rawVal === 'string' && rawVal.length > 0) ? rawVal : (el.name || '');
        b.addEventListener('click', () => submitInteraction({ event: id, values: appState.modalValues }));
        return b;
      }
      if (kind === 'button') {
        const b = document.createElement('button');
        b.type = 'button';
        b.className = 'btn';
        b.disabled = disabled;
        b.textContent = (typeof rawVal === 'string' && rawVal.length > 0) ? rawVal : (el.name || id);
        b.addEventListener('click', () => submitInteraction({ event: id, values: appState.modalValues }));
        return b;
      }
      if (kind === 'ok' || kind === 'ok_cancel' || kind === 'ok_cancel_other') {
        const row = document.createElement('div');
        row.className = 'ac-row';
        const okBtn = document.createElement('button');
        okBtn.type = 'button';
        okBtn.className = 'btn primary';
        okBtn.disabled = disabled;
        okBtn.textContent = el.ok_name || 'OK';
        okBtn.addEventListener('pointerdown', () => { appState.suppressNextBlurSubmit = true; });
        okBtn.addEventListener('click', () => submitInteraction({ result: 'ok', values: appState.modalValues }));
        row.appendChild(okBtn);
        if (kind === 'ok_cancel_other') {
          const otherBtn = document.createElement('button');
          otherBtn.type = 'button';
          otherBtn.className = 'btn';
          otherBtn.disabled = disabled;
          otherBtn.textContent = el.other_name || 'Other';
          otherBtn.addEventListener('pointerdown', () => { appState.suppressNextBlurSubmit = true; });
          otherBtn.addEventListener('click', () => submitInteraction({ result: 'other', values: appState.modalValues }));
          row.appendChild(otherBtn);
        }
        if (kind !== 'ok') {
          const cancelBtn = document.createElement('button');
          cancelBtn.type = 'button';
          cancelBtn.className = 'btn';
          cancelBtn.textContent = el.cancel_name || 'Cancel';
          cancelBtn.addEventListener('pointerdown', () => { appState.suppressNextBlurSubmit = true; });
          cancelBtn.addEventListener('click', () => submitInteraction({ result: 'cancel', values: appState.modalValues }));
          row.appendChild(cancelBtn);
        }
        return row;
      }
      if (kind === 'check_box') {
        const lbl = document.createElement('label');
        lbl.className = 'ac-check';
        const inp = document.createElement('input');
        inp.type = 'checkbox';
        inp.checked = !!rawVal;
        inp.disabled = disabled;
        inp.addEventListener('change', () => {
          appState.modalValues[id] = inp.checked;
          submitInteraction({ event: id, values: appState.modalValues });
        });
        lbl.appendChild(inp);
        const span = document.createElement('span');
        span.className = textClass;
        span.textContent = el.name || id;
        lbl.appendChild(span);
        return lbl;
      }
      if (kind === 'radio') {
        const lbl = document.createElement('label');
        lbl.className = 'ac-check';
        const inp = document.createElement('input');
        inp.type = 'radio';
        inp.name = el.group_id || 'radio';
        inp.checked = !!rawVal;
        inp.disabled = disabled;
        inp.addEventListener('change', () => {
          appState.modalValues[id] = true;
          submitInteraction({ event: id, values: appState.modalValues });
        });
        lbl.appendChild(inp);
        const span = document.createElement('span');
        span.className = textClass;
        span.textContent = el.name || id;
        lbl.appendChild(span);
        return lbl;
      }
      if (kind === 'edit_text' && el.PopupEdit && (isPlainObj(rawVal) || appState.modalPopupOptions[id])) {
        const opts = appState.modalPopupOptions[id] || (isPlainObj(rawVal) ? rawVal : {});
        const leaves = optionLeaves(opts);
        const selectedLeaf = leaves.find((l) => l.value > 0);
        const wrap = document.createElement('div');
        wrap.className = 'ac-col';
        const inp = document.createElement('input');
        inp.type = 'text';
        inp.value = typeof rawVal === 'string' ? rawVal : (selectedLeaf ? selectedLeaf.path[selectedLeaf.path.length - 1] : '');
        inp.disabled = disabled || !!el.readonly;
        inp.addEventListener('change', () => {
          appState.modalValues[id] = inp.value;
          submitInteraction({ event: id, values: appState.modalValues });
        });
        wrap.appendChild(inp);
        if (leaves.length > 0) {
          const sel = document.createElement('select');
          sel.disabled = disabled;
          sel.innerHTML = '<option value="">Select preset…</option>';
          leaves.forEach((l, idx) => {
            const opt = document.createElement('option');
            opt.value = String(idx);
            opt.textContent = l.path.join(' › ');
            if (l.value > 0) opt.selected = true;
            sel.appendChild(opt);
          });
          sel.addEventListener('change', () => {
            const chosen = leaves[Number(sel.value)];
            if (!chosen) return;
            const copy = JSON.parse(JSON.stringify(opts));
            selectOption(copy, chosen.path, false);
            appState.modalPopupOptions[id] = copy;
            appState.modalValues[id] = copy;
            submitInteraction({ event: id, values: appState.modalValues });
          });
          wrap.appendChild(sel);
        }
        return wrap;
      }
      if ((kind === 'popup' || kind === 'list_box' || kind === 'hier_list_box' || kind === 'edit_text') && isPlainObj(rawVal)) {
        const leaves = optionLeaves(rawVal);
        if (kind === 'list_box' || kind === 'hier_list_box') {
          const box = document.createElement('div');
          box.className = 'ac-listbox';
          leaves.forEach((l) => {
            const item = document.createElement('button');
            item.type = 'button';
            item.className = `ac-list-opt${l.value > 0 ? ' selected' : ''}`;
            item.disabled = disabled;
            item.textContent = l.path.join(' › ');
            item.addEventListener('click', (ev) => {
              const copy = JSON.parse(JSON.stringify(appState.modalValues[id]));
              selectOption(copy, l.path, ev.ctrlKey || ev.metaKey);
              appState.modalValues[id] = copy;
              submitInteraction({ event: id, values: appState.modalValues });
            });
            box.appendChild(item);
          });
          return box;
        }
        const sel = document.createElement('select');
        sel.disabled = disabled;
        leaves.forEach((l, idx) => {
          const opt = document.createElement('option');
          opt.value = String(idx);
          opt.textContent = l.path.join(' › ');
          if (l.value > 0) opt.selected = true;
          sel.appendChild(opt);
        });
        sel.addEventListener('change', () => {
          const chosen = leaves[Number(sel.value)];
          if (!chosen) return;
          const copy = JSON.parse(JSON.stringify(appState.modalValues[id]));
          selectOption(copy, chosen.path, false);
          appState.modalValues[id] = copy;
          submitInteraction({ event: id, values: appState.modalValues });
        });
        return sel;
      }
      if (kind === 'edit_text') {
        const isMulti = !!el.multiline || (el.char_height && el.char_height > 1);
        const isSpin = !!el.SpinEdit && !el.PopupEdit && !el.readonly;
        const wrap = document.createElement('div');
        wrap.className = isSpin ? 'ac-spin' : 'ac-col';
        const inp = document.createElement(isMulti ? 'textarea' : 'input');
        if (!isMulti) inp.type = el.password ? 'password' : 'text';
        inp.value = rawVal === undefined || rawVal === null ? '' : String(rawVal);
        inp.disabled = disabled;
        inp.readOnly = !!el.readonly;
        inp.addEventListener('input', () => {
          appState.modalValues[id] = inp.value;
        });
        inp.addEventListener('change', () => {
          appState.modalValues[id] = inp.value;
          if (appState.suppressNextBlurSubmit) {
            appState.suppressNextBlurSubmit = false;
            return;
          }
          submitInteraction({ event: id, values: appState.modalValues });
        });
        wrap.appendChild(inp);
        if (isSpin) {
          const minus = document.createElement('button');
          minus.type = 'button';
          minus.className = 'btn small';
          minus.disabled = disabled;
          minus.textContent = '−';
          minus.addEventListener('click', () => {
            const n = parseInt(inp.value, 10) || 0;
            appState.modalValues[id] = String(n - 1);
            submitInteraction({ event: id, values: appState.modalValues });
          });
          const plus = document.createElement('button');
          plus.type = 'button';
          plus.className = 'btn small';
          plus.disabled = disabled;
          plus.textContent = '+';
          plus.addEventListener('click', () => {
            const n = parseInt(inp.value, 10) || 0;
            appState.modalValues[id] = String(n + 1);
            submitInteraction({ event: id, values: appState.modalValues });
          });
          wrap.appendChild(minus);
          wrap.appendChild(plus);
        }
        return wrap;
      }
      if (kind === 'image' && rawVal && rawVal.argb && rawVal.width && rawVal.height) {
        const c = document.createElement('canvas');
        c.width = rawVal.width;
        c.height = rawVal.height;
        const ctx = c.getContext('2d');
        const img = ctx.createImageData(rawVal.width, rawVal.height);
        const hex = rawVal.argb;
        for (let i = 0, p = 0; i + 8 <= hex.length && p < img.data.length; i += 8, p += 4) {
          const v = parseInt(hex.slice(i, i + 8), 16);
          img.data[p] = (v >> 16) & 255;
          img.data[p + 1] = (v >> 8) & 255;
          img.data[p + 2] = v & 255;
          img.data[p + 3] = (v >>> 24) & 255;
        }
        ctx.putImageData(img, 0, 0);
        return c;
      }
      if (kind === 'gap') {
        const g = document.createElement('div');
        g.className = 'ac-gap';
        return g;
      }
      return null;
    }

    const rendered = renderNode(desc);
    if (rendered) body.appendChild(rendered);

    // Always offer a Cancel button in the footer if the dialog didn't embed ok_cancel buttons (e.g. popup menus).
    const cancelBtn = document.createElement('button');
    cancelBtn.type = 'button';
    cancelBtn.className = 'btn';
    cancelBtn.textContent = 'Close / Cancel';
    cancelBtn.addEventListener('pointerdown', () => { appState.suppressNextBlurSubmit = true; });
    cancelBtn.addEventListener('click', () => submitInteraction({ result: 'cancel', values: appState.modalValues }));
    footer.appendChild(cancelBtn);

    $('acrobat-modal').classList.remove('hidden');
    return true;
  }

  function closeAcrobatModal(clearedId = null, clearedServerInstanceId = null) {
    if (clearedId) {
      const clearedKey = interactionKey({
        id: clearedId,
        serverInstanceId: clearedServerInstanceId,
      });
      retireInteraction(clearedId, clearedServerInstanceId);
      if (appState.activeInteraction && interactionKey(appState.activeInteraction) !== clearedKey) {
        return;
      }
      if (appState.inFlightInteractionKey === clearedKey) {
        appState.inFlightInteractionKey = null;
      }
    } else if (appState.activeInteraction) {
      const activeKey = interactionKey(appState.activeInteraction);
      retireInteraction(
        appState.activeInteraction.id,
        appState.activeInteraction.serverInstanceId
      );
      if (appState.inFlightInteractionKey === activeKey) {
        appState.inFlightInteractionKey = null;
      }
    } else {
      appState.inFlightInteractionKey = null;
    }
    $('acrobat-modal').classList.add('hidden');
    appState.activeInteraction = null;
    appState.suppressNextBlurSubmit = false;
  }

  $('am-close').addEventListener('pointerdown', () => { appState.suppressNextBlurSubmit = true; });
  $('am-close').addEventListener('click', () => {
    const inter = appState.activeInteraction;
    if (!inter) return closeAcrobatModal();
    if (inter.kind === 'alert') {
      const nType = Number(inter.request?.nType || 0);
      const code = (nType === 1 || nType === 3) ? 2 : nType === 2 ? 4 : 1;
      submitInteraction({ button: code, checked: false });
    } else {
      submitInteraction({ result: 'cancel', values: appState.modalValues });
    }
  });

  async function submitInteraction(reply) {
    const inter = appState.activeInteraction;
    if (!inter) return;
    const interId = inter.id;
    const interServerId = inter.serverInstanceId || appState.lastServerInstanceId || '';
    const interKey = interactionKey({ id: interId, serverInstanceId: interServerId });
    appState.suppressNextBlurSubmit = false;
    if (appState.inFlightInteractionKey === interKey) return;
    appState.inFlightInteractionKey = interKey;
    const wasUnopened = !appState.sheet || !appState.sheet.open;
    const prevSessionId = appState.sheet?.sessionId || null;
    try {
      const res = await api(`/api/session/interaction/${encodeURIComponent(interId)}`, {
        method: 'POST',
        json: reply,
      });
      if (appState.inFlightInteractionKey === interKey) {
        appState.inFlightInteractionKey = null;
      }
      if (res.status === 'interaction_required' && res.interaction) {
        retireInteraction(interId, interServerId);
        openAcrobatInteraction(res.interaction);
      } else {
        closeAcrobatModal(interId, interServerId);
        if (res.state) {
          const switchedToNewSession = Boolean(
            res.state.open && (wasUnopened || (res.state.sessionId && res.state.sessionId !== prevSessionId))
          );
          if (applySessionState(res.state) && switchedToNewSession) {
            appState.page = 0;
            showBanner(`Loaded ${res.state.path}`, 'ok', 2500);
            if (activeNewCharModalInstance === null) {
              switchTab('play');
              const destFocus = $('btn-classes');
              if (destFocus && typeof destFocus.focus === 'function') destFocus.focus();
            }
            refreshLibrary();
          }
        }
      }
    } catch (err) {
      if (appState.inFlightInteractionKey === interKey) {
        appState.inFlightInteractionKey = null;
      }
      if (err.status === 409) {
        closeAcrobatModal(interId, interServerId);
        showBanner(err.message, 'err');
      } else if (
        appState.activeInteraction &&
        interactionKey(appState.activeInteraction) === interKey
      ) {
        closeAcrobatModal(interId, interServerId);
        showBanner(err.message, 'err');
      }
    }
  }

  // --- LIBRARY & GIT TAB ---
  function renderGit() {
    const g = appState.git;
    const badge = $('git-badge');
    const summary = $('git-summary');
    const conflictBox = $('git-conflict-box');
    const syncBtn = $('btn-git-sync');
    const pullBtn = $('btn-git-pull');
    const histCard = $('git-history-card');

    if (!g || !g.enabled) {
      badge.textContent = 'Local Store';
      badge.className = 'status-badge';
      summary.textContent = 'Running against local directory storage. Pass --git-repo / MPMB_GIT_REPO to enable GitHub sync.';
      syncBtn.disabled = true;
      pullBtn.disabled = true;
      conflictBox.classList.add('hidden');
      histCard.classList.add('hidden');
      return;
    }

    syncBtn.disabled = false;
    pullBtn.disabled = false;
    histCard.classList.remove('hidden');

    if (g.last_conflict_branch) {
      badge.textContent = 'Conflict Branch';
      badge.className = 'status-badge warn';
      conflictBox.textContent = `Diverged edits were preserved safely on remote branch "${g.last_conflict_branch}".`;
      conflictBox.classList.remove('hidden');
    } else if (g.dirty || g.ahead > 0) {
      badge.textContent = `${g.changed_files.length} Unsynced`;
      badge.className = 'status-badge warn';
      conflictBox.classList.add('hidden');
    } else {
      badge.textContent = 'Synced ✓';
      badge.className = 'status-badge ok';
      conflictBox.classList.add('hidden');
    }

    const parts = [
      `Branch: ${g.branch || 'main'}`,
      g.head_sha ? `HEAD: ${g.head_sha.slice(0, 7)}` : 'No commits yet',
      g.repo_url ? `Remote: ${g.repo_url}` : '',
      g.last_error ? `Note: ${g.last_error}` : '',
    ].filter(Boolean);
    summary.textContent = parts.join(' • ');
  }

  function isTemplateSheet(sh) {
    return Boolean(sh && (sh.is_template || String(sh.path || '').toLowerCase().startsWith('templates/')));
  }

  function preferredDefaultTemplate() {
    const tpls = appState.templates || [];
    if (!tpls.length) return null;
    return (
      tpls.find((t) => /2024/i.test(t.name || t.path)) ||
      tpls.find((t) => /v24/i.test(t.name || t.path)) ||
      tpls[0]
    );
  }

  function formatTemplateLabel(sh) {
    return String(sh.name || sh.path || '').replace(/\.pdf$/i, '');
  }

  let newCharModalOpener = null;
  let newCharModalInstanceSeq = 0;
  let activeNewCharModalInstance = null;

  function updateNewCharPreview() {
    const preview = $('nc-preview');
    const name = ($('nc-name').value || '').trim();
    const tplPath = $('nc-template').value || '';
    const tpl = (appState.templates || []).find((t) => t.path === tplPath);
    if (!tpl) {
      preview.textContent = 'Upload a blank MPMB PDF under Sheet Templates first.';
      return;
    }
    const dest = name
      ? (name.toLowerCase().endsWith('.pdf') ? name : `${name}.pdf`)
      : '<Character Name>.pdf';
    preview.textContent = `Creates ${dest} from ${tpl.name}`;
  }

  function openNewCharModal(preselectedTemplatePath = null) {
    const tpls = appState.templates || [];
    if (!tpls.length) {
      showBanner('No templates yet — upload a blank MPMB PDF under Sheet Templates first', 'warn', 5000);
      switchTab('library');
      return;
    }
    newCharModalInstanceSeq += 1;
    activeNewCharModalInstance = newCharModalInstanceSeq;
    newCharModalOpener = document.activeElement || null;
    const sel = $('nc-template');
    sel.innerHTML = '';
    tpls.forEach((tpl) => {
      const opt = document.createElement('option');
      opt.value = tpl.path;
      opt.textContent = formatTemplateLabel(tpl);
      sel.appendChild(opt);
    });
    const def = preselectedTemplatePath || preferredDefaultTemplate()?.path || tpls[0].path;
    sel.value = def;
    $('nc-name').value = '';
    updateNewCharPreview();
    $('new-char-modal').classList.remove('hidden');
    if (typeof $('nc-name').focus === 'function') $('nc-name').focus();
  }

  function closeNewCharModal(restoreFocus = false, expectedInstance = undefined) {
    if (expectedInstance !== undefined) {
      if (expectedInstance === null || activeNewCharModalInstance !== expectedInstance) {
        return;
      }
    }
    activeNewCharModalInstance = null;
    $('new-char-modal').classList.add('hidden');
    const opener = newCharModalOpener;
    newCharModalOpener = null;
    if (restoreFocus && opener && typeof opener.focus === 'function') {
      opener.focus();
    }
  }

  async function createCharacterFromTemplate(
    template,
    name,
    force = false,
    discard = null,
    modalInstance = activeNewCharModalInstance,
  ) {
    const trimmed = String(name || '').trim();
    if (!trimmed) {
      showBanner('Enter a character name first', 'warn', 3500);
      return;
    }
    if (!template) {
      showBanner('Select a sheet template first', 'warn', 3500);
      return;
    }
    try {
      showBanner(`Creating ${trimmed}…`, 'warn', 0);
      const body = { template, name: trimmed, open: true, force };
      if (discard) body.discard = discard;
      const res = await api('/api/sheets/new', { method: 'POST', json: body });
      closeNewCharModal(false, modalInstance);
      const applied = await handleActionResponse(res);
      const createdSessionRef = res && res.state && res.state.open
        ? {
            sheet: res.state.path || '',
            session: res.state.sessionId || '',
          }
        : null;
      await refreshLibrary();
      if (
        applied &&
        res.status !== 'interaction_required' &&
        createdSessionRef &&
        isCurrentSession(createdSessionRef)
      ) {
        appState.page = 0;
        const createdPath = res.sheet?.path || trimmed;
        showBanner(`Created and opened ${createdPath}`, 'ok', 3000);
        // Do not switch tabs or steal focus behind a newer New Character form.
        const newerModalOpen =
          activeNewCharModalInstance !== null &&
          activeNewCharModalInstance !== modalInstance;
        if (!newerModalOpen) {
          switchTab('play');
          const destFocus = $('btn-classes');
          if (destFocus && typeof destFocus.focus === 'function') destFocus.focus();
        }
      }
    } catch (err) {
      if (err.status === 409 && err.data && err.data.status === 'interaction_required' && err.data.interaction) {
        closeNewCharModal(false, modalInstance);
        openAcrobatInteraction(err.data.interaction);
        showBanner('Finish or cancel the active dialog before creating a new character', 'warn', 5000);
        return;
      }
      const target = err.data && err.data.discardTarget;
      if (err.status === 409 && !force && target) {
        const originatingFormActive =
          modalInstance === null
            ? activeNewCharModalInstance === null
            : activeNewCharModalInstance === modalInstance;
        if (!originatingFormActive) {
          showBanner(`Creation request for ${trimmed} is out of date`, 'warn', 5000);
          return;
        }
        if (
          confirm(`${err.message}\n\nDiscard unsaved edits on ${target.sheet} (rev ${target.revision}) and create ${trimmed}?`)
        ) {
          const stillActiveAfterConfirm =
            modalInstance === null
              ? activeNewCharModalInstance === null
              : activeNewCharModalInstance === modalInstance;
          if (!stillActiveAfterConfirm) {
            showBanner(`Creation request for ${trimmed} is out of date`, 'warn', 5000);
            return;
          }
          return createCharacterFromTemplate(template, trimmed, true, target, modalInstance);
        }
      }
      if (err.status === 409 && force) {
        refreshSession();
      }
      showBanner(err.message, 'err', 6000);
    }
  }

  $('nc-close').addEventListener('click', () => closeNewCharModal(true));
  $('nc-cancel').addEventListener('click', () => closeNewCharModal(true));
  $('new-char-modal').addEventListener('keydown', (ev) => {
    if (ev.key === 'Escape') {
      ev.preventDefault();
      closeNewCharModal(true);
    }
  });
  $('nc-name').addEventListener('input', updateNewCharPreview);
  $('nc-template').addEventListener('change', updateNewCharPreview);
  $('nc-name').addEventListener('keydown', (ev) => {
    if (ev.key === 'Enter') {
      ev.preventDefault();
      createCharacterFromTemplate($('nc-template').value, $('nc-name').value);
    }
  });
  $('nc-create').addEventListener('click', () => {
    createCharacterFromTemplate($('nc-template').value, $('nc-name').value);
  });

  function buildCharacterRow(sh, activePath) {
    const row = document.createElement('div');
    row.className = 'row-card';
    const title = sh.character_name ? `${sh.character_name} (${sh.name})` : sh.name;
    const meta = [
      sh.class_and_levels || (sh.level ? `Lv ${sh.level}` : ''),
      `${(sh.size_bytes / (1024 * 1024)).toFixed(2)} MB`,
      sh.path,
    ].filter(Boolean).join(' • ');
    row.innerHTML = `
      <div class="row-main">
        <div class="row-title">${esc(title)}</div>
        <div class="row-sub">${esc(meta)}</div>
      </div>
    `;
    const actions = document.createElement('div');
    actions.className = 'seg-group';
    const dl = document.createElement('a');
    const tokenQs = appState.token ? `?token=${encodeURIComponent(appState.token)}` : '';
    dl.href = `/api/sheets/${encodeURIComponent(sh.path)}/download${tokenQs}`;
    dl.className = 'btn small';
    dl.textContent = '↓';
    dl.title = 'Download PDF';
    const openBtn = document.createElement('button');
    openBtn.type = 'button';
    openBtn.className = activePath === sh.path ? 'btn small accent' : 'btn small primary';
    openBtn.textContent = activePath === sh.path ? 'Open ✓' : 'Open';
    openBtn.addEventListener('click', () => openSheet(sh.path));
    actions.appendChild(dl);
    actions.appendChild(openBtn);
    row.appendChild(actions);
    return row;
  }

  function renderSheets() {
    const list = $('sheets-list');
    const tplList = $('templates-list');
    const emptyChars = $('empty-chars-list');
    list.innerHTML = '';
    tplList.innerHTML = '';
    emptyChars.innerHTML = '';

    const activePath = appState.sheet?.path;
    const chars = appState.characters || [];
    const tpls = appState.templates || [];

    if (!chars.length) {
      list.innerHTML = tpls.length
        ? '<div class="muted small-text">No characters yet. Tap "+ New Character" to start from a blank MPMB template.</div>'
        : '<div class="muted small-text">No characters yet. Upload a blank template below or upload a PDF.</div>';
      emptyChars.classList.add('hidden');
    } else {
      chars.forEach((sh) => {
        list.appendChild(buildCharacterRow(sh, activePath));
        emptyChars.appendChild(buildCharacterRow(sh, activePath));
      });
      emptyChars.classList.remove('hidden');
    }

    if (!tpls.length) {
      tplList.innerHTML = '<div class="muted small-text">No sheet templates yet. Tap "Upload Template" to add a blank MPMB PDF.</div>';
    } else {
      tpls.forEach((tpl) => {
        const row = document.createElement('div');
        row.className = 'row-card';
        const meta = [
          `${(tpl.size_bytes / (1024 * 1024)).toFixed(2)} MB`,
          tpl.path,
        ].join(' • ');
        row.innerHTML = `
          <div class="row-main">
            <div class="row-title">${esc(formatTemplateLabel(tpl))}</div>
            <div class="row-sub">${esc(meta)}</div>
          </div>
        `;
        const actions = document.createElement('div');
        actions.className = 'seg-group';
        const dl = document.createElement('a');
        const tokenQs = appState.token ? `?token=${encodeURIComponent(appState.token)}` : '';
        dl.href = `/api/sheets/${encodeURIComponent(tpl.path)}/download${tokenQs}`;
        dl.className = 'btn small';
        dl.textContent = '↓';
        dl.title = 'Download Template PDF';
        const useBtn = document.createElement('button');
        useBtn.type = 'button';
        useBtn.className = 'btn small primary';
        useBtn.textContent = '+ New';
        useBtn.addEventListener('click', () => openNewCharModal(tpl.path));
        actions.appendChild(dl);
        actions.appendChild(useBtn);
        row.appendChild(actions);
        tplList.appendChild(row);
      });
    }
  }

  function renderHistory(commits) {
    const box = $('git-history-list');
    box.innerHTML = '';
    if (!commits.length) {
      box.innerHTML = '<div class="muted small-text">No commits yet.</div>';
      return;
    }
    commits.forEach((c) => {
      const row = document.createElement('div');
      row.className = 'row-card';
      row.innerHTML = `
        <div class="row-main">
          <div class="row-title">${esc(c.subject)}</div>
          <div class="row-sub">${esc(c.short_sha)} • ${esc(c.author)} • ${esc(c.date)}</div>
        </div>
      `;
      box.appendChild(row);
    });
  }

  async function openSheet(path, force = false, discard = null) {
    try {
      showBanner(`Loading ${path}…`, 'warn', 0);
      const body = { path, force };
      if (discard) body.discard = discard;
      const res = await api('/api/session/open', { method: 'POST', json: body });
      const applied = await handleActionResponse(res);
      if (applied && res.status !== 'interaction_required') {
        appState.page = 0;
        showBanner(`Loaded ${path}`, 'ok', 2500);
        switchTab('play');
      }
    } catch (err) {
      if (err.status === 409 && err.data && err.data.status === 'interaction_required' && err.data.interaction) {
        openAcrobatInteraction(err.data.interaction);
        showBanner('Finish or cancel the active dialog before switching sheets', 'warn', 5000);
        return;
      }
      const target = err.data && err.data.discardTarget;
      if (
        err.status === 409 &&
        !force &&
        target &&
        confirm(`${err.message}\n\nDiscard unsaved edits on ${target.sheet} (rev ${target.revision}) and open ${path}?`)
      ) {
        return openSheet(path, true, target);
      }
      if (err.status === 409 && force) {
        refreshSession();
      }
      showBanner(err.message, 'err');
    }
  }

  async function doSaveNow(force = false) {
    if (force && !confirm('Overwrite the externally modified PDF on disk with your current in-memory session?')) {
      return;
    }
    try {
      const res = await api('/api/session/save', {
        method: 'POST',
        json: Object.assign({ force }, targetPayload(null)),
      });
      if (res.state) applySessionState(res.state);
      showBanner(res.message || 'Saved PDF to disk', 'ok', 3000);
      await refreshLibrary();
    } catch (err) {
      if (err.data && err.data.state) applySessionState(err.data.state);
      showBanner(err.message, 'err');
    }
  }

  async function doGitSync(message) {
    try {
      showBanner('Syncing with GitHub…', 'warn', 0);
      const res = await api('/api/git/sync', { method: 'POST', json: { message } });
      $('git-commit-msg').value = '';
      if (res.git) appState.git = res.git;
      if (res.state) applySessionState(res.state);
      const kind = res.sync?.status === 'conflict_branch' ? 'warn' : 'ok';
      showBanner(res.sync?.message || 'Synced', kind, 6000);
      await refreshLibrary();
    } catch (err) {
      showBanner(err.message, 'err', 7000);
    }
  }

  async function doGitPull(force = false, discard = null) {
    try {
      showBanner('Pulling latest from GitHub…', 'warn', 0);
      const body = { force };
      if (discard) body.discard = discard;
      const res = await api('/api/git/pull', { method: 'POST', json: body });
      if (res.state) applySessionState(res.state);
      showBanner(res.pull?.message || 'Pull complete', res.pull?.dirty ? 'warn' : 'ok', 5000);
      await refreshLibrary();
    } catch (err) {
      if (err.data && err.data.state) applySessionState(err.data.state);
      const target = err.data && err.data.discardTarget;
      if (
        err.status === 409 &&
        !force &&
        target &&
        confirm(`${err.message}\n\nDiscard unsaved edits on ${target.sheet} (rev ${target.revision}) and pull latest?`)
      ) {
        return doGitPull(true, target);
      }
      if (err.status === 409 && force) {
        refreshSession();
      }
      showBanner(err.message, 'err', 7000);
    }
  }

  $('btn-git-sync').addEventListener('click', () => doGitSync($('git-commit-msg').value.trim()));
  $('btn-git-pull').addEventListener('click', () => doGitPull(false));
  $('btn-save-now').addEventListener('click', () => doSaveNow(false));
  $('btn-force-save').addEventListener('click', () => doSaveNow(true));

  async function handlePdfUpload(file, targetName, label) {
    try {
      showBanner(`Uploading ${label}…`, 'warn', 0);
      const buf = await file.arrayBuffer();
      try {
        await api(`/api/sheets/upload?name=${encodeURIComponent(targetName)}&overwrite=false`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/pdf' },
          body: buf,
        });
      } catch (err) {
        const isAlreadyExists =
          err.status === 409 &&
          (err.data?.code === 'already_exists' ||
            (!err.data?.code && /already exists/i.test(err.message || '')));
        if (isAlreadyExists && confirm(`"${targetName}" already exists. Overwrite it?`)) {
          await api(`/api/sheets/upload?name=${encodeURIComponent(targetName)}&overwrite=true`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/pdf' },
            body: buf,
          });
        } else {
          throw err;
        }
      }
      showBanner(`Uploaded ${label}`, 'ok', 3000);
      await refreshLibrary();
    } catch (err) {
      showBanner(err.message, 'err');
    }
  }

  $('file-upload').addEventListener('change', async (ev) => {
    const file = ev.target.files?.[0];
    ev.target.value = '';
    if (!file) return;
    await handlePdfUpload(file, file.name, file.name);
  });

  $('template-upload').addEventListener('change', async (ev) => {
    const file = ev.target.files?.[0];
    ev.target.value = '';
    if (!file) return;
    await handlePdfUpload(file, `templates/${file.name}`, `template ${file.name}`);
  });

  function isPlainObj(v) {
    return v !== null && typeof v === 'object' && !Array.isArray(v) && v.argb === undefined;
  }

  function esc(s) {
    return String(s ?? '').replace(/[&<>"']/g, (c) => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[c]));
  }

  // Boot
  updateConnDot();
  connectWs();
  refreshAll();
})();
