"""Local VieNeu bridge. Synthesis in isolated Python; playback in capture-excluded parent."""
import base64
from collections import deque
import json
import os
from pathlib import Path
import subprocess
import threading
import time

RATE = 48000

class PCMBuffer:
    def __init__(self):
        self.data = bytearray()
        self.ready = False
        self.finished = True
        self.stalls = 0
    def clear(self):
        self.data.clear(); self.ready=False; self.finished=True
    def push(self, pcm):
        if len(self.data)+len(pcm) > RATE*2*10:
            raise RuntimeError('Voice audio is over 10 seconds behind. Voice stopped; subtitles continue.')
        self.data.extend(pcm)
    def take(self, frames):
        size=frames*2
        if not self.ready:
            if len(self.data)>=int(RATE*2*.24) or (self.finished and self.data): self.ready=True
            else: return bytes(size)
        n=min(size,len(self.data))//2*2
        result=bytes(self.data[:n]); del self.data[:n]
        if n<size:
            if not self.finished: self.stalls+=1
            self.ready=False
        return result+bytes(size-n)

class EngineOutput:
    def __init__(self, report):
        self.report=report
        self.lock=threading.RLock()
        self.write_lock=threading.Lock()
        self.epoch=0
        self.enabled=False
        self.closed=False
        self.language='Vietnamese'
        self.voice='Mai Anh'
        self.volume=.85
        self.process=None
        self.stream=None
        self.buffer=PCMBuffer()
        self.pending={}
        self.job=0
        self.ready=False
        self.starts=deque()
        self.underflows=0

    def _send(self, command):
        p=self.process
        if p is None or p.poll() is not None: return
        with self.write_lock:
            p.stdin.write(json.dumps(command,ensure_ascii=True)+'\n'); p.stdin.flush()

    def _python(self):
        if self.language == 'English':
            path=Path(__file__).resolve().parent/'.venv-english/Scripts/python.exe'
            if not path.is_file(): raise RuntimeError('English voices need setup: run .\\.venv\\Scripts\\python.exe setup_english.py')
            return path
        configured=os.environ.get('VIENEU_PYTHON')
        path=Path(configured) if configured else Path.home()/'Downloads/vieneu-voice-test/.venv/Scripts/python.exe'
        if not path.is_file():
            raise RuntimeError('VieNeu Python not found. Set VIENEU_PYTHON to the python.exe inside your successful voice-test .venv. See README.md.')
        return path

    def _start(self):
        if self.process is not None and self.process.poll() is None: return
        python=self._python()
        env=os.environ.copy(); env['PYTHONIOENCODING']='utf-8'; env['PYTHONUTF8']='1'
        self.ready=False
        self.process=subprocess.Popen([str(python),'-u',str(Path(__file__).with_name('english_worker.py' if self.language=='English' else 'vieneu_worker.py'))],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=None,text=True,encoding='utf-8',
            bufsize=1,env=env)
        p=self.process
        # Align worker before any jobs, including after restarting it.
        self._send({'op':'cancel','epoch':self.epoch})
        threading.Thread(target=self._read,args=(p,),daemon=True).start()
        self.report('Loading local voices. Wait for the preview before starting your video.')

    def _player(self):
        if self.stream is not None: return
        import numpy as np
        import sounddevice as sd
        def callback(out, frames, timing, status):
            with self.lock:
                if status.output_underflow: self.underflows+=1
                pcm=self.buffer.take(frames) if self.enabled else bytes(frames*2)
                gain=self.volume
            a=np.frombuffer(pcm,dtype='<i2').astype(np.float32)*(gain/32768)
            out[:,0]=a; out[:,1]=a
        self.stream=sd.OutputStream(samplerate=RATE,channels=2,dtype='float32',blocksize=960,
                                    latency=.06,callback=callback)
        self.stream.start()

    def configure(self, enabled, language, gender, volume, rate=0):
        with self.lock:
            if (language,gender)!=(self.language,self.voice) or not enabled: self.cancel()
            if language != self.language:
                old=self.process; self.process=None; self.ready=False
                if old is not None and old.poll() is None:
                    old.terminate()
                    threading.Thread(target=old.wait,daemon=True).start()
            self.language,self.voice=language,gender
            self.volume=max(0,min(1,float(volume)/100))
            self.enabled=bool(enabled)


    def cancel(self):
        with self.lock:
            self.epoch+=1
            self.pending.clear(); self.buffer.clear()
            try: self._send({'op':'cancel','epoch':self.epoch})
            except (OSError,ValueError): pass

    def fail(self, message):
        with self.lock:
            self.enabled=False; self.cancel()
        self.report('Voice stopped: '+message,True)

    def submit(self, text):
        if not text.strip(): return
        try:
            with self.lock:
                if not self.enabled or self.closed: return
                if len(self.pending)>=16: raise RuntimeError('Speech cannot keep up. Subtitles continue; turn voice on to retry.')
                allowed=('Mai Anh','Hải Đăng') if self.language=='Vietnamese' else ('Bella','Michael')
                if self.voice not in allowed: raise ValueError('Choose a voice for the selected language.')
                self._start()
                self.job+=1
                self.pending[self.job]={'created':time.monotonic(),'first':True,'queued_before_ready':not self.ready}
                self.buffer.finished=False
                wait=max((time.monotonic()-v['created'] for v in self.pending.values()),default=0)
                speed=1.12 if self.language=='English' and wait>3 else 1.0
                self._send({'op':'speak','epoch':self.epoch,'job':self.job,'text':text,'voice':self.voice,'speed':speed})
        except Exception as exc: self.fail(str(exc))

    def _audio(self, p, msg):
        pcm=base64.b64decode(msg['pcm'],validate=True)
        if len(pcm)%2: raise ValueError('Incomplete PCM sample')
        for offset in range(0,len(pcm),RATE): # <= 0.5 seconds per queued block
            while True:
                with self.lock:
                    if self.closed or p is not self.process or msg['epoch']!=self.epoch or not self.enabled: return
                    item=self.pending.get(msg['job'])
                    if item is None: return
                    if item['first']:
                        age=time.monotonic()-item['created']

                        item['first']=False
                        label='Load/generation/queue wait' if item['queued_before_ready'] else 'Generation/queue wait'
                        self.report(f'{self.voice} | {label}: {age:.2f}s | Buffered audio: {len(self.buffer.data)/(RATE*2):.1f}s')
                    if len(self.buffer.data)<RATE*2*2:
                        self.buffer.push(pcm[offset:offset+RATE])
                        self._player()
                        break
                # Backpressure: faster synthesis waits instead of overflowing or dropping speech.
                time.sleep(.02)

    def _read(self,p):
        try:
            for line in p.stdout:
                try: msg=json.loads(line)
                except json.JSONDecodeError:
                    print('Voice diagnostic:',line.rstrip(),flush=True); continue
                if msg['kind']=='audio':
                    self._audio(p,msg)
                    continue
                with self.lock:
                    if self.closed or p is not self.process: return
                    kind=msg['kind']
                    if kind=='fatal': raise RuntimeError(msg['message'])
                    if kind=='status': self.report(msg['message']); continue
                    if kind=='ready': self.ready=True; self.report('Local voice engine ready.'); continue
                    if msg.get('epoch')!=self.epoch or not self.enabled: continue
                    if kind=='error': raise RuntimeError(msg['message'])
                    if kind=='done' and msg.get('job') in self.pending:
                        del self.pending[msg['job']]
                        if not self.pending: self.buffer.finished=True
                        print(f'Voice playback: starvation events={self.buffer.stalls}, device underflows={self.underflows}',flush=True)
            if not self.closed and p is self.process: raise RuntimeError('Voice worker exited. See terminal details; switch voice off/on and try Test voice.')
        except Exception as exc:
            if not self.closed and p is self.process:
                self.fail(str(exc))
                with self.lock:
                    if p is self.process: self.process=None
                if p.poll() is None: p.terminate()
                p.wait(timeout=5)
        finally:
            if p.stdout: p.stdout.close()

    def close(self):
        with self.lock:
            self.closed=True; self.enabled=False; self.cancel()
            p=self.process
            try: self._send({'op':'close'})
            except (OSError,ValueError): pass
        if self.stream is not None:
            self.stream.abort(); self.stream.close()
        if p is not None:
            # Bounded asynchronous cleanup, including interrupted model downloads.
            def reap():
                try: p.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    p.terminate()
                    try: p.wait(timeout=2)
                    except subprocess.TimeoutExpired: p.kill(); p.wait()
                if p.stdin: p.stdin.close()
            threading.Thread(target=reap,daemon=False).start()


