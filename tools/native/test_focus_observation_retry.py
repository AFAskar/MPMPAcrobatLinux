import importlib.util
from pathlib import Path
import unittest
spec=importlib.util.spec_from_file_location('typing_control',Path(__file__).with_name('reader-ascii-input.py'))
typing=importlib.util.module_from_spec(spec);spec.loader.exec_module(typing)
ERROR='UI Automation child timed out after 15 seconds; desktop worker remains available'
class Controller:
    def __init__(self, outcomes, owned=True):self.outcomes=iter(outcomes);self.calls=[];self.owned=owned
    def command(self, action, **kw):
        self.calls.append((action,kw))
        if action=='health':return {'foreground_pid':7 if self.owned else 99,'readers':[{'Id':7}]}
        if action=='inspect_focused':
            result=next(self.outcomes)
            if isinstance(result,Exception):raise result
            if result is False:raise RuntimeError(ERROR)
            return {'in_reader':True,'foreground_class':'AcrobatSDIWindow','type':'ControlType.Edit'}
        if action=='keys':return {'sent':kw['keys']}
        raise AssertionError(action)
    def script(self, action, **kw):
        self.calls.append((action,kw))
        if action=='focus':return {'field':kw['field']}
        if action=='read':return {'fields':{kw['fields'][0]:'20'}}
        raise AssertionError(action)
class FocusTests(unittest.TestCase):
    def test_reads_before_and_after_typing_retry_without_replaying_input(self):
        c=Controller([False,True,False,True]);r=typing.commit(c,'runs/copy.pdf','Cha','20')
        self.assertTrue(r['verified'])
        self.assertEqual([v['keys'] for a,v in c.calls if a=='keys'],['^a20','{TAB}'])
        self.assertEqual(sum(a=='focus' for a,v in c.calls),1)
        self.assertEqual(len(r['observed_focus']['observation_attempts']),2)
        self.assertEqual(len(r['pending_focus']['observation_attempts']),2)
    def test_exhaustion_retains_attempts_and_sends_no_keys(self):
        c=Controller([False]*3)
        with self.assertRaises(typing.FocusObservationError) as e:typing.commit(c,'runs/copy.pdf','Cha','20')
        self.assertEqual(len(e.exception.observation_attempts),3)
        self.assertFalse(any(a=='keys' for a,v in c.calls))
    def test_unrelated_provider_error_is_not_retried(self):
        c=Controller([RuntimeError('No focused UI Automation element')])
        with self.assertRaises(typing.FocusObservationError):typing.commit(c,'runs/copy.pdf','Cha','20')
        self.assertEqual(sum(a=='inspect_focused' for a,v in c.calls),1)
        self.assertFalse(any(a=='keys' for a,v in c.calls))
    def test_foreground_loss_stops_without_retry_or_input(self):
        c=Controller([False,True],owned=False)
        with self.assertRaises(typing.FocusObservationError):typing.commit(c,'runs/copy.pdf','Cha','20')
        self.assertEqual(sum(a=='inspect_focused' for a,v in c.calls),1)
        self.assertFalse(any(a=='keys' for a,v in c.calls))
if __name__=='__main__':unittest.main()
