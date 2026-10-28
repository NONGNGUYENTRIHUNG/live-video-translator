import base64
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import patch
from voice_output import EngineOutput,VoiceOutput

class Tests(unittest.TestCase):
    def test_old_job_is_not_rejected_after_ten_seconds(self):
        reports=[]; e=EngineOutput(lambda *a: reports.append(a)); e.enabled=True
        e.process=object(); e._player=lambda:None
        e.pending[1]={'created':time.monotonic()-12,'first':True,'queued_before_ready':False}
        e._audio(e.process,{'epoch':e.epoch,'job':1,'pcm':base64.b64encode(bytes(960)).decode()})
        self.assertEqual(len(e.buffer.data),960); self.assertTrue(e.enabled)
        self.assertTrue(reports)
    def test_stale_chunks_ignored(self):
        e=EngineOutput(lambda *a:None); e.enabled=True; e.process=object(); e._player=lambda:None
        e.pending[1]={'created':time.monotonic(),'first':True,'queued_before_ready':False}
        e._audio(e.process,{'epoch':e.epoch-1,'job':1,'pcm':base64.b64encode(bytes(960)).decode()})
        self.assertFalse(e.buffer.data)
    @patch('voice_output.threading.Thread.start')
    def test_language_switch_keeps_both_engines(self,_):
        v=VoiceOutput(lambda *a:None)
        vi=v.engines['Vietnamese']; en=v.engines['English']
        vi.ready=en.ready=True
        v.configure(True,'English','Bella',85)
        v.configure(True,'Vietnamese','Mai Anh',85)
        self.assertIs(v.engines['English'],en); self.assertTrue(en.ready)
        self.assertIs(v.engines['Vietnamese'],vi); self.assertTrue(vi.ready)
        self.assertFalse(en.enabled); self.assertTrue(vi.enabled)
        v.close()
    @patch('voice_output.threading.Thread.start')
    def test_selected_engine_only_receives_text(self,_):
        v=VoiceOutput(lambda *a:None)
        with patch.object(v.engines['English'],'submit') as en, patch.object(v.engines['Vietnamese'],'submit') as vi:
            v.configure(True,'English','Michael',85); v.submit('Hello')
            en.assert_called_once_with('Hello'); vi.assert_not_called()
        v.close()

if __name__=='__main__': unittest.main()
