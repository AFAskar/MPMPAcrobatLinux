import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('console_observer',Path(__file__).with_name('reader-console.py'))
console=importlib.util.module_from_spec(spec);spec.loader.exec_module(console)

class Controller:
    def __init__(self, replies, change_owner=False):
        self.replies=iter(replies);self.calls=[];self.change_owner=change_owner
    def command(self, action, **kw):
        self.calls.append((action,kw))
        if action=='inspect':
            return [{'handle':1,'class':'#32770','name':'JavaScript Debugger','enabled':True},
                    {'handle':2,'owner':9 if self.change_owner else 1,'class':'RICHEDIT50W','enabled':True,'rect':[0,0,100,40]}]
        if action!='dialog_control':raise AssertionError('Only observation commands may be retried')
        result=next(self.replies)
        if isinstance(result,Exception):raise result
        return {'owner':1,'handle':2,'class':'RICHEDIT50W','text':result}

class ConsoleReadTests(unittest.TestCase):
    def test_transient_getter_failure_is_retained_before_live_success(self):
        c=Controller([RuntimeError('Exception calling ControlText: Control query timed out'),'sentinel\r\n'])
        r=console.read_console_text(1,2,controller=c)
        self.assertEqual(r['live']['text'],'sentinel\r\n')
        self.assertEqual(len(r['read_attempts']),2)
        self.assertIn('timed out',r['read_attempts'][0]['error'])
        self.assertEqual([a for a,k in c.calls],['inspect','dialog_control','inspect','dialog_control'])
    def test_exhausted_getters_fail_with_every_attempt(self):
        c=Controller([RuntimeError('ControlText: Control text read timed out')]*3)
        with self.assertRaises(console.ConsoleReadError) as r:console.read_console_text(1,2,controller=c)
        self.assertEqual(len(r.exception.read_attempts),3)
    def test_other_errors_and_changed_ownership_are_not_retried(self):
        c=Controller([RuntimeError('Unrelated rejected operation')])
        with self.assertRaises(console.ConsoleReadError):console.read_console_text(1,2,controller=c)
        self.assertEqual(len(c.calls),2)
        c=Controller(['cached caption'],change_owner=True)
        with self.assertRaises(console.ConsoleReadError):console.read_console_text(1,2,controller=c)
        self.assertEqual(len(c.calls),1)

if __name__=='__main__':unittest.main()
