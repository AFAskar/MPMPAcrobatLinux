"""Verified literal typing in a named Acrobat field, without clipboard mutation.

This is a committed-field control, not a claim of per-keystroke native parity.
All caller text is escaped for SendKeys; the original field actions run and the
committed target value is independently read after document readiness.
"""
class FocusObservationError(RuntimeError):
    def __init__(self, message, attempts):
        self.observation_attempts = attempts
        super().__init__(message)


def observe_focus(c, max_attempts=3):
    """Retry only the timed-out read-only UIA worker, preserving failed reads."""
    if not 1 <= max_attempts <= 3:
        raise ValueError('One to three focused observations required')
    attempts = []
    for index in range(max_attempts):
        try:
            value = c.command('inspect_focused')
        except RuntimeError as error:
            attempt = {'attempt': index + 1, 'error': str(error)}
            attempts.append(attempt)
            if 'UI Automation child timed out after 15 seconds; desktop worker remains available' not in str(error):
                raise FocusObservationError(str(error), attempts) from error
            health = c.command('health')
            attempt['health'] = health
            reader_ids = [r['Id'] for r in health.get('readers', [])]
            if index + 1 == max_attempts or health.get('foreground_pid') not in reader_ids:
                raise FocusObservationError(str(error), attempts) from error
            continue
        attempts.append({'attempt': index + 1, 'succeeded': True})
        value = dict(value)
        value['observation_attempts'] = attempts
        return value
    raise AssertionError('Unreachable focused observation state')


def commit(c,path,field,value,*,cycle_focus=False):
    assert isinstance(value,str) and all(32 <= ord(ch) < 127 for ch in value), 'This control is ASCII only'
    escaped=''.join('{'+ch+'}' if ch in '+^%~(){}[]' else ch for ch in value)
    focused=c.script('focus',path=path,field=field)
    cycle=c.command('keys',keys='{TAB}+{TAB}') if cycle_focus else None
    observed=observe_focus(c)
    # Reader can expose the active PDF text caret only as its AVPageView
    # Document provider. The view role alone cannot identify the focused field;
    # the independent exact field read after the actual Tab commit is required.
    page_view=(observed.get('type')=='ControlType.Document' and observed.get('class')=='AVL_AVView' and observed.get('name')=='AVPageView' and observed.get('native_window_handle',0) and len(observed.get('rect',[]))==4 and observed['rect'][2]>0 and observed['rect'][3]>0)
    assert observed.get('in_reader') and observed.get('foreground_class')=='AcrobatSDIWindow' and (observed.get('type') in ('ControlType.Edit','ControlType.ComboBox','ControlType.Pane') or page_view), ('Requested PDF edit is not the observed editable control',field,observed)
    keys='^a'+(escaped if value else '{BACKSPACE}')
    sent=c.command('keys',keys=keys)
    pending=observe_focus(c)
    assert pending.get('in_reader') and pending.get('foreground_class')=='AcrobatSDIWindow', ('Reader edit lost ownership before commit',pending)
    committed=c.command('keys',keys='{TAB}')
    actual=c.script('read',path=path,fields=[field])['fields'][field]
    result={'focus':focused,'keyboard_focus_cycle':cycle,'observed_focus':observed,'keys':sent,'pending_focus':pending,'commit':committed,'value':actual,'verified':actual==value,'verification':'Named-field focus, optional forward/back keyboard focus, separate literal typing and commit, observed Reader ownership and exact target-field read'}
    assert actual==value,('Named field typing did not commit the requested value',field,value,result)
    return result
