import shutil
import subprocess
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP_JS = ROOT / "src/serve/pwa/app.js"
SW_JS = ROOT / "src/serve/pwa/sw.js"

PWA_HARNESS = textwrap.dedent(
    r"""
    const assert = require('node:assert/strict');
    const fs = require('node:fs');
    const vm = require('node:vm');

    const source = fs.readFileSync(process.argv[process.argv.length - 1], 'utf8').replace(
      '  // Boot\n  updateConnDot();\n  connectWs();\n  refreshAll();',
      '  globalThis.harness = { appState, applySessionState, openFieldEditorByName, enqueueStep, currentSessionRef, editField, activateField, openSheet, openNewCharModal, closeNewCharModal, createCharacterFromTemplate, handlePdfUpload, doGitPull, refreshSession, connectWs, openAcrobatInteraction, closeAcrobatModal, submitInteraction };'
    );

    const elements = new Map();
    function element(id) {
      if (!elements.has(id)) {
        const classes = new Set();
        const el = {
          id,
          listeners: {},
          dataset: {},
          style: {},
          value: '',
          textContent: '',
          focus() { context.document.activeElement = el; },
          classList: {
            toggle(c, force) {
              if (force === undefined) {
                if (classes.has(c)) classes.delete(c);
                else classes.add(c);
              } else if (force) classes.add(c);
              else classes.delete(c);
            },
            add(c) { classes.add(c); },
            remove(c) { classes.delete(c); },
            contains(c) { return classes.has(c); },
          },
          addEventListener(type, fn) { this.listeners[type] = fn; },
          getAttribute() {},
          setAttribute() {},
          appendChild() {},
        };
        elements.set(id, el);
      }
      return elements.get(id);
    }

    const sockets = [];
    class MockWebSocket {
      static CONNECTING = 0;
      static OPEN = 1;
      static CLOSED = 3;
      constructor(url) {
        this.url = url;
        this.readyState = MockWebSocket.CONNECTING;
        sockets.push(this);
      }
      close() {
        this.readyState = MockWebSocket.CLOSED;
      }
    }

    let fetchHandler = null;
    let confirmHandler = () => true;
    const context = {
      navigator: { onLine: true },
      localStorage: { getItem() { return ''; }, setItem() {} },
      window: { addEventListener() {}, open() {}, innerWidth: 1000, devicePixelRatio: 1 },
      document: {
        activeElement: null,
        getElementById: element,
        documentElement: element('root'),
        querySelector() { return null; },
        querySelectorAll(sel) {
          if (sel === '.tab-panel') {
            return [element('tab-play'), element('tab-sheet'), element('tab-tools'), element('tab-library')];
          }
          return [];
        },
        createElement() { return element(Symbol()); },
        createTextNode(t) { return { textContent: t }; },
      },
      URLSearchParams,
      WebSocket: MockWebSocket,
      location: { search: '', protocol: 'http:', host: '127.0.0.1:8080', pathname: '/' },
      history: { replaceState() {} },
      confirm(msg) { return confirmHandler(msg); },
      setTimeout() {},
      clearTimeout() {},
      fetch(path, options) {
        return fetchHandler(path, options);
      },
    };
    vm.createContext(context);
    vm.runInContext(source, context);
    const {
      appState,
      applySessionState,
      openFieldEditorByName,
      enqueueStep,
      currentSessionRef,
      editField,
      activateField,
      openSheet,
      openNewCharModal,
      closeNewCharModal,
      createCharacterFromTemplate,
      handlePdfUpload,
      doGitPull,
      refreshSession,
      connectWs,
      openAcrobatInteraction,
      closeAcrobatModal,
      submitInteraction,
    } = context.harness;

    function jsonResp(payload, status = 200) {
      return {
        status,
        ok: status >= 200 && status < 300,
        statusText: String(status),
        headers: { get: () => 'application/json' },
        json: async () => payload,
      };
    }

    (async () => {
      const alpha1 = {
        open: true,
        path: 'Alpha.pdf',
        serverInstanceId: 'srv-1',
        sessionId: 'srv-1-s1',
        stateSeq: 1,
        revision: 1,
        vitals: { hpCurrent: '10', hpMax: '20' },
      };
      const beta1 = {
        open: true,
        path: 'Beta.pdf',
        serverInstanceId: 'srv-1',
        sessionId: 'srv-1-s2',
        stateSeq: 2,
        revision: 1,
        vitals: { hpCurrent: '20', hpMax: '20' },
      };
      const edits = [];
      const fieldCalls = [];
      fetchHandler = async (path, options) => {
        if (path.startsWith('/api/session/field?')) {
          fieldCalls.push(path);
          return jsonResp({ name: 'HP Current', value: '10', type: 'text' });
        }
        if (path === '/api/session/edit') {
          edits.push(JSON.parse(options.body));
          return jsonResp({});
        }
        throw new Error('Unexpected fetch ' + path);
      };

      // 1. Editor opened on Alpha must not submit edit for Beta after live sheet switch.
      applySessionState(alpha1);
      await openFieldEditorByName('HP Current');
      assert.ok(fieldCalls[0].includes('sheet=Alpha.pdf'));
      assert.ok(fieldCalls[0].includes('session=srv-1-s1'));
      element('fm-input').value = '7';
      applySessionState(beta1);
      assert.equal(appState.selectedField, null);
      await element('fm-save').listeners.click();
      assert.deepEqual(edits, []);

      // 2. Same-path reopen (new sessionId) closes modal and rejects stale editor submit.
      applySessionState({ ...alpha1, sessionId: 'srv-1-s3', stateSeq: 3 });
      await openFieldEditorByName('HP Current');
      element('fm-input').value = '5';
      applySessionState({ ...alpha1, sessionId: 'srv-1-s4', stateSeq: 4 });
      assert.equal(appState.selectedField, null);
      await element('fm-save').listeners.click();
      assert.deepEqual(edits, []);

      // 3. Delayed lower stateSeq from Alpha must not overwrite newer Beta across paths.
      applySessionState({ ...beta1, stateSeq: 5 });
      assert.equal(applySessionState({ ...alpha1, stateSeq: 1 }), false);
      assert.equal(appState.sheet.path, 'Beta.pdf');
      assert.equal(appState.lastStateSeq, 5);

      // 4. Server restart (new serverInstanceId, reset stateSeq=1) is accepted,
      //    AND delayed snapshots from the retired serverInstanceId are rejected!
      const beta2 = {
        open: true,
        path: 'Beta.pdf',
        serverInstanceId: 'srv-2',
        sessionId: 'srv-2-s1',
        stateSeq: 1,
        revision: 0,
        vitals: { hpCurrent: '20', hpMax: '20' },
      };
      assert.equal(applySessionState(beta2), true);
      assert.equal(appState.lastServerInstanceId, 'srv-2');
      assert.equal(appState.lastStateSeq, 1);
      assert.equal(applySessionState({ ...alpha1, serverInstanceId: 'srv-1', stateSeq: 99 }), false);
      assert.equal(appState.sheet.path, 'Beta.pdf');
      assert.equal(appState.lastServerInstanceId, 'srv-2');
      assert.equal(appState.lastStateSeq, 1);

      // 5. Overlap between pending HTTP refreshSession/openSheet and WebSocket reconnect
      //    to a new server generation (srv-3), plus superseded WebSocket handlers!
      connectWs();
      const wsOld = sockets[sockets.length - 1];
      wsOld.readyState = MockWebSocket.OPEN;
      wsOld.onopen();

      let resolveOldRefresh;
      let resolveOldOpen;
      const srv3Gamma = {
        open: true,
        path: 'Gamma.pdf',
        serverInstanceId: 'srv-3',
        sessionId: 'srv-3-s1',
        stateSeq: 1,
        revision: 1,
        vitals: { hpCurrent: '30', hpMax: '30' },
      };
      let stateCallCount = 0;
      fetchHandler = (path) => {
        if (path === '/api/session/state') {
          stateCallCount += 1;
          if (stateCallCount === 1) {
            return new Promise((r) => { resolveOldRefresh = r; });
          }
          return Promise.resolve(jsonResp(srv3Gamma));
        }
        if (path === '/api/session/open') {
          return new Promise((r) => { resolveOldOpen = r; });
        }
        throw new Error('Unexpected overlap fetch ' + path);
      };

      const pendingRefresh = refreshSession();
      const pendingOpen = openSheet('Alpha.pdf');

      // Reconnect establishes a new WebSocket (wsNew) and fetches srv-3 Gamma first.
      wsOld.readyState = MockWebSocket.CLOSED;
      appState.ws = null;
      connectWs();
      const wsNew = sockets[sockets.length - 1];
      wsNew.readyState = MockWebSocket.OPEN;
      wsNew.onopen();
      await new Promise((r) => setImmediate(r));
      assert.equal(appState.sheet.path, 'Gamma.pdf', 'banner=' + element('banner').textContent);
      assert.equal(appState.lastServerInstanceId, 'srv-3');

      // Now delayed HTTP responses from retired srv-2 arrive AND superseded wsOld fires events!
      resolveOldRefresh(jsonResp({ ...beta2, stateSeq: 40 }));
      resolveOldOpen(jsonResp({ status: 'ok', state: { ...beta2, path: 'Alpha.pdf', stateSeq: 41 } }));
      await pendingRefresh;
      await pendingOpen;
      wsOld.onmessage({ data: JSON.stringify({ type: 'state_updated', state: { ...beta2, stateSeq: 42 } }) });
      wsOld.onmessage({ data: JSON.stringify({ type: 'interaction_requested', interaction: { id: 'old-int', kind: 'alert', request: { cMsg: 'stale' } } }) });
      wsOld.onclose();

      assert.equal(appState.sheet.path, 'Gamma.pdf');
      assert.equal(appState.lastServerInstanceId, 'srv-3');
      assert.equal(appState.activeInteraction, null);
      assert.equal(appState.wsConnected, true);

      // 6. Queued step captured on srv-3-s1 is dropped if sheet switches before execution.
      const targetGamma = currentSessionRef();
      let releaseBlocker;
      const blocker = new Promise((r) => { releaseBlocker = r; });
      enqueueStep(targetGamma, () => blocker);
      const queued = enqueueStep(targetGamma, (ref) => editField('HP Current', '9', 'user', ref));
      applySessionState({ ...srv3Gamma, path: 'Delta.pdf', sessionId: 'srv-3-s2', stateSeq: 2 });
      releaseBlocker();
      await queued;
      assert.deepEqual(edits, []);

      // 7. openSheet and doGitPull carry structured discardTarget through confirmation
      //    and never re-confirm blindly if the server returns discard_target_stale.
      const openBodies = [];
      const pullBodies = [];
      const discardTarget = { sheet: 'Delta.pdf', sessionId: 'srv-3-s2', revision: 7 };
      let openAttempt = 0;
      let pullAttempt = 0;
      let confirms = 0;
      confirmHandler = () => { confirms += 1; return true; };
      fetchHandler = async (path, options) => {
        if (path === '/api/session/open') {
          const body = JSON.parse(options.body);
          openBodies.push(body);
          openAttempt += 1;
          if (openAttempt === 1) {
            return jsonResp({ status: 'conflict', code: 'unsaved_edits', error: 'unsaved', discardTarget }, 409);
          }
          return jsonResp({ status: 'conflict', code: 'discard_target_stale', error: 'stale', discardTarget: { sheet: 'Other.pdf', sessionId: 'srv-3-s9', revision: 2 } }, 409);
        }
        if (path === '/api/git/pull') {
          const body = JSON.parse(options.body);
          pullBodies.push(body);
          pullAttempt += 1;
          if (pullAttempt === 1) {
            return jsonResp({ status: 'conflict', code: 'unsaved_edits', error: 'unsaved', discardTarget }, 409);
          }
          return jsonResp({ status: 'ok', pull: { message: 'ok' }, state: { ...srv3Gamma, stateSeq: 3 } }, 200);
        }
        if (path === '/api/session/state') {
          return jsonResp({ ...srv3Gamma, stateSeq: 3 });
        }
        if (path === '/api/sheets') {
          return jsonResp({ sheets: [], git: { enabled: false } });
        }
        throw new Error('Unexpected discard test fetch ' + path);
      };

      await openSheet('Alpha.pdf');
      assert.equal(confirms, 1, 'stale retry must not loop confirm');
      assert.deepEqual(openBodies, [
        { path: 'Alpha.pdf', force: false },
        { path: 'Alpha.pdf', force: true, discard: discardTarget },
      ]);

      await doGitPull();
      assert.equal(confirms, 2);
      assert.deepEqual(pullBodies, [
        { force: false },
        { force: true, discard: discardTarget },
      ]);

      // 8. Late HTTP 202 must NOT resurrect a dialog already cleared over WebSocket,
      //    duplicate deliveries must preserve in-progress modal input, stale clears must
      //    not close newer dialogs, and a new server generation can reuse int-N IDs.
      let resolveDelayedActivate;
      fetchHandler = (path) => {
        if (path === '/api/session/activate') {
          return new Promise((r) => { resolveDelayedActivate = r; });
        }
        throw new Error('Unexpected interaction test fetch ' + path);
      };
      const alert77 = {
        id: 'int-77',
        serverInstanceId: 'srv-3',
        kind: 'alert',
        request: { cTitle: 'Alert', cMsg: 'Done', nType: 0 },
      };
      const pendingActivate = activateField('TimerButton', 0);
      wsNew.onmessage({ data: JSON.stringify({ type: 'interaction_requested', interaction: alert77 }) });
      assert.equal(appState.activeInteraction.id, 'int-77');
      assert.equal(element('acrobat-modal').classList.contains('hidden'), false);

      // WebSocket clears int-77 before the original HTTP 202 response arrives.
      wsNew.onmessage({ data: JSON.stringify({ type: 'interaction_cleared', id: 'int-77', serverInstanceId: 'srv-3' }) });
      assert.equal(appState.activeInteraction, null);
      assert.equal(element('acrobat-modal').classList.contains('hidden'), true);

      // Delayed HTTP 202 arrives for int-77 -> MUST NOT resurrect the cleared alert!
      resolveDelayedActivate(jsonResp({ status: 'interaction_required', interaction: alert77 }, 202));
      await pendingActivate;
      assert.equal(appState.activeInteraction, null, 'late HTTP 202 must not resurrect cleared alert');
      assert.equal(element('acrobat-modal').classList.contains('hidden'), true);

      // Duplicate delivery for an open dialog must preserve user's in-progress modalValues!
      const dialog78 = {
        id: 'int-78',
        serverInstanceId: 'srv-3',
        kind: 'dialog',
        request: {
          description: { name: 'Edit Hero', elements: [{ type: 'edit_text', item_id: 'hero' }, { type: 'ok_cancel' }] },
          values: { hero: 'Initial' },
        },
      };
      assert.equal(openAcrobatInteraction(dialog78), true);
      appState.modalValues.hero = 'User Typed Draft';
      assert.equal(openAcrobatInteraction(dialog78), true);
      assert.equal(appState.modalValues.hero, 'User Typed Draft', 'duplicate interaction must not reset user input');

      // Opening int-79 retires int-78; a late interaction_cleared for int-78 must NOT close int-79!
      const dialog79 = { ...alert77, id: 'int-79' };
      assert.equal(openAcrobatInteraction(dialog79), true);
      wsNew.onmessage({ data: JSON.stringify({ type: 'interaction_cleared', id: 'int-78', serverInstanceId: 'srv-3' }) });
      assert.equal(appState.activeInteraction.id, 'int-79', 'stale clear for int-78 must not close int-79');
      closeAcrobatModal('int-79', 'srv-3');
      assert.equal(appState.activeInteraction, null);

      // New server generation (srv-4) can cleanly reuse id 'int-77' without false collision,
      // AND a delayed 409 error from srv-3:int-77 must NOT close srv-4:int-77!
      assert.equal(openAcrobatInteraction({ ...alert77, serverInstanceId: 'srv-4' }), true);
      assert.equal(appState.activeInteraction.id, 'int-77');
      assert.equal(appState.activeInteraction.serverInstanceId, 'srv-4');
      closeAcrobatModal('int-77', 'srv-3');
      assert.equal(
        appState.activeInteraction.serverInstanceId,
        'srv-4',
        'closeAcrobatModal must compare full (serverInstanceId, id) identity'
      );

      // In-flight error from srv-4:int-77 after srv-5:int-77 opened must not close srv-5:int-77.
      let rejectSrv4Reply;
      fetchHandler = (path) => {
        if (path.startsWith('/api/session/interaction/')) {
          return new Promise((_, rej) => { rejectSrv4Reply = rej; });
        }
        throw new Error('Unexpected submit test fetch ' + path);
      };
      const pendingReply = submitInteraction({ button: 1, checked: false });
      assert.equal(appState.inFlightInteractionKey, 'srv-4:int-77');
      assert.equal(openAcrobatInteraction({ ...alert77, serverInstanceId: 'srv-5' }), true);
      rejectSrv4Reply(Object.assign(new Error('stale'), { status: 409 }));
      await pendingReply;
      assert.equal(appState.activeInteraction.serverInstanceId, 'srv-5');
      closeAcrobatModal('int-77', 'srv-5');

      // 9. openSheet receiving 409 interaction_required surfaces the active dialog without discard confirm.
      let openInteractionConfirms = 0;
      confirmHandler = () => { openInteractionConfirms += 1; return true; };
      const blockingModal = { ...alert77, id: 'srv-5-int-2', serverInstanceId: 'srv-5' };
      fetchHandler = async (path) => {
        if (path === '/api/session/open') {
          return jsonResp({ status: 'interaction_required', error: 'active dialog', interaction: blockingModal }, 409);
        }
        throw new Error('Unexpected open interaction fetch ' + path);
      };
      await openSheet('Beta.pdf');
      assert.equal(openInteractionConfirms, 0);
      assert.equal(appState.activeInteraction.id, 'srv-5-int-2');
      closeAcrobatModal('srv-5-int-2', 'srv-5');

      // 10. New Character from Template prefers explicit 2024 before v24 fallback,
      //     restores focus on cancel, carries discardTarget on 409, and reaches success state.
      appState.templates = [
        { path: 'templates/MPMB-2014-v24.2.0-Blank.pdf', name: 'MPMB-2014-v24.2.0-Blank.pdf', is_template: true, size_bytes: 100 },
        { path: 'templates/MPMB-2024-Blank.pdf', name: 'MPMB-2024-Blank.pdf', is_template: true, size_bytes: 100 },
      ];
      const openerBtn = element('btn-new-char');
      openerBtn.focus();
      openNewCharModal();
      assert.equal(element('nc-template').value, 'templates/MPMB-2024-Blank.pdf');
      assert.equal(element('new-char-modal').classList.contains('hidden'), false);
      assert.equal(context.document.activeElement, element('nc-name'));
      closeNewCharModal(true);
      assert.equal(element('new-char-modal').classList.contains('hidden'), true);
      assert.equal(context.document.activeElement, openerBtn);

      openNewCharModal();
      const newCalls = [];
      let newConfirms = 0;
      confirmHandler = () => { newConfirms += 1; return true; };
      fetchHandler = async (path, opts) => {
        if (path === '/api/sheets/new') {
          const body = JSON.parse(opts.body);
          newCalls.push(body);
          if (!body.force) {
            return jsonResp({
              status: 'conflict',
              reason: 'unsaved_edits',
              error: 'unsaved edits',
              discardTarget: { sheet: 'Alpha.pdf', sessionId: 'srv-5-s1', revision: 4 },
            }, 409);
          }
          return jsonResp({
            status: 'ok',
            sheet: { path: 'Aelar.pdf', name: 'Aelar.pdf', is_template: false, size_bytes: 100 },
            state: { open: true, serverInstanceId: 'srv-5', sessionId: 'srv-5-s2', stateSeq: 20, path: 'Aelar.pdf', revision: 1, fields: [] },
          });
        }
        if (path === '/api/sheets') {
          return jsonResp({ sheets: appState.templates, templates: appState.templates, characters: [], git: null });
        }
        throw new Error('Unexpected template create fetch ' + path);
      };
      await createCharacterFromTemplate('templates/MPMB-2024-Blank.pdf', 'Aelar');
      assert.equal(newConfirms, 1);
      assert.equal(newCalls.length, 2);
      assert.equal(newCalls[0].force, false);
      assert.equal(newCalls[1].force, true);
      assert.deepEqual(newCalls[1].discard, { sheet: 'Alpha.pdf', sessionId: 'srv-5-s1', revision: 4 });
      assert.equal(element('new-char-modal').classList.contains('hidden'), true);
      assert.equal(element('banner').textContent, 'Created and opened Aelar.pdf');
      assert.equal(element('banner').className, 'banner ok');
      assert.equal(element('tab-play').classList.contains('active'), true);
      assert.equal(context.document.activeElement, element('btn-classes'));

      // 11. When creating a new character while another sheet is already open triggers a startup dialog,
      //     completing the dialog switches from Library to Play for the new session.
      element('tab-play').classList.remove('active');
      element('tab-library').classList.add('active');
      const startupInter = { ...alert77, id: 'srv-5-int-99', serverInstanceId: 'srv-5' };
      fetchHandler = async (path) => {
        if (path === '/api/sheets/new') {
          return jsonResp({ status: 'interaction_required', interaction: startupInter }, 202);
        }
        if (path === '/api/session/interaction/srv-5-int-99') {
          return jsonResp({
            status: 'ok',
            state: { open: true, serverInstanceId: 'srv-5', sessionId: 'srv-5-s3', stateSeq: 21, path: 'Bryn.pdf', revision: 1, fields: [] },
          });
        }
        if (path === '/api/sheets') {
          return jsonResp({ sheets: appState.templates, templates: appState.templates, characters: [], git: null });
        }
        throw new Error('Unexpected startup-dialog create fetch ' + path);
      };
      await createCharacterFromTemplate('templates/MPMB-2024-Blank.pdf', 'Bryn');
      assert.equal(appState.activeInteraction.id, 'srv-5-int-99');
      await submitInteraction({ button: 1, checked: false });
      assert.equal(element('tab-play').classList.contains('active'), true);
      assert.equal(element('banner').textContent, 'Loaded Bryn.pdf');

      // 12. Obsolete New Character submission must NOT close a newer modal draft,
      //     switch tabs behind it, or steal focus away from the newer form.
      element('tab-play').classList.remove('active');
      element('tab-library').classList.add('active');
      openNewCharModal();
      element('nc-name').value = 'FirstDraft';
      let resolveFirstCreate = null;
      fetchHandler = async (path) => {
        if (path === '/api/sheets/new') {
          return new Promise((resolve) => {
            resolveFirstCreate = () => resolve(jsonResp({
              status: 'ok',
              sheet: { path: 'FirstDraft.pdf', name: 'FirstDraft.pdf', is_template: false, size_bytes: 100 },
              state: { open: true, serverInstanceId: 'srv-5', sessionId: 'srv-5-s4', stateSeq: 22, path: 'FirstDraft.pdf', revision: 1, fields: [] },
            }));
          });
        }
        if (path === '/api/sheets') {
          return jsonResp({ sheets: appState.templates, templates: appState.templates, characters: [], git: null });
        }
        throw new Error('Unexpected obsolete-form create fetch ' + path);
      };
      const firstCreatePromise = createCharacterFromTemplate('templates/MPMB-2024-Blank.pdf', 'FirstDraft');
      assert.ok(resolveFirstCreate, 'first create POST should be in flight');
      // User closes the first modal and opens a fresh one to type a second character draft.
      closeNewCharModal(true);
      openNewCharModal();
      element('nc-name').value = 'SecondDraft';
      assert.equal(context.document.activeElement, element('nc-name'));
      resolveFirstCreate();
      await firstCreatePromise;
      assert.equal(
        element('new-char-modal').classList.contains('hidden'),
        false,
        'obsolete create response must not close the newly opened modal',
      );
      assert.equal(element('nc-name').value, 'SecondDraft');
      assert.equal(
        context.document.activeElement,
        element('nc-name'),
        'obsolete create response must not steal focus from the newer creation form',
      );
      assert.equal(
        element('tab-library').classList.contains('active'),
        true,
        'obsolete create response must not switch tabs behind the newer form',
      );
      assert.equal(element('tab-play').classList.contains('active'), false);
      closeNewCharModal(false);

      // 13. If another sheet/session becomes active while refreshLibrary() is pending
      //     after createCharacterFromTemplate, stale completion must NOT reset appState.page,
      //     overwrite the banner, switch tabs, or steal focus.
      element('tab-play').classList.remove('active');
      element('tab-sheet').classList.add('active');
      const keepFocusBtn = element('btn-new-char');
      keepFocusBtn.focus();
      let resolveStaleLib = null;
      fetchHandler = async (path) => {
        if (path === '/api/sheets/new') {
          return jsonResp({
            status: 'ok',
            sheet: { path: 'StaleHero.pdf', name: 'StaleHero.pdf', is_template: false, size_bytes: 100 },
            state: { open: true, serverInstanceId: 'srv-5', sessionId: 'srv-5-s5', stateSeq: 23, path: 'StaleHero.pdf', revision: 1, fields: [] },
          });
        }
        if (path === '/api/sheets') {
          return new Promise((resolve) => {
            resolveStaleLib = () => resolve(jsonResp({
              sheets: appState.templates,
              templates: appState.templates,
              characters: [],
              git: null,
            }));
          });
        }
        throw new Error('Unexpected stale-refresh create fetch ' + path);
      };
      openNewCharModal();
      const staleCreatePromise = createCharacterFromTemplate('templates/MPMB-2024-Blank.pdf', 'StaleHero');
      // Wait a microtask tick for /api/sheets/new -> handleActionResponse -> /api/sheets to start.
      await new Promise((r) => setTimeout(r, 0));
      assert.ok(resolveStaleLib, 'refreshLibrary fetch should be pending');
      // While refreshLibrary is pending, another session becomes active on page 3.
      applySessionState({
        open: true,
        serverInstanceId: 'srv-5',
        sessionId: 'srv-5-s6',
        stateSeq: 24,
        path: 'NewerHero.pdf',
        revision: 2,
        pageCount: 6,
        fields: [],
      });
      appState.page = 3;
      element('banner').textContent = 'Loaded NewerHero.pdf';
      element('banner').className = 'banner ok';
      element('tab-play').classList.remove('active');
      element('tab-sheet').classList.add('active');
      keepFocusBtn.focus();
      resolveStaleLib();
      await staleCreatePromise;
      assert.equal(appState.sheet.path, 'NewerHero.pdf');
      assert.equal(appState.sheet.sessionId, 'srv-5-s6');
      assert.equal(appState.page, 3, 'stale create completion must not reset active page');
      assert.equal(element('banner').textContent, 'Loaded NewerHero.pdf');
      assert.equal(element('tab-sheet').classList.contains('active'), true);
      assert.equal(element('tab-play').classList.contains('active'), false);
      assert.equal(context.document.activeElement, keepFocusBtn);

      // 14. Obsolete New Character submission receiving 409 discardTarget after its form
      //     was dismissed / replaced by a newer draft must NOT prompt to discard edits or retry.
      openNewCharModal();
      element('nc-name').value = 'DismissedHero';
      let resolveDismissed409 = null;
      let dismissedCalls = 0;
      let dismissedConfirms = 0;
      confirmHandler = () => { dismissedConfirms += 1; return true; };
      fetchHandler = async (path) => {
        if (path === '/api/sheets/new') {
          dismissedCalls += 1;
          return new Promise((resolve) => {
            resolveDismissed409 = () => resolve(jsonResp({
              status: 'conflict',
              code: 'unsaved_edits',
              error: 'unsaved edits on NewerHero.pdf',
              discardTarget: { sheet: 'NewerHero.pdf', sessionId: 'srv-5-s6', revision: 2 },
            }, 409));
          });
        }
        throw new Error('Unexpected dismissed-409 fetch ' + path);
      };
      const dismissedPromise = createCharacterFromTemplate('templates/MPMB-2024-Blank.pdf', 'DismissedHero');
      assert.ok(resolveDismissed409, 'dismissed create POST should be in flight');
      closeNewCharModal(true);
      openNewCharModal();
      element('nc-name').value = 'ActiveReplacementDraft';
      resolveDismissed409();
      await dismissedPromise;
      assert.equal(dismissedConfirms, 0, 'obsolete 409 must not open discard confirm prompt');
      assert.equal(dismissedCalls, 1, 'obsolete 409 must not issue a forced retry');
      assert.equal(element('new-char-modal').classList.contains('hidden'), false);
      assert.equal(element('nc-name').value, 'ActiveReplacementDraft');
      assert.equal(context.document.activeElement, element('nc-name'));
      assert.ok(
        element('banner').textContent.includes('out of date'),
        'obsolete 409 should report that the request is out of date',
      );
      closeNewCharModal(false);

      // 15. When submitInteraction() completes a startup dialog into a new session
      //     while a newer New Character form is open, preserve the new form's tab and focus.
      element('tab-play').classList.remove('active');
      element('tab-library').classList.add('active');
      const startupInter2 = { ...alert77, id: 'srv-5-int-150', serverInstanceId: 'srv-5', stateSeq: 25 };
      let resolveInterReply = null;
      fetchHandler = async (path) => {
        if (path === '/api/session/interaction/srv-5-int-150') {
          return new Promise((resolve) => {
            resolveInterReply = () => resolve(jsonResp({
              status: 'ok',
              state: { open: true, serverInstanceId: 'srv-5', sessionId: 'srv-5-s7', stateSeq: 26, path: 'StartupLater.pdf', revision: 1, fields: [] },
            }));
          });
        }
        if (path === '/api/sheets') {
          return jsonResp({ sheets: appState.templates, templates: appState.templates, characters: [], git: null });
        }
        throw new Error('Unexpected startup-focus fetch ' + path);
      };
      openAcrobatInteraction(startupInter2);
      const interSubmitPromise = submitInteraction({ button: 1, checked: false });
      assert.ok(resolveInterReply, 'interaction reply POST should be in flight');
      // User opens a new creation form while the server is finishing the startup reply.
      openNewCharModal();
      element('nc-name').value = 'FreshModalDraft';
      assert.equal(context.document.activeElement, element('nc-name'));
      resolveInterReply();
      await interSubmitPromise;
      assert.equal(appState.sheet.path, 'StartupLater.pdf');
      assert.equal(element('new-char-modal').classList.contains('hidden'), false);
      assert.equal(
        context.document.activeElement,
        element('nc-name'),
        'startup reply must not steal focus from a newer New Character form',
      );
      assert.equal(element('tab-library').classList.contains('active'), true);
      assert.equal(element('tab-play').classList.contains('active'), false);
      closeNewCharModal(false);

      // 16. handlePdfUpload offers overwrite ONLY on already_exists 409, NOT on absent-PDF
      //     sidecar_conflict 409.
      const fakePdf = { arrayBuffer: async () => new Uint8Array([0x25, 0x50, 0x44, 0x46, 0x2d]) };
      let uploadCalls = [];
      let uploadConfirms = 0;
      confirmHandler = () => { uploadConfirms += 1; return true; };
      fetchHandler = async (path) => {
        uploadCalls.push(path);
        if (path.startsWith('/api/sheets/upload?name=RevDouble.pdf&overwrite=false')) {
          return jsonResp({
            error: 'conflict: destination sidecar RevDouble.pdf.state.json belongs to another existing sheet',
            code: 'sidecar_conflict',
          }, 409);
        }
        if (path.startsWith('/api/sheets/upload?name=Existing.pdf&overwrite=false')) {
          return jsonResp({
            error: 'sheet already exists: Existing.pdf (pass overwrite=true to replace)',
            code: 'already_exists',
          }, 409);
        }
        if (path.startsWith('/api/sheets/upload?name=Existing.pdf&overwrite=true')) {
          return jsonResp({ sheet: { path: 'Existing.pdf' } }, 201);
        }
        if (path === '/api/sheets') {
          return jsonResp({ sheets: appState.templates, templates: appState.templates, characters: [], git: null });
        }
        throw new Error('Unexpected upload fetch ' + path);
      };
      await handlePdfUpload(fakePdf, 'RevDouble.pdf', 'RevDouble.pdf');
      assert.equal(uploadConfirms, 0, 'sidecar_conflict 409 must not offer overwrite prompt');
      assert.equal(uploadCalls.length, 1, 'sidecar_conflict 409 must not retry overwrite=true');
      assert.ok(element('banner').textContent.includes('belongs to another existing sheet'));

      uploadCalls = [];
      await handlePdfUpload(fakePdf, 'Existing.pdf', 'Existing.pdf');
      assert.equal(uploadConfirms, 1, 'already_exists 409 must offer overwrite prompt');
      assert.ok(uploadCalls.some((p) => p.includes('overwrite=true')));

      // 17. A late creation/state reply arriving after a newer Acrobat prompt was opened
      //     must NOT dismiss or retire that prompt (both for duplicate stateSeq and when
      //     the late reply has stateSeq < activeInteraction.stateSeq).
      applySessionState({
        open: true,
        serverInstanceId: 'srv-5',
        sessionId: 'srv-5-s8',
        stateSeq: 30,
        path: 'CreatedA.pdf',
        revision: 1,
        fields: [],
      });
      const newerPrompt = { ...alert77, id: 'srv-5-int-200', serverInstanceId: 'srv-5', stateSeq: 31 };
      openAcrobatInteraction(newerPrompt);
      assert.equal(appState.activeInteraction.id, 'srv-5-int-200');
      // 17a: Duplicate HTTP replay of stateSeq 30 with activeInteraction=null must NOT close srv-5-int-200.
      applySessionState({
        open: true,
        serverInstanceId: 'srv-5',
        sessionId: 'srv-5-s8',
        stateSeq: 30,
        path: 'CreatedA.pdf',
        revision: 1,
        fields: [],
      });
      assert.equal(
        appState.activeInteraction && appState.activeInteraction.id,
        'srv-5-int-200',
        'duplicate stateSeq reply must not dismiss newer Acrobat prompt',
      );
      // 17b: Even if stateSeq 30 arrives when lastStateSeq was behind (e.g. missed WS state_updated),
      //      stateSeq 30 < activeInteraction.stateSeq (31) must NOT dismiss srv-5-int-200.
      appState.lastStateSeq = 29;
      applySessionState({
        open: true,
        serverInstanceId: 'srv-5',
        sessionId: 'srv-5-s8',
        stateSeq: 30,
        path: 'CreatedA.pdf',
        revision: 1,
        fields: [],
      });
      assert.equal(
        appState.activeInteraction && appState.activeInteraction.id,
        'srv-5-int-200',
        'earlier-sequenced state reply must not dismiss newer Acrobat prompt',
      );
      // 17c: A genuinely newer state snapshot (stateSeq 32 > 31) with no activeInteraction DOES close it.
      applySessionState({
        open: true,
        serverInstanceId: 'srv-5',
        sessionId: 'srv-5-s8',
        stateSeq: 32,
        path: 'CreatedA.pdf',
        revision: 2,
        fields: [],
      });
      assert.equal(appState.activeInteraction, null);

      // 18: Server restart / instance switch clears old-server prompts even when the new
      // server starts at a lower stateSeq (e.g. srv-5 prompt at 50 -> srv-6 state at 1),
      // while still protecting newer same-server prompts against delayed snapshots.
      openAcrobatInteraction({
        id: 'srv-5-int-50',
        serverInstanceId: 'srv-5',
        stateSeq: 50,
        kind: 'alert',
        request: { cTitle: 'Old Server Prompt', cMsg: 'Before restart' },
      });
      assert.equal(appState.activeInteraction && appState.activeInteraction.id, 'srv-5-int-50');
      assert.equal(
        applySessionState({
          open: true,
          serverInstanceId: 'srv-6',
          sessionId: 'srv-6-s1',
          stateSeq: 1,
          path: 'CreatedA.pdf',
          revision: 1,
          fields: [],
        }),
        true,
      );
      assert.equal(
        appState.activeInteraction,
        null,
        'prompt from retired server instance must be cleared on instance switch',
      );
      assert.equal(
        appState.retiredServerInstanceIds.has('srv-5'),
        true,
        'previous server instance must be marked retired',
      );
      // Delayed busy snapshot from retired server srv-5 must be rejected.
      assert.equal(
        applySessionState({
          open: true,
          busy: true,
          serverInstanceId: 'srv-5',
          stateSeq: 51,
          activeInteraction: {
            id: 'srv-5-int-51',
            serverInstanceId: 'srv-5',
            stateSeq: 51,
            kind: 'alert',
            request: { cTitle: 'Zombie Prompt', cMsg: 'Retired server' },
          },
        }),
        false,
      );
      assert.equal(appState.activeInteraction, null);

      // 19: Delayed busy snapshot on the SAME server instance must never replace or retire
      // a newer displayed Acrobat prompt, while duplicate delivery of the same prompt still works.
      openAcrobatInteraction({
        id: 'srv-6-int-20',
        serverInstanceId: 'srv-6',
        stateSeq: 20,
        kind: 'alert',
        request: { cTitle: 'Prompt B', cMsg: 'Newer active prompt' },
      });
      assert.equal(appState.activeInteraction && appState.activeInteraction.id, 'srv-6-int-20');
      assert.equal(
        applySessionState({
          open: true,
          busy: true,
          serverInstanceId: 'srv-6',
          stateSeq: 10,
          activeInteraction: {
            id: 'srv-6-int-10',
            serverInstanceId: 'srv-6',
            stateSeq: 10,
            kind: 'alert',
            request: { cTitle: 'Prompt A', cMsg: 'Stale busy prompt' },
          },
        }),
        false,
        'delayed busy snapshot older than active prompt must be ignored',
      );
      assert.equal(
        appState.activeInteraction && appState.activeInteraction.id,
        'srv-6-int-20',
        'newer prompt B must remain displayed',
      );
      assert.equal(
        appState.retiredInteractionKeys.has('srv-6:srv-6-int-20'),
        false,
        'newer prompt B must NOT be retired by delayed older busy snapshot',
      );
      // Direct openAcrobatInteraction with older same-server prompt also refuses to replace B.
      assert.equal(
        openAcrobatInteraction({
          id: 'srv-6-int-10',
          serverInstanceId: 'srv-6',
          stateSeq: 10,
          kind: 'alert',
          request: { cTitle: 'Prompt A', cMsg: 'Stale direct prompt' },
        }),
        false,
      );
      assert.equal(appState.activeInteraction && appState.activeInteraction.id, 'srv-6-int-20');
      // Redelivery of prompt B itself (same key) is still accepted cleanly.
      assert.equal(
        applySessionState({
          open: true,
          busy: true,
          serverInstanceId: 'srv-6',
          stateSeq: 20,
          activeInteraction: {
            id: 'srv-6-int-20',
            serverInstanceId: 'srv-6',
            stateSeq: 20,
            kind: 'alert',
            request: { cTitle: 'Prompt B', cMsg: 'Newer active prompt' },
          },
        }),
        true,
      );
      assert.equal(appState.activeInteraction && appState.activeInteraction.id, 'srv-6-int-20');
      // Same-server delayed open snapshot (stateSeq 19 < 20) still keeps prompt B open.
      applySessionState({
        open: true,
        serverInstanceId: 'srv-6',
        sessionId: 'srv-6-s1',
        stateSeq: 19,
        path: 'CreatedA.pdf',
        revision: 2,
        fields: [],
      });
      assert.equal(appState.activeInteraction && appState.activeInteraction.id, 'srv-6-int-20');
      // Same-server genuinely newer open snapshot (stateSeq 21 > 20) closes prompt B.
      applySessionState({
        open: true,
        serverInstanceId: 'srv-6',
        sessionId: 'srv-6-s1',
        stateSeq: 21,
        path: 'CreatedA.pdf',
        revision: 3,
        fields: [],
      });
      assert.equal(appState.activeInteraction, null);

      console.log('PWA_CLIENT_REGRESSIONS_OK');
    })().catch((err) => {
      console.error(err);
      process.exit(1);
    });
    """
)


class PwaClientRegressionTests(unittest.TestCase):
    def test_pwa_js_syntax_and_state_machine_regressions(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node is not installed")
        for script in (APP_JS, SW_JS):
            check = subprocess.run(
                [node, "--check", str(script)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(
                check.returncode,
                0,
                f"node --check failed for {script}: {check.stderr}",
            )
        run = subprocess.run(
            [node, "-e", PWA_HARNESS, str(APP_JS)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(
            run.returncode,
            0,
            f"PWA regression harness failed:\nstdout={run.stdout}\nstderr={run.stderr}",
        )
        self.assertIn("PWA_CLIENT_REGRESSIONS_OK", run.stdout)


if __name__ == "__main__":
    unittest.main()
