"""Windows proof of concept: system audio -> speech recognition -> subtitles."""
import queue
import json
from datetime import datetime
from speech_pipeline import WindowBuilder, WordCommitter, SentenceBuffer
import os
from pathlib import Path
from voice_output import VoiceOutput
from translation_client import TranslationClient, TranslationCancelled
from session_state import SessionState

SOURCE_CODES = {"Auto": None, "English": "en", "Vietnamese": "vi", "Spanish": "es", "French": "fr", "German": "de", "Japanese": "ja", "Korean": "ko", "Chinese": "zh", "Portuguese": "pt", "Italian": "it", "Arabic": "ar", "Hindi": "hi", "Russian": "ru", "Thai": "th", "Indonesian": "id", "Turkish": "tr"}
import re
import time
import threading
import tkinter as tk
from tkinter import ttk, messagebox

SAMPLE_RATE = 16000
FRAME_SECONDS = 0.25
MAX_SPEECH_SECONDS = 2.5
SILENCE_FRAMES = 2
MAX_SENTENCE_WAIT = 3

class TranslatorApp:
    def __init__(self, root):
        self.root = root
        root.title('Live Video Translator — Prototype')
        root.geometry('900x580')
        root.attributes('-topmost', True)
        self.events = queue.Queue()
        self.stop_event = threading.Event()
        self.running = False
        self.sessions = SessionState()
        self.translator = TranslationClient()
        self.voice = VoiceOutput(lambda text, failed=False: self.events.put(('voice_error' if failed else 'voice_status', text)))
        self.speak = tk.BooleanVar(value=False)
        self.gender = tk.StringVar(value='Mai Anh')
        self.voice_volume = tk.DoubleVar(value=85)
        self.voice_rate = tk.DoubleVar(value=0)
        self.voice_status = tk.StringVar(value='Loading English and Vietnamese voices in the background...')
        self.language = tk.StringVar(value='Vietnamese')
        self.source = tk.StringVar(value='Auto')
        self.quality = tk.StringVar(value='Turbo')
        self.status = tk.StringVar(value='Choose a language, then press Start.')
        self.subtitle = tk.StringVar(value='Your translated subtitles will appear here.')
        from desktop_ui import DesktopUI
        self.ui = DesktopUI(self, SOURCE_CODES)
        root.protocol('WM_DELETE_WINDOW', self.close)
        root.after(100, self.poll)

    def change_language(self, event=None):
        voices = ['Mai Anh', 'Hải Đăng'] if self.language.get() == 'Vietnamese' else ['Bella', 'Michael']
        self.genderbox.configure(values=voices)
        self.gender.set(voices[0])
        self.sync_voice()

    def sync_voice(self):
        self.voice.configure(self.speak.get(), self.language.get(), self.gender.get(), self.voice_volume.get(), self.voice_rate.get())
        if not self.speak.get():
            self.voice.cancel()
            self.voice_status.set('Voice off')
        else:
            self.voice_status.set('Voice enabled. ' + self.voice.status())

    def test_voice(self):
        self.speak.set(True)
        self.sync_voice()
        self.voice.cancel()
        text = ('Xin chào! Đây là giọng đọc thử. Bạn có nghe rõ và tự nhiên không?'
                if self.language.get() == 'Vietnamese' else
                'Hello! This is a voice preview. Does this sound clear and natural?')
        self.voice.submit(text)

    def clear_display(self):
        self.subtitle.set('Waiting for the new video…')
        self.original.set('Recognized speech will appear here.')
        self.history.configure(state='normal')
        self.history.delete('1.0', 'end')
        self.history.configure(state='disabled')

    def start(self):
        if self.running: return
        self.running = True
        session = self.sessions.start()
        self.voice.cancel()
        self.clear_display()
        self.sync_voice()
        self.stop_event = threading.Event()
        self.choice.configure(state='disabled'); self.source_choice.configure(state='disabled'); self.model_choice.configure(state='disabled'); self.start_button.configure(state='disabled'); self.stop_button.configure(state='normal')
        self.status.set('Loading models. The first start may download files and take several minutes...')
        threading.Thread(target=self.worker, args=(self.language.get(), self.source.get(), self.quality.get(), self.stop_event, self.save_log.get(), session), daemon=True).start()

    def stop(self):
        self.sessions.stop()
        self.clear_display()
        self.voice.cancel()
        self.stop_event.set()
        self.status.set('Stopping after the current operation...')
        self.stop_button.configure(state='disabled')

    def close(self):
        self.stop_event.set(); self.translator.close(); self.voice.close(); self.root.destroy()

    def poll(self):
        try:
            while True:
                event = self.events.get_nowait()
                session, kind, value = event if len(event) == 3 else (None, *event)
                if not self.sessions.accepts(session, kind): continue
                if kind == 'status': self.status.set(value)
                elif kind == 'subtitle':
                    self.subtitle.set(value)
                    self.history.configure(state='normal')
                    self.history.insert('end', value + '\n\n')
                    self.history.see('end')
                    self.history.configure(state='disabled')
                    if self.running and not self.stop_event.is_set(): self.voice.submit(value)
                elif kind == 'source_text':
                    self.original.set(value)
                    self.history.configure(state='normal')
                    self.history.insert('end', 'Original: ' + value + '\n')
                    self.history.configure(state='disabled')
                elif kind == 'voice_status': self.voice_status.set(value)
                elif kind == 'voice_error':
                    self.speak.set(False)
                    self.voice_status.set(value)
                elif kind == 'error': self.status.set('Stopped due to an error.'); messagebox.showerror('Translation error', value)
                elif kind == 'done':
                    self.running = False
                    self.choice.configure(state='readonly'); self.source_choice.configure(state='readonly'); self.model_choice.configure(state='readonly'); self.start_button.configure(state='normal'); self.stop_button.configure(state='disabled')
                    if value: self.status.set(value)
        except queue.Empty: pass
        self.root.after(100, self.poll)

    def worker(self, target, source, quality, stop_event, save_log, session):
        logfile = None
        capture_thread = None
        def post(kind, value):
            self.events.put((session, kind, value))
        try:
            import numpy as np
            import soundcard as sc
            from faster_whisper import WhisperModel
            import sys
            if sys.platform != 'win32':
                raise RuntimeError('This prototype captures Windows system audio. Run it with Windows Python, not WSL.')
            model_name = ('dropbox-dash/faster-whisper-large-v3-turbo' if quality == 'Turbo'
                          else quality.lower() + ('.en' if source == 'English' else ''))
            # Retain DLL-directory handles for the session, including cuDNN’s CUDA-specific bin.
            dll_handles = []
            for base in [Path(os.environ.get('ProgramFiles', 'C:/Program Files')) / 'NVIDIA/CUDNN', Path(os.environ.get('ProgramFiles', 'C:/Program Files')) / 'NVIDIA GPU Computing Toolkit/CUDA']:
                if base.exists():
                    for pattern in ['**/cudnn64_9.dll', '**/cublas64_12.dll']:
                        for dll in sorted(base.glob(pattern), reverse=True):
                            if '13.' not in str(dll):
                                dll_handles.append(os.add_dll_directory(str(dll.parent)))
                                break
            model = WhisperModel(model_name, device='cuda', compute_type='int8_float16')
            target_code = SOURCE_CODES[target]
            language = SOURCE_CODES[source]
            prepare_source = language or ('vi' if target_code == 'en' else 'en')
            self.translator.request(prepare_source, target_code, '', stop_event,
                                    lambda text: post('status', text), prepare=True)
            if stop_event.is_set(): return
            # FIFO retains every window. It never evicts old captured speech.
            chunks = queue.Queue(maxsize=64)
            capture_error = queue.Queue(maxsize=1)
            capture_done = threading.Event()
            if save_log:
                folder = Path(__file__).resolve().parent / 'logs'
                folder.mkdir(exist_ok=True)
                logfile = (folder / (datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '.jsonl')).open('w', encoding='utf-8')
            def log(kind, **fields):
                if logfile:
                    logfile.write(json.dumps(dict(time=datetime.now().isoformat(), kind=kind, **fields), ensure_ascii=False) + '\n')
                    logfile.flush()

            def capture():
                try:
                    import flexaudio
                    builder=WindowBuilder()
                    buffered=np.empty(0,dtype=np.float32)
                    previous_drops=0
                    with flexaudio.open('system', exclude_self=True, output_rate=SAMPLE_RATE, output_channels=1, strict=True) as stream:
                        while not stop_event.is_set():
                            event=stream.poll_event()
                            if event is not None and event.type=='error': raise RuntimeError(str(event))
                            drops=stream.dropped_chunks()
                            if drops>previous_drops:
                                post('status', 'Capture lost audio at the device. Check system load; see terminal.')
                                print('Capture dropped chunks:', drops, flush=True)
                            previous_drops=drops
                            chunk=stream.poll_chunk()
                            if chunk is None:
                                stop_event.wait(.005); continue
                            buffered=np.concatenate((buffered,np.frombuffer(chunk.data,dtype='<f4')))
                            while len(buffered)>=1600:
                                window=builder.feed(buffered[:1600])
                                buffered=buffered[1600:]
                                if window is not None:
                                    try: chunks.put_nowait((window,time.monotonic()))
                                    except queue.Full:
                                        raise RuntimeError('Recognition cannot keep up: capture stopped rather than deleting queued speech. Pause the video and use a smaller model.')
                except Exception as exc:
                    capture_error.put(exc)
                finally:
                    capture_done.set()

            post('status', 'Listening. Original-language recognition → multilingual translation.')
            capture_thread = threading.Thread(target=capture,daemon=True)
            capture_thread.start()
            committer=WordCommitter()
            sentences=SentenceBuffer()
            last_text_time=time.monotonic()
            current_source = language
            detected_previous = None
            detection_count = 0
            recognition_seconds=0.0
            def emit(text, reason):
                if not text or stop_event.is_set(): return
                t=time.monotonic()
                post('source_text', text)
                result, translation_model = self.translator.request(current_source, target_code, text, stop_event,
                    lambda value: post('status', value))
                log('translation', recognized=text, translated=result, target=target, boundary=reason,
                    source=current_source, translation_model=translation_model, recognition_seconds=recognition_seconds, translation_seconds=time.monotonic()-t)
                if not stop_event.is_set(): post('subtitle',result)
            while not stop_event.is_set():
                try: window,captured=chunks.get(timeout=.2)
                except queue.Empty:
                    if sentences.pending and time.monotonic()-last_text_time>3:
                        for sentence in sentences.add('',final=True): emit(sentence,'idle timeout')
                    if capture_done.is_set():
                        try: err=capture_error.get_nowait()
                        except queue.Empty: break
                        log('capture_error', message=str(err))
                        raise RuntimeError(str(err))
                    continue
                lag=time.monotonic()-captured
                recognition_started=time.monotonic()
                segments,info=model.transcribe(window.audio,language=language,task='transcribe',
                    beam_size=3, word_timestamps=True, vad_filter=True,
                    vad_parameters=dict(threshold=.35,min_silence_duration_ms=600,speech_pad_ms=300),
                    condition_on_previous_text=False)
                segments=list(segments)
                detected = language or info.language
                if current_source and detected != current_source:
                    for sentence in sentences.add('', final=True): emit(sentence, 'language change')
                current_source = detected
                if language is None and any(segment.text.strip() for segment in segments):
                    detection_count = detection_count + 1 if detected == detected_previous else 1
                    detected_previous = detected
                    if detection_count >= 2 and info.language_probability >= .7:
                        language = detected  # One dominant language per video; reset on Start.
                words=[word for segment in segments for word in (segment.words or [])]
                text=committer.accept(window,words)
                recognition_seconds=time.monotonic()-recognition_started
                log('recognition', window_start=window.start, final=window.final,
                    raw=' '.join(s.text for s in segments), committed=text, detected_language=info.language,
                    queue_delay_seconds=lag, recognition_seconds=recognition_seconds)
                if text: last_text_time=time.monotonic()
                for sentence in sentences.add(text, final=window.final):
                    emit(sentence,'speech pause' if window.final else 'punctuation/clause')
                message=f'Recognition {recognition_seconds:.1f}s | Queue delay {lag:.1f}s | Waiting windows {chunks.qsize()}'
                if lag>5: message+=' | Falling behind: pause video or choose a smaller model.'
                post('status', f'Source: {current_source} | ' + message)
        except TranslationCancelled:
            pass
        except Exception as exc:
            if not stop_event.is_set(): post('error', str(exc))
        finally:
            was_stopped = stop_event.is_set()
            stop_event.set()
            if capture_thread is not None: capture_thread.join()
            if logfile: logfile.close()
            if session == self.sessions.generation: self.voice.cancel()
            post('done', 'Stopped.' if was_stopped else '')

if __name__ == '__main__':
    root = tk.Tk(); TranslatorApp(root); root.mainloop()
