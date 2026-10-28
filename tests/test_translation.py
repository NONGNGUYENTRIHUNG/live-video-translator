import unittest
import sys
import types
import threading
from unittest.mock import Mock, patch
from session_state import SessionState
from translation_models import route, split_to_fit, MODEL_ID
from translation_client import TranslationClient, TranslationCancelled

class UpdateTests(unittest.TestCase):
    def test_stopped_and_previous_sessions_cannot_deliver(self):
        s=SessionState(); first=s.start()
        self.assertTrue(s.accepts(first,'subtitle'))
        s.stop()
        self.assertFalse(s.accepts(first,'subtitle'))
        self.assertTrue(s.accepts(first,'done'))
        second=s.start()
        for kind in ('subtitle','source_text','status','error','done'):
            self.assertFalse(s.accepts(first,kind))
        self.assertTrue(s.accepts(second,'subtitle'))
    def test_multilingual_routing(self):
        for language in ('vi','es','ja','fr','ar','de','ko','hi'):
            self.assertEqual(route(language,'en'),MODEL_ID)
        self.assertIsNone(route('vi','vi'))
    def test_long_input_not_truncated(self):
        tokenizer=types.SimpleNamespace(encode=lambda text,**kw:list(text))
        text=' '.join(['A complete sentence.']*70)
        parts=split_to_fit(text,tokenizer,100)
        self.assertEqual(' '.join(parts),text)
        self.assertTrue(all(len(part)<=100 for part in parts))
    def test_cancelled_translation_does_not_start_process(self):
        client=TranslationClient(); stop=threading.Event(); stop.set()
        with self.assertRaises(TranslationCancelled):
            client.request('ja','en','test',stop,lambda _:None)
        self.assertIsNone(client.process)
    def test_start_clears_display_and_voice(self):
        with patch.dict(sys.modules,{'voice_output':types.SimpleNamespace(VoiceOutput=Mock())}):
            import app
        obj=app.TranslatorApp.__new__(app.TranslatorApp)
        obj.running=False; obj.sessions=SessionState(); obj.voice=Mock()
        obj.subtitle=Mock(); obj.original=Mock(); obj.history=Mock(); obj.sync_voice=Mock()
        for name in ('choice','source_choice','model_choice','start_button','stop_button','status','language','source','quality','save_log'):
            setattr(obj,name,Mock())
        with patch.object(app.threading,'Thread'):
            obj.start()
        obj.history.delete.assert_called_once_with('1.0','end')
        obj.original.set.assert_called_once_with('Recognized speech will appear here.')
        obj.voice.cancel.assert_called_once()
        self.assertEqual(obj.sessions.generation,1)
        obj.stop()
        self.assertTrue(obj.stop_event.is_set())
        self.assertFalse(obj.sessions.accepts(1,'subtitle'))

if __name__=='__main__': unittest.main()