class VoiceOutput:
    """Keep one warm engine for each language; only the selected one speaks."""
    def __init__(self, report):
        self.report=report
        self.language='Vietnamese'
        self.closed=False
        self.states={'Vietnamese':'loading','English':'loading'}
        self.engines={}
        for language,voice in [('Vietnamese','Mai Anh'),('English','Bella')]:
            engine=EngineOutput(lambda text,failed=False,lang=language:self._status(lang,text,failed))
            engine.language=language; engine.voice=voice
            self.engines[language]=engine
        for language in self.engines:
            threading.Thread(target=self._prepare,args=(language,),daemon=True).start()

    def _status(self, language, text, failed=False):
        if self.closed: return
        if failed: self.states[language]='unavailable'
        elif self.engines[language].ready: self.states[language]='ready'
        if failed and language!=self.language:
            self.report(f'{language} voice unavailable; see terminal. Other language remains usable.')
            print(text,flush=True)
        elif language==self.language:
            self.report(text,failed)
        elif self.states[language]=='ready':
            self.report(self.status())

    def status(self):
        return ' | '.join(f'{lang}: {state}' for lang,state in self.states.items())

    def _prepare(self, language):
        engine=self.engines[language]
        try:
            with engine.lock:
                if self.closed: return
                engine._start()
        except Exception as exc:
            self.states[language]='unavailable'
            print(f'{language} preload: {exc}',flush=True)
            self.report(self.status()+'. Click Test voice for details.')

    def configure(self, enabled, language, gender, volume, rate=0):
        if language!=self.language:
            old=self.engines[self.language]
            old.configure(False,old.language,old.voice,old.volume*100)
            self.language=language
        engine=self.engines[language]
        engine.configure(enabled,language,gender,volume,rate)
        self.report(self.status())

    def submit(self,text): self.engines[self.language].submit(text)
    def cancel(self):
        for engine in self.engines.values(): engine.cancel()
    def close(self):
        self.closed=True
        for engine in self.engines.values(): engine.close()
