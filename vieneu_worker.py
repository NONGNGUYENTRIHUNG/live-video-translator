"""Isolated inference process; PCM is returned to the parent, never played here."""
import sys
import json
import queue
import threading
import base64
import traceback

# Reserve stdout for the protocol, redirect Python library diagnostics to stderr.
wire = sys.stdout
sys.stdout = sys.stderr
state = {'epoch': 0}
closed = threading.Event()
jobs = queue.Queue(maxsize=16)

def send(kind, **fields):
    wire.write(json.dumps(dict(kind=kind, **fields), ensure_ascii=True) + '\n')
    wire.flush()

def reader():
    try:
        for line in sys.stdin:
            cmd = json.loads(line)
            if cmd['op'] == 'close': break
            if cmd['op'] == 'cancel':
                state['epoch'] = cmd['epoch']
                while True:
                    try: jobs.get_nowait()
                    except queue.Empty: break
            elif cmd['op'] == 'speak':
                try: jobs.put_nowait(cmd)
                except queue.Full: send('error', epoch=cmd['epoch'], message='Voice queue is full.')
    finally:
        closed.set()


def main():
    threading.Thread(target=reader, daemon=True).start()
    import numpy as np
    import torch
    from vieneu import Vieneu
    if not torch.cuda.is_available():
        raise RuntimeError('VieNeu worker cannot see CUDA. Use the Python environment from your successful voice test.')
    send('status', message='Loading local VieNeu on ' + torch.cuda.get_device_name(0))
    model = Vieneu(mode='v3turbo', backend='pytorch', precision='fp32', max_streams=1)
    for _ in model.infer_stream('Xin chào.', voice='Mai Anh'):
        if closed.is_set(): return
    send('ready')
    while not closed.is_set():
        try: cmd=jobs.get(timeout=.1)
        except queue.Empty: continue
        epoch=cmd['epoch']
        if epoch != state['epoch']: continue
        iterator = None
        try:
            iterator = model.infer_stream(cmd['text'], voice=cmd['voice'])
            for chunk in iterator:
                if closed.is_set() or epoch != state['epoch']: break
                a=np.asarray(chunk, dtype=np.float32).reshape(-1)
                if not np.all(np.isfinite(a)): raise RuntimeError('Non-finite speech samples')
                pcm=(np.clip(a,-1,1)*32767).astype('<i2').tobytes()
                if pcm: send('audio', epoch=epoch, job=cmd['job'], pcm=base64.b64encode(pcm).decode('ascii'))
            if epoch == state['epoch']: send('done', epoch=epoch, job=cmd['job'])
        except Exception as exc:
            traceback.print_exc()
            send('error', epoch=epoch, message=str(exc))
        finally:
            if iterator is not None and hasattr(iterator,'close'): iterator.close()

if __name__ == '__main__':
    try: main()
    except Exception as exc:
        traceback.print_exc()
        send('fatal', message=str(exc))
