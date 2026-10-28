# Live Video Translator

A Windows desktop app that translates system audio into English or Vietnamese subtitles and optional speech. Built with Python and Tkinter.

## Features
- Original-language recognition with faster-whisper and multilingual text translation with M2M100.
- English voices: Bella and Michael (Kokoro). Vietnamese voices: Mai Anh and Hải Đăng (VieNeu).
- Dark & Gold and Blue & White themes, rounded controls, optional page animations.
- Movable transparent subtitle overlay with font sizing.
- Original transcript, translation history and optional local logs.
- Stop/Start session isolation to clear old video results.

## Requirements
Windows, Python 3.12, an NVIDIA CUDA-capable GPU, and compatible CUDA 12/cuDNN 9 runtime libraries for faster-whisper. The Vietnamese worker also requires CUDA. This is a GPU-oriented prototype, not a CPU-only or cross-platform release.

The app was developed for an RTX 4060 laptop. Memory use and performance vary with concurrent recognition and synthesis. Internet is needed for installation and model downloads; this version uses local inference rather than paid speech APIs.

## Setup (PowerShell)
From the repository folder:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe setup_translation.py
.\.venv\Scripts\python.exe setup_english.py
```

Create a separate environment for Vietnamese speech:

```powershell
py -3.12 -m venv .venv-vieneu
.\.venv-vieneu\Scripts\python.exe -m pip install --upgrade pip
.\.venv-vieneu\Scripts\python.exe -m pip install torch==2.8.0 torchaudio==2.8.0 --index-url https://download.pytorch.org/whl/cu128
.\.venv-vieneu\Scripts\python.exe -m pip install -r requirements-vieneu.txt
$env:VIENEU_PYTHON = (Resolve-Path '.\.venv-vieneu\Scripts\python.exe').Path
.\.venv\Scripts\python.exe app.py
```

Set VIENEU_PYTHON in each new terminal before launch. If you already have a working VieNeu environment, point it to that environment's python.exe instead. Do not recreate existing working environments unnecessarily.

The first launch downloads additional recognition/voice models. GPU drivers and CUDA libraries must be compatible; installing these Python packages alone does not configure the system CUDA runtime. A complete clean-machine installation has not been validated.

## Use
1. Get Started → select video language (or Auto) and target language.
2. Optionally enable Read aloud and Test voice.
3. Start translation; wait for Listening, then play the video.
4. Subtitle Overlay hides the main panel. Drag text to move; hover for size/exit controls. Escape exits while the overlay has focus.
5. Stop and wait before starting another video.

Settings holds recognition model, motion and always-on-top controls. History & logging controls transcript persistence. Logs are local and enabled by default; disable them before starting a session if unwanted. Theme preferences are saved under LOCALAPPDATA/LiveVideoTranslator.

## Limitations
Recognition and translation can be inaccurate. Translation and speech add delay; processing may fall behind. Exclusive full-screen players may obscure the overlay; use windowed/borderless playback. Windows transparency needs verification on each target setup. Native window borders are controlled by Windows.

## Tests
```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```
Automated tests cover session isolation and selected translation/voice behaviors, not real-time accuracy, GPU performance or listening quality.

## Third-party components
Model weights are downloaded separately and are not included. This project uses faster-whisper/Whisper, facebook/m2m100_418M, VieNeu and kokoro-onnx/Kokoro, plus libraries listed in the requirements and setup scripts. Their upstream code, model and voice terms apply separately. No project-wide license has been selected yet.

Design inspiration: Taras Bakusevych's “58 rules for beautiful UI design”: https://uxdesign.cc/58-rules-for-stunning-and-effective-user-interface-design-ea4b93f931f6
