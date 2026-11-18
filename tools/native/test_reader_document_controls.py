"""Reading-preparation cancellation must never act on another dialog/document."""
import unittest
from reader_document_controls import cancel_reading_preparation


class Surface:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def command(self, action, **arguments):
        self.calls.append((action, arguments))
        if action == 'inspect':
            return self.rows
        raise AssertionError('Unexpected desktop mutation')


class CancellationGuards(unittest.TestCase):
    def rows(self):
        return [dict(handle=10, name='disposable.pdf - Adobe Acrobat Reader (64-bit)', class_='AcrobatSDIWindow'),
                dict(handle=20, name='Preparing document for reading', class_='#32770'),
                dict(handle=21, name='Cancel', class_='Button', owner=20, enabled=True)]

    def reject(self, rows, path='disposable.pdf'):
        rows = [{('class' if k == 'class_' else k):v for k,v in row.items()} for row in rows]
        surface = Surface(rows)
        with self.assertRaises(AssertionError):
            cancel_reading_preparation(surface, path)
        self.assertEqual(surface.calls, [('inspect', {})])

    def test_another_document(self):
        self.reject(self.rows(), 'another.pdf')

    def test_other_dialog(self):
        rows=self.rows();rows[1]['name']='Source selection'
        self.reject(rows)

    def test_other_button_owner(self):
        rows=self.rows();rows[2]['owner']=99
        self.reject(rows)

    def test_ambiguous_cancel(self):
        rows=self.rows();rows.append(dict(rows[2],handle=22))
        self.reject(rows)

    def test_another_modal_present(self):
        rows=self.rows();rows.append(dict(handle=30,class_='AVL_AVDialog',name='Save as'))
        self.reject(rows)


if __name__ == '__main__':
    unittest.main()
