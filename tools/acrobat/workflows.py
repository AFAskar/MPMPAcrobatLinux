#!/usr/bin/env python3
"""Target the Druid wild-shape and spell-dialog workflows before a full suite."""
import json
import time
import control as c
import resources
from wildshape import test as wildshape
from spells import test as spells


def main(rules=None):
    rules=rules or ['2014','2024']
    if any(r not in ['2014','2024'] for r in rules) or len(set(rules))!=len(rules):raise ValueError('Choose each of 2014 and 2024 at most once')
    started=time.time();run_id=str(int(started));cases=[];report=c.STATE/('workflows-'+run_id+'.json')
    result=dict(run_id=run_id,planned_cases=len(rules)*2+1,status='running',passed=False,cases=cases)
    report.write_text(json.dumps(result,indent=2))
    def record(name,fn):
        t=time.monotonic()
        try:detail=fn();passed=True
        except Exception as error:detail=dict(error=str(error));passed=False
        cases.append(dict(name=name,passed=passed,seconds=round(time.monotonic()-t,3),detail=detail))
        result.update(status='running' if passed else 'failed',elapsed_seconds=round(time.time()-started,3))
        report.write_text(json.dumps(result,indent=2));print(name,'PASS' if passed else 'FAIL',flush=True)
        if not passed:raise RuntimeError('Workflow failed; evidence: '+str(report))
    with c.desktop_lock():
        for rule in rules:
            record('druid-'+rule+'-wildshape',lambda r=rule:wildshape(r,run_id))
            record('druid-'+rule+'-spells',lambda r=rule:spells(r,run_id))
        def audit():
            data=resources.snapshot(started)
            assert not data['guest']['reader_events'],data
            assert not data['guest']['resource_exhaustion'],data
            return data
        record('no-reader-crash-or-resource-exhaustion',audit)
        result.update(status='complete',passed=True);report.write_text(json.dumps(result,indent=2));print(report)
if __name__=='__main__':
    import sys
    main(sys.argv[1:])
