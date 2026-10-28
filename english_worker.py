"""American English Kokoro on CPU. Uses the same local pipe protocol as VieNeu."""
import asyncio
import base64
from pathlib import Path
import queue
import re
import threading
import traceback
import vieneu_worker as ipc

VOICES={'Bella':'af_bella','Michael':'am_michael'}

def phrases(text):
    """Start speaking a clause without waiting for a long subtitle's full synthesis."""
    remaining=text.strip()
    while len(remaining)>160:
        marks=list(re.finditer(r'[,;:!?]|\.(?=\s)',remaining[:160]))
        marks=[m for m in marks if m.end()>=60]
        cut=marks[-1].end() if marks else remaining.rfind(' ',0,160)
        if cut<=0: cut=160
        yield remaining[:cut].strip()
        remaining=remaining[cut:].strip()
    if remaining: yield remaining

def main():
    threading.Thread(target=ipc.reader,daemon=True).start()
    import numpy as np
    import onnxruntime as ort
    from scipy.signal import resample_poly
    from kokoro_onnx import Kokoro
    assets=Path(__file__).resolve().parent/'english_models'
    if not (assets/'kokoro-v1.0.onnx').exists() or not (assets/'voices-v1.0.bin').exists():
        raise RuntimeError('English models missing. Run setup_english.py using your project Python.')
    ipc.send('status',message='Loading local American English voices on CPU...')
    options=ort.SessionOptions(); options.intra_op_num_threads=4; options.inter_op_num_threads=1
    session=ort.InferenceSession(str(assets/'kokoro-v1.0.onnx'),sess_options=options,providers=['CPUExecutionProvider'])
    model=Kokoro.from_session(session,str(assets/'voices-v1.0.bin'))
    if not set(VOICES.values()).issubset(set(model.get_voices())):
        raise RuntimeError('English voice pack lacks Bella or Michael.')
    model.create('Hello, welcome to the voice preview.',voice='af_bella',lang='en-us')
    ipc.send('ready')
    async def speak(cmd):
        for phrase in phrases(cmd['text']):
            if ipc.closed.is_set() or cmd['epoch']!=ipc.state['epoch']: return
            stream=model.create_stream(phrase,voice=VOICES[cmd['voice']],lang='en-us',speed=cmd.get('speed',1.0))
            try:
                async for audio,rate in stream:
                    if ipc.closed.is_set() or cmd['epoch']!=ipc.state['epoch']: return
                    a=np.asarray(audio,dtype=np.float32).reshape(-1)
                    if not np.all(np.isfinite(a)): raise RuntimeError('Non-finite Kokoro audio')
                    if rate!=24000: raise RuntimeError(f'Unexpected Kokoro sample rate: {rate}')
                    a=resample_poly(a,2,1)
                    pcm=(np.clip(a,-1,1)*32767).astype('<i2').tobytes()
                    for offset in range(0,len(pcm),48000):
                        if cmd['epoch']!=ipc.state['epoch']: return
                        ipc.send('audio',epoch=cmd['epoch'],job=cmd['job'],pcm=base64.b64encode(pcm[offset:offset+48000]).decode('ascii'))
            finally: await stream.aclose()
    while not ipc.closed.is_set():
        try: cmd=ipc.jobs.get(timeout=.1)
        except queue.Empty: continue
        if cmd['epoch']!=ipc.state['epoch']: continue
        try:
            asyncio.run(speak(cmd))
            if cmd['epoch']==ipc.state['epoch']: ipc.send('done',epoch=cmd['epoch'],job=cmd['job'])
        except Exception as exc:
            traceback.print_exc(); ipc.send('error',epoch=cmd['epoch'],message=str(exc))

if __name__=='__main__':
    try: main()
    except Exception as exc:
        traceback.print_exc(); ipc.send('fatal',message=str(exc))
