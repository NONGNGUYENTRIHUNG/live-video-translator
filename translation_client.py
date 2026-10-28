"""Persistent local translator, cancellable waits and request-ID isolation."""
import json
from pathlib import Path
import queue
import subprocess
import threading
import time

class TranslationCancelled(Exception): pass

class TranslationClient:
    def __init__(self):
        self.process=None; self.responses=queue.Queue(); self.serial=0
        self.lock=threading.Lock(); self.closed=False
    def _start(self):
        if self.closed: raise TranslationCancelled()
        if self.process is not None and self.process.poll() is None: return
        root=Path(__file__).resolve().parent
        python=root/'.venv-translation/Scripts/python.exe'
        if not python.is_file(): raise RuntimeError('Translation setup is missing. Run .\\.venv\\Scripts\\python.exe setup_translation.py first.')
        self.responses=queue.Queue()
        self.process=subprocess.Popen([str(python),'-u',str(root/'translation_worker.py')],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True,encoding='utf-8',bufsize=1)
        process=self.process; replies=self.responses
        def read():
            try:
                for line in process.stdout:
                    try: replies.put(json.loads(line))
                    except json.JSONDecodeError: print('Translation diagnostic:',line.rstrip(),flush=True)
            finally:
                replies.put(dict(kind='fatal',id=0,message='Translation process exited; see terminal.'))
                process.stdout.close()
        threading.Thread(target=read,daemon=True).start()
    def request(self, source,target,text,stop_event,status,prepare=False):
        if source==target: return text,'passthrough'
        with self.lock:
            if stop_event.is_set(): raise TranslationCancelled()
            self._start(); self.serial+=1; ident=self.serial
            self.process.stdin.write(json.dumps(dict(op='prepare' if prepare else 'translate',id=ident,
                source=source,target=target,text=text),ensure_ascii=True)+'\n'); self.process.stdin.flush()
            deadline=time.monotonic()+300
            while time.monotonic()<deadline:
                if stop_event.is_set() or self.closed: raise TranslationCancelled()
                try: response=self.responses.get(timeout=.1)
                except queue.Empty: continue
                if response['kind']=='fatal': raise RuntimeError(response['message'])
                if response['id']!=ident: continue # Canceled session's response cannot leak.
                if response['kind']=='status': status(response['message'])
                elif response['kind']=='error': raise RuntimeError(response['message'])
                elif response['kind']=='result': return response['text'],response['model']
            raise RuntimeError('Translation timed out. Stop and restart the app; inspect terminal details.')
    def close(self):
        self.closed=True
        p=self.process
        if p is not None:
            try: p.terminate()
            except OSError: pass
            def reap():
                try: p.wait(timeout=3)
                except subprocess.TimeoutExpired: p.kill(); p.wait()
                if p.stdin: p.stdin.close()
            threading.Thread(target=reap,daemon=False).start()
