"""Editing gestures remain native; spelling opens only by explicit request."""
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from openvoice.ocr_ui import SpellingController


class Clock:
    def __init__(self):
        self.counter=0
        self.idle={}
        self.tk=SimpleNamespace(call=lambda *args: 'x11' if args==('tk','windowingsystem') else len(args[-1]))
    def after(self,*args):
        self.counter+=1
        return self.counter
    def after_idle(self,callback):
        token=self.after()
        self.idle[token]=callback
        return token
    def after_cancel(self,token): self.idle.pop(token,None)
    def flush(self):
        callbacks=list(self.idle.values());self.idle.clear()
        for callback in callbacks: callback()


class Editor:
    def __init__(self,tk):
        self.tk=tk
        self.bindings={}
        self.content='The freind.'
        self.cursor='1.5'
        self.focused=False
    def bind(self,event,callback,add=None): self.bindings[event]=callback
    def tag_configure(self,*args,**kwargs): pass
    def tag_remove(self,*args): pass
    def edit_modified(self,*args): return False
    def offset(self,index):
        if index.startswith('1.0+'):
            return sum(int(part.removesuffix('c')) for part in index[4:].split('+'))
        return int(index.split('.')[1])
    def get(self,start,end):
        return self.content if end=='end-1c' else self.content[:self.offset(end)]
    def index(self,index):
        if index=='insert': return self.cursor
        x,y=map(int,index[1:].split(','))
        return f'1.{min(x//10,len(self.content)-1)}'
    def bbox(self,index): return self.offset(index)*10,0,10,20
    def winfo_exists(self): return True
    def focus_set(self): self.focused=True
    def mark_set(self,name,index): self.cursor=index
    def see(self,index): pass
    def dispatch(self,event,x=52,y=10):
        callback=self.bindings.get(event)
        return callback(SimpleNamespace(x=x,y=y)) if callback else None


class SpellingEditingTests(unittest.TestCase):
    def setUp(self):
        self.root=Clock();self.editor=Editor(self.root.tk)
        self.controller=SpellingController(self.root,self.editor,SimpleNamespace(set=lambda value:None))
        self.controller.snapshot=self.editor.content
        self.issue=SimpleNamespace(start=4,end=10,original='freind',suggestions=['friend'])
        self.controller.issues=[self.issue]
        self.opened=[]
        self.controller.show_issue=lambda index:self.opened.append(index) or 'break'
    def tearDown(self): self.controller.close()

    def test_normal_click_double_click_and_drag_do_not_open_spelling(self):
        for sequence in [('<ButtonPress-1>','<ButtonRelease-1>'),
                         ('<Double-ButtonPress-1>','<ButtonRelease-1>'),
                         ('<ButtonPress-1>','<B1-Motion>','<ButtonRelease-1>')]:
            for event in sequence:
                self.assertIsNone(self.editor.dispatch(event))
            self.root.flush()
        self.assertFalse(self.opened)
        self.assertEqual(self.editor.cursor,'1.5')
        self.assertNotIn('<ButtonRelease-1>',self.editor.bindings)

    def test_right_click_and_control_click_open_suggestions(self):
        self.assertEqual(self.editor.dispatch('<Button-3>'),'break')
        self.assertFalse(self.opened)
        self.root.flush()
        self.assertEqual(self.opened,['1.5'])
        self.editor.dispatch('<Control-ButtonPress-1>')
        self.editor.dispatch('<Control-ButtonRelease-1>')
        self.root.flush()
        self.assertEqual(self.opened,['1.5','1.5'])

    def test_dragging_with_control_does_not_open_a_popup(self):
        self.editor.dispatch('<Control-ButtonPress-1>',x=42)
        self.editor.dispatch('<Control-ButtonRelease-1>',x=82)
        self.root.flush()
        self.assertFalse(self.opened)

    def test_correct_text_blank_space_and_stale_results_do_not_open(self):
        self.assertIsNone(self.editor.dispatch('<Button-3>',x=12))
        self.assertIsNone(self.editor.dispatch('<Button-3>',x=300))
        self.editor.content='New text that is being typed'
        self.assertIsNone(self.editor.dispatch('<Button-3>'))
        self.root.flush()
        self.assertFalse(self.opened)

    def test_keyboard_shortcuts_open_at_caret(self):
        for event in ('<Shift-F10>','<Control-period>','<KeyPress-Menu>'):
            self.assertEqual(self.editor.dispatch(event),'break')
        self.assertEqual(self.opened,['1.5']*3)

    def test_typing_or_an_editing_click_cancels_a_pending_popup(self):
        self.editor.dispatch('<Button-3>')
        self.editor.dispatch('<ButtonPress-1>')
        self.root.flush()
        self.assertFalse(self.opened)
        self.editor.dispatch('<Button-3>')
        self.controller._modified = SpellingController._modified.__get__(self.controller)
        self.editor.edit_modified=lambda value=None: value is None
        self.controller._modified()
        self.root.flush()
        self.assertFalse(self.opened)

    def test_correction_and_close_restore_editor_focus(self):
        def replace(editor,replacement,start,end):
            editor.content=editor.content[:editor.offset(start)]+replacement+editor.content[editor.offset(end):]
        with patch('openvoice.ocr_ui.replace_text',side_effect=replace):
            self.controller.replace_issue(self.issue,'friend')
        self.assertEqual(self.editor.content,'The friend.')
        self.assertEqual(self.editor.offset(self.editor.cursor),10)
        self.assertTrue(self.editor.focused)
        self.editor.focused=False
        popup=SimpleNamespace(destroy=lambda:None)
        self.controller.popup=popup
        self.assertEqual(self.controller.dismiss_popup(),'break')
        self.assertTrue(self.editor.focused)


if __name__=='__main__': unittest.main()
