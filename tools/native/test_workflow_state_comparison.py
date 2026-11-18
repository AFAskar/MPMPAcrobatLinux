import unittest
from workflow_state_comparison import encoded_state, compare


class StrictStates(unittest.TestCase):
    def test_boolean_is_not_number(self):
        for a,b in [(False,0),(True,1)]:
            self.assertNotEqual(encoded_state({'nested':[a]}),encoded_state({'nested':[b]}))

    def test_strings_remain_exact(self):
        self.assertNotEqual(encoded_state({'x':'a\u00a0b'}),encoded_state({'x':'a b'}))

    def test_only_object_order_ignored(self):
        self.assertEqual(encoded_state({'a':1,'b':[False,0]}),encoded_state({'b':[False,0],'a':1}))
        self.assertNotEqual(encoded_state({'a':[False,0]}),encoded_state({'a':[0,False]}))

    def test_captured_case_order_required(self):
        report=lambda labels:dict(passed=True,phases=[dict(label=k,state={}) for k in labels])
        with self.assertRaises(AssertionError):compare(report(['a','b']),report(['b','a']))

    def test_incomplete_report_rejected(self):
        report=dict(passed=False,phases=[dict(label='a',state={})])
        with self.assertRaises(AssertionError):compare(report,dict(report,passed=True))


if __name__=='__main__':unittest.main()
