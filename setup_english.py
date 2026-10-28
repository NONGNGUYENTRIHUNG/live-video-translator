"""Install only the isolated English voice environment and download model assets."""
from pathlib import Path
import subprocess
import sys
import urllib.request

ROOT=Path(__file__).resolve().parent
URL='https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/'

def main():
    env=ROOT/'.venv-english'
    python=env/('Scripts/python.exe' if sys.platform=='win32' else 'bin/python')
    if not python.exists(): subprocess.run([sys.executable,'-m','venv',str(env)],check=True)
    subprocess.run([str(python),'-m','pip','install','kokoro-onnx==0.6.1','scipy>=1.11,<2'],check=True)
    assets=ROOT/'english_models'; assets.mkdir(exist_ok=True)
    for name in ('kokoro-v1.0.onnx','voices-v1.0.bin'):
        path=assets/name
        if path.is_file() and path.stat().st_size>1000000:
            print('Already downloaded:',name,flush=True); continue
        print('Downloading',name,'— please wait.',flush=True)
        temporary=path.with_suffix(path.suffix+'.part')
        try:
            with urllib.request.urlopen(URL+name,timeout=60) as response, temporary.open('wb') as out:
                expected=response.headers.get('Content-Length')
                total=0
                while True:
                    chunk=response.read(1024*1024)
                    if not chunk: break
                    out.write(chunk); total+=len(chunk)
                    print(f'\r{total/1024/1024:.0f} MB',end='',flush=True)
            print()
            if total<1000000 or (expected and total!=int(expected)): raise RuntimeError('Incomplete download: '+name)
            temporary.replace(path)
        finally: temporary.unlink(missing_ok=True)
    # Load files and confirm required voices, without using the translator environment.
    code="from kokoro_onnx import Kokoro; import sys; k=Kokoro(sys.argv[1],sys.argv[2]); assert {'af_bella','am_michael'} <= set(k.get_voices()); print('Bella and Michael are installed. Start the translator and click Test voice.')"
    subprocess.run([str(python),'-c',code,str(assets/'kokoro-v1.0.onnx'),str(assets/'voices-v1.0.bin')],check=True)

if __name__=='__main__': main()
