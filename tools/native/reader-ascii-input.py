"""Verified literal typing in a named Acrobat field, without clipboard mutation.

This is a committed-field control, not a claim of per-keystroke native parity.
All caller text is escaped for SendKeys; the original field actions run and the
committed target value is independently read after document readiness.
"""
def commit(c,path,field,value,*,cycle_focus=False):
    assert isinstance(value,str) and all(32 <= ord(ch) < 127 for ch in value), 'This control is ASCII only'
    escaped=''.join('{'+ch+'}' if ch in '+^%~(){}[]' else ch for ch in value)
    focused=c.script('focus',path=path,field=field)
    cycle=c.command('keys',keys='{TAB}+{TAB}') if cycle_focus else None
    observed=c.command('inspect_focused')
    assert observed.get('in_reader') and observed.get('foreground_class')=='AcrobatSDIWindow' and observed.get('type') in ('ControlType.Edit','ControlType.ComboBox','ControlType.Pane'), ('Requested PDF edit is not the observed editable control',field,observed)
    keys='^a'+(escaped if value else '{BACKSPACE}')
    sent=c.command('keys',keys=keys)
    pending=c.command('inspect_focused')
    assert pending.get('in_reader') and pending.get('foreground_class')=='AcrobatSDIWindow', ('Reader edit lost ownership before commit',pending)
    committed=c.command('keys',keys='{TAB}')
    actual=c.script('read',path=path,fields=[field])['fields'][field]
    result={'focus':focused,'keyboard_focus_cycle':cycle,'observed_focus':observed,'keys':sent,'pending_focus':pending,'commit':committed,'value':actual,'verified':actual==value,'verification':'Named-field focus, optional forward/back keyboard focus, separate literal typing and commit, observed Reader ownership and exact target-field read'}
    assert actual==value,('Named field typing did not commit the requested value',field,value,result)
    return result
