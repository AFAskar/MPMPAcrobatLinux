// Protocol behavior test; real Reader preflight/readiness remain mandatory.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const steps = [], timers = [];
let depth = 0, timerFails = false;
const app = {
  trustedFunction: fn => fn,
  beginPriv() { depth++; },
  endPriv() { depth--; assert.ok(depth >= 0); },
  addMenuItem() {},
  setTimeOut(code, delay) {
    assert.equal(depth, 0);
    if (timerFails) throw Error('Unavailable timer');
    const timer = {code, delay}; timers.push(timer); steps.push('scheduled'); return timer;
  },
  alert(request) {
    steps.push('alert');
    assert.equal(request.cTitle, 'MPMB Automation Result');
    assert.ok(request.cMsg.startsWith('MPMB_RESULT\n'));
    return 1;
  }
};
const ctx = vm.createContext({app});
vm.runInContext(fs.readFileSync(path.join(__dirname, '../windows/mpmb-testing.js'), 'utf8'), ctx);
const bridge = ctx.MPMBTesting;
let calls = 0;
bridge.execute = q => { calls++; steps.push('execute'); return {observed:q.id}; };
bridge.doc = requested => ({getField(name) {assert.equal(requested, '/C/Users/mpmb-test/MPMB-Testing/runs/test.pdf'); assert.equal(name, 'PC Name'); return {setFocus() {assert.equal(steps.at(-1), 'alert'); steps.push('focus');}};}});
function request(id, op='read') {return {id, op, path:'/C/Users/mpmb-test/MPMB-Testing/runs/test.pdf', field:'PC Name', expires:Date.now()+60000};}
function deliver() {const timer=timers.shift(); assert.equal(timer.delay, 0); vm.runInContext(timer.code, ctx);}
bridge.run(request('1'.repeat(32), 'focus'));
assert.deepEqual(steps, ['execute', 'scheduled']);
assert.equal(calls, 1); assert.equal(bridge.busy, true); assert.equal(bridge.resultTimer, timers[0]);
assert.throws(() => bridge.run(request('2'.repeat(32))), /Previous command/);
assert.equal(calls, 1);
deliver();
assert.deepEqual(steps, ['execute', 'scheduled', 'alert', 'focus']);
assert.equal(bridge.busy, false); assert.equal(depth, 0);
bridge.deliverResult(); assert.equal(steps.filter(s => s === 'alert').length, 1);
bridge.execute = () => {throw Error('Observed operation failure');};
bridge.run(request('3'.repeat(32)));
assert.equal(JSON.parse(bridge.pendingResult.encoded).ok, false); deliver();
bridge.execute = () => 'X'.repeat(13000);
bridge.run(request('4'.repeat(32)));
const oversized = JSON.parse(bridge.pendingResult.encoded);
assert.equal(oversized.ok, false); assert.equal(oversized.operation_completed, true); deliver();
// Native Acrobat alert controls double mnemonic ampersands. The encoded
// response must roundtrip even after that display-layer transformation.
const ampersands = {'A&B':'A&B C&&D E&&&F &amp; <x> "quote" \\path \u00a0\u2028\ud83d\ude00'};
bridge.execute = () => ampersands;
bridge.run(request('6'.repeat(32)));
assert.equal(bridge.pendingResult.encoded.includes('&'), false);
assert.deepEqual(JSON.parse(bridge.pendingResult.encoded.replace(/&/g,'&&')).result, ampersands);
deliver();
bridge.execute = () => '&'.repeat(2200);
bridge.run(request('7'.repeat(32)));
assert.equal(JSON.parse(bridge.pendingResult.encoded).operation_completed, true);
assert.equal(JSON.parse(bridge.pendingResult.encoded).ok, false);
deliver();
timerFails = true;
bridge.execute = () => {calls++; return 'retained result';};
const before = calls; bridge.run(request('5'.repeat(32)));
assert.equal(calls, before+1); assert.equal(bridge.busy, false); assert.equal(bridge.pendingResult, null);
assert.equal(depth, 0); assert.equal(timers.length, 0);
console.log('Deferred result delivery, ownership, error/overflow and focus sequencing PASS');
