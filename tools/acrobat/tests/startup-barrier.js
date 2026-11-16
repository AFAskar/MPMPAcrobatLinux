// Protocol controls only; completed real Reader readiness remains required.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const timers = [];
const app = {
  trustedFunction: fn => fn, beginPriv() {}, endPriv() {}, addMenuItem() {},
  calculate: true, activeDocs: [],
  setTimeOut(code, delay) { const timer = {code, delay}; timers.push(timer); return timer; }
};
const ctx = vm.createContext({app});
vm.runInContext(fs.readFileSync(path.join(__dirname, '../windows/mpmb-testing.js'), 'utf8'), ctx);
const bridge = ctx.MPMBTesting;
function doc(name) {
  return {path:bridge.root+'runs/'+name+'.pdf', numPages:6, calculate:true, delay:false,
          InitializeEverything() {}, CalcMod() {}, OpeningStatement() {}};
}
let target = doc('first');
bridge.doc = () => target;
function observe() {return bridge.execute({op:'functions',path:target.path,session:bridge.session,names:['InitializeEverything','CalcMod']});}
assert.equal(observe().startup.invocations, 0);
assert.equal(observe().startup.invocations, 0);
assert.equal(timers.length, 1);
assert.equal(target.__MPMBTestingStartupTimer, timers[0]);
assert.equal(timers[0].delay, 3100);
// Calculation is already enabled, but no readiness claim before the callback.
ctx.tDoc = target;
vm.runInContext(timers[0].code, ctx);
assert.equal(observe().startup.invocations, 1);
assert.equal(timers.length, 1);
const first = target;
target = doc('second');
assert.equal(observe().startup.invocations, 0);
assert.equal(timers.length, 2);
assert.notEqual(target.__MPMBTestingStartupTimer, first.__MPMBTestingStartupTimer);
ctx.tDoc = target;
vm.runInContext(timers[1].code, ctx);
assert.equal(observe().startup.invocations, 1);
assert.equal(first.__MPMBTestingStartupCount, 1);
console.log('Per-document retained startup barrier and actual invocation controls PASS');
