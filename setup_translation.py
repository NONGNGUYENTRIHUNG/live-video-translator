"""Create an isolated CPU translation environment, then download the multilingual model."""
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parent

def main():
    env=ROOT/'.venv-translation'
    python=env/('Scripts/python.exe' if sys.platform=='win32' else 'bin/python')
    if not python.exists(): subprocess.run([sys.executable,'-m','venv',str(env)],check=True)
    subprocess.run([str(python),'-m','pip','install','torch==2.8.0','--index-url','https://download.pytorch.org/whl/cpu'],check=True)
    subprocess.run([str(python),'-m','pip','install','transformers==4.57.6','sentencepiece>=0.2,<0.3','sacremoses>=0.1,<0.2'],check=True)
    code='''from transformers import AutoTokenizer,AutoModelForSeq2SeqLM
for name in ['facebook/m2m100_418M']:
 print('Downloading/checking '+name,flush=True)
 t=AutoTokenizer.from_pretrained(name)
 m=AutoModelForSeq2SeqLM.from_pretrained(name)
 del m,t
print('Translation setup complete. You can start the app.',flush=True)
'''
    subprocess.run([str(python),'-u','-c',code],check=True)
if __name__=='__main__': main()
