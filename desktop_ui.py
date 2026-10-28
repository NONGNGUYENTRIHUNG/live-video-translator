"""Presentation layer for the existing Tk translator; no audio/model dependencies."""
import json
import os
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox

PALETTES = {
    'Dark & Gold': dict(bg='#17191d', panel='#22252b', text='#f4f1e9', muted='#b5b7be', accent='#d8b16b', ink='#191b20', border='#3a3e46'),
    'Blue & White': dict(bg='#f2f6fc', panel='#ffffff', text='#192d48', muted='#526680', accent='#2167d5', ink='#ffffff', border='#d5deec'),
}

class DesktopUI:
    def __init__(self, app, source_codes):
        self.app, self.root = app, app.root
        self.config_path = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'LiveVideoTranslator' / 'appearance.json'
        try:
            prefs = json.loads(self.config_path.read_text(encoding='utf-8'))
            if not isinstance(prefs, dict): prefs = {}
        except (OSError, ValueError):
            prefs = {}
        self.theme = tk.StringVar(value=prefs.get('theme') if prefs.get('theme') in PALETTES else 'Dark & Gold')
        self.motion = tk.BooleanVar(value=bool(prefs.get('motion', True)))
        try:
            size = int(prefs.get('font_size', 30))
        except (ValueError, TypeError):
            size = 30
        self.font_size = tk.IntVar(value=max(18, min(54, size)))
        self.overlay = None
        self.fade_job = None
        self.root.title('Live Video Translator')
        self.root.geometry('1080x820')
        self.root.minsize(940, 740)
        self.root.attributes('-topmost', False)
        self.style = ttk.Style(self.root)
        self.style.theme_use('clam')
        self.header = ttk.Frame(self.root, padding=(24, 14))
        self.header.pack(fill='x')
        ttk.Button(self.header, text='Home', command=lambda: self.show('home')).pack(side='left')
        ttk.Label(self.header, text='  LIVE VIDEO TRANSLATOR', style='Brand.TLabel').pack(side='left')
        self.theme_button = ttk.Button(self.header, command=self.toggle_theme)
        self.theme_button.pack(side='right')
        ttk.Button(self.header, text='Settings', command=self.open_settings).pack(side='right', padx=12)
        self.body = ttk.Frame(self.root, padding=(24, 8, 24, 20))
        self.body.pack(fill='both', expand=True)
        self.pages = {name: ttk.Frame(self.body) for name in ('home', 'translate', 'help', 'about')}
        home = self.pages['home']
        center = ttk.Frame(home)
        center.place(relx=.5, rely=.46, anchor='center')
        ttk.Label(center, text='▂ ▅ █ ▅ ▂', style='Mark.TLabel', anchor='center').pack(pady=(0, 22))
        ttk.Label(center, text='Live Video Translator', style='Hero.TLabel', anchor='center').pack()
        ttk.Label(center, text='Understand videos across languages.', style='Muted.TLabel', anchor='center').pack(pady=(12, 36))
        for title, page, style in [('Get Started', 'translate', 'Accent.TButton'), ('How to Use', 'help', 'TButton'), ('About Us', 'about', 'TButton')]:
            ttk.Button(center, text=title, width=34, style=style, command=lambda p=page: self.show(p)).pack(fill='x', pady=7, ipady=6)
        ttk.Label(home, text='Live subtitles  •  Natural voices  •  Your choice of languages', style='Muted.TLabel', anchor='center').pack(side='bottom', pady=24)
        self.build_translator(source_codes)
        self.build_info('help', 'A few steps. A world of videos.', [
            ('01  Choose your languages', 'Select the video language, or use Auto. Choose English or Vietnamese for your translation.'),
            ('02  Make it sound right', 'Turn on Read aloud, choose a voice, and use Test voice. English: Bella or Michael. Vietnamese: Mai Anh or Hải Đăng.'),
            ('03  Start, then play your video', 'Press Start and wait for Listening before playing the video. Model preparation can take time on the first run.'),
            ('04  Put subtitles over your video', 'Select Subtitle Overlay. Drag the text to move it; hover to reveal text-size controls and Exit. Press Esc while the overlay is focused to return.'),
            ('05  Switch to a new video', 'Press Stop, wait until Start is available, then start again. The previous subtitles and pending results are cleared.'),
        ])
        self.build_info('about', 'Understand more. Connect more.', [
            ('Our purpose', 'Make videos easier to understand across languages through translated subtitles and natural spoken translation.'),
            ('Built around your viewing experience', 'Read alongside a video, listen to translated speech, or use a lightweight subtitle overlay without the full control panel.'),
            ('Local processing', 'This version uses local recognition, translation and voice engines. Initial setup requires model downloads. Optional transcript logs stay in your project’s logs folder.'),
            ('A helpful companion', 'Speech recognition and translation can make mistakes. Compare the original text with the translation when meaning matters.'),
        ])
        self.apply_theme()
        self.show('home', animate=False)
        self.app.subtitle.trace_add('write', self.redraw_overlay)
        self.root.bind('<Escape>', lambda e: self.exit_overlay())

    def build_info(self, name, title, sections):
        page = self.pages[name]
        ttk.Label(page, text=title, style='Hero.TLabel').pack(anchor='w', pady=(18, 20))
        for heading, text in sections:
            card = ttk.Frame(page, style='Card.TFrame', padding=16)
            card.pack(fill='x', pady=5)
            ttk.Label(card, text=heading, style='CardTitle.TLabel').pack(anchor='w')
            ttk.Label(card, text=text, style='Card.TLabel', wraplength=840, justify='left').pack(anchor='w', pady=(7, 0))
        ttk.Button(page, text='Back to Home', command=lambda: self.show('home')).pack(anchor='w', pady=14)

    def build_translator(self, source_codes):
        a = self.app
        page = self.pages['translate']
        title = ttk.Frame(page); title.pack(fill='x', pady=(6, 14))
        ttk.Label(title, text='Live translation', style='Heading.TLabel').pack(side='left')
        a.keep = tk.BooleanVar(value=False)
        ttk.Label(title, text='Choose languages → Start → Play your video', style='Muted.TLabel').pack(side='right')
        controls = ttk.Frame(page); controls.pack(fill='x', pady=(0, 16))
        for col, (label, var, values, attr) in enumerate([
            ('Video language', a.source, list(source_codes), 'source_choice'),
            ('Translate to', a.language, ['English', 'Vietnamese'], 'choice')]):
            box = ttk.Frame(controls); box.grid(row=0, column=col, sticky='ew', padx=(0, 16 if col < 1 else 0))
            controls.columnconfigure(col, weight=1)
            ttk.Label(box, text=label, style='Muted.TLabel').pack(anchor='w', pady=(0, 7))
            combo = ttk.Combobox(box, textvariable=var, values=values, state='readonly', font=('Segoe UI', 11))
            combo.pack(fill='x', ipady=4); setattr(a, attr, combo)
        a.choice.bind('<<ComboboxSelected>>', a.change_language)
        self.settings_window = tk.Toplevel(self.root)
        self.settings_window.withdraw()
        self.settings_window.title('Settings')
        self.settings_window.geometry('500x520')
        self.settings_window.resizable(False, False)
        self.settings_window.protocol('WM_DELETE_WINDOW', self.settings_window.withdraw)
        settings = ttk.Frame(self.settings_window, padding=24); settings.pack(fill='both', expand=True)
        ttk.Label(settings, text='Make it yours', style='Heading.TLabel').pack(anchor='w', pady=(0,20))
        ttk.Checkbutton(settings, text='Gentle page animations', variable=self.motion, command=self.save).pack(anchor='w', pady=8)
        ttk.Checkbutton(settings, text='Keep translator above other windows', variable=a.keep, command=lambda: self.root.attributes('-topmost', a.keep.get())).pack(anchor='w', pady=8)
        ttk.Label(settings, text='Recognition model', style='Muted.TLabel').pack(anchor='w', pady=(16,6))
        a.model_choice=ttk.Combobox(settings, textvariable=a.quality, values=['Small','Turbo'], state='readonly')
        a.model_choice.pack(fill='x')
        ttk.Label(settings, text='Turbo favors accuracy. Small reduces processing load.\nStop translation before changing models.', style='Muted.TLabel', wraplength=400).pack(anchor='w', pady=10)
        ttk.Button(settings, text='Done', command=self.settings_window.withdraw).pack(anchor='e')
        a.original = tk.StringVar(value='Recognized speech will appear here.')
        original_card = ttk.Frame(page, style='Card.TFrame', padding=16); original_card.pack(fill='x', pady=(0, 12))
        ttk.Label(original_card, text='ORIGINAL', style='CardTitle.TLabel').pack(anchor='w')
        self.original_label = ttk.Label(original_card, textvariable=a.original, style='Card.TLabel', wraplength=920)
        self.original_label.pack(fill='x', pady=(8, 0))
        card = ttk.Frame(page, style='Card.TFrame', padding=20); card.pack(fill='both', expand=True)
        ttk.Label(card, text='TRANSLATED SUBTITLES', style='CardTitle.TLabel').pack(anchor='w')
        self.subtitle_label = ttk.Label(card, textvariable=a.subtitle, style='Subtitle.TLabel', wraplength=900, anchor='w', justify='left')
        self.subtitle_label.pack(fill='both', expand=True, pady=14)
        card.bind('<Configure>', lambda e: self.subtitle_label.configure(wraplength=max(200, e.width-40)))
        self.original_label.bind('<Configure>', lambda e: self.original_label.configure(wraplength=max(200, e.width)))
        voicebar = ttk.Frame(page); voicebar.pack(fill='x', pady=16)
        ttk.Checkbutton(voicebar, text='Read aloud', variable=a.speak, command=a.sync_voice).pack(side='left')
        a.genderbox = ttk.Combobox(voicebar, textvariable=a.gender, values=['Mai Anh', 'Hải Đăng'], state='readonly', width=13)
        a.genderbox.pack(side='left', padx=12)
        a.genderbox.bind('<<ComboboxSelected>>', lambda e: a.sync_voice())
        ttk.Button(voicebar, text='Test voice', command=a.test_voice).pack(side='left')
        ttk.Label(voicebar, text='Volume', style='Muted.TLabel').pack(side='left', padx=(20, 8))
        ttk.Scale(voicebar, from_=0, to=100, variable=a.voice_volume, command=lambda v: a.sync_voice()).pack(side='left', fill='x', expand=True, padx=(0, 16))
        ttk.Button(voicebar, text='Subtitle Overlay', command=self.open_overlay).pack(side='right')
        actions = ttk.Frame(page); actions.pack(fill='x')
        a.start_button = ttk.Button(actions, text='Start translation', style='Accent.TButton', command=a.start, width=19); a.start_button.pack(side='left')
        a.stop_button = ttk.Button(actions, text='Stop', command=a.stop, state='disabled', width=10); a.stop_button.pack(side='left', padx=10)
        ttk.Button(actions, text='History & logging', command=self.open_history).pack(side='right')
        ttk.Label(page, textvariable=a.status, style='Muted.TLabel', wraplength=940).pack(fill='x', pady=(14, 3))
        ttk.Label(page, textvariable=a.voice_status, style='Muted.TLabel', wraplength=940).pack(fill='x', pady=(0, 4))
        a.save_log = tk.BooleanVar(value=True)
        self.history_window = tk.Toplevel(self.root); self.history_window.withdraw()
        self.history_window.title('Translation history'); self.history_window.geometry('800x520')
        self.history_window.protocol('WM_DELETE_WINDOW', self.history_window.withdraw)
        ttk.Checkbutton(self.history_window, text='Save recognized text and translations to local logs', variable=a.save_log).pack(anchor='w', padx=16, pady=12)
        a.history = tk.Text(self.history_window, wrap='word', state='disabled', font=('Segoe UI', 11), padx=16, pady=16)
        a.history.pack(side='left', fill='both', expand=True)
        scroll = ttk.Scrollbar(self.history_window, command=a.history.yview); scroll.pack(side='right', fill='y')
        a.history.configure(yscrollcommand=scroll.set)

    def open_settings(self):
        self.settings_window.deiconify(); self.settings_window.lift()

    def open_history(self):
        self.history_window.deiconify(); self.history_window.lift()

    def save(self):
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            self.config_path.write_text(json.dumps(dict(theme=self.theme.get(), motion=self.motion.get(), font_size=self.font_size.get())), encoding='utf-8')
        except OSError:
            pass

    def toggle_theme(self):
        self.theme.set('Blue & White' if self.theme.get() == 'Dark & Gold' else 'Dark & Gold')
        self.apply_theme(); self.save()

    def apply_theme(self):
        p = PALETTES[self.theme.get()]; s = self.style
        self.root.configure(bg=p['bg'])
        s.configure('.', background=p['bg'], foreground=p['text'], font=('Segoe UI', 11), bordercolor=p['border'])
        s.configure('TFrame', background=p['bg'])
        s.configure('TLabel', background=p['bg'], foreground=p['text'])
        s.configure('Muted.TLabel', foreground=p['muted'])
        s.configure('Brand.TLabel', font=('Segoe UI', 10, 'bold'))
        s.configure('Hero.TLabel', font=('Segoe UI', 28, 'bold'))
        s.configure('Heading.TLabel', font=('Segoe UI', 21, 'bold'))
        s.configure('Mark.TLabel', font=('Segoe UI', 32), foreground=p['accent'])
        s.configure('Card.TFrame', background=p['panel'])
        for style in ('Card.TLabel', 'CardTitle.TLabel', 'Subtitle.TLabel'):
            s.configure(style, background=p['panel'], foreground=p['text'])
        s.configure('CardTitle.TLabel', font=('Segoe UI', 10, 'bold'), foreground=p['muted'])
        s.configure('Subtitle.TLabel', font=('Segoe UI', 23))
        s.configure('TButton', background=p['panel'], foreground=p['text'], padding=(14, 10), borderwidth=1, focusthickness=2, focuscolor=p['accent'])
        s.map('TButton', background=[('active', p['border']), ('pressed', p['border'])], foreground=[('disabled', p['muted'])])
        s.configure('Accent.TButton', background=p['accent'], foreground=p['ink'])
        s.map('Accent.TButton', background=[('disabled', p['border']), ('active', p['accent'])], foreground=[('disabled', p['muted']), ('!disabled', p['ink'])])
        s.configure('TCombobox', fieldbackground=p['panel'], background=p['panel'], foreground=p['text'], arrowcolor=p['text'], padding=5)
        s.map('TCombobox', fieldbackground=[('readonly', p['panel']), ('disabled', p['bg'])], foreground=[('readonly', p['text']), ('disabled', p['muted'])], selectbackground=[('readonly', p['panel'])], selectforeground=[('readonly', p['text'])])
        s.configure('TCheckbutton', background=p['bg'], foreground=p['text'])
        s.map('TCheckbutton', background=[('active', p['bg'])], foreground=[('active', p['text'])])
        s.configure('Horizontal.TScale', background=p['bg'], troughcolor=p['border'])
        self.root.option_add('*TCombobox*Listbox.background', p['panel'])
        self.root.option_add('*TCombobox*Listbox.foreground', p['text'])
        self.root.option_add('*TCombobox*Listbox.selectBackground', p['accent'])
        self.root.option_add('*TCombobox*Listbox.selectForeground', p['ink'])
        self.app.history.configure(bg=p['panel'], fg=p['text'], insertbackground=p['text'], selectbackground=p['accent'])
        self.theme_button.configure(text='Theme: ' + self.theme.get())
        from rounded_styles import install
        install(self, p)

    def show(self, name, animate=True):
        if name != 'translate' and self.app.running:
            if not messagebox.askyesno('Stop translation?', 'Stop the current translation and return to this screen?', parent=self.root):
                return
            self.app.stop()
        for page in self.pages.values(): page.pack_forget()
        self.pages[name].pack(fill='both', expand=True)
        if animate and self.motion.get(): self.fade()

    def fade(self):
        if self.fade_job is not None: self.root.after_cancel(self.fade_job)
        def step(index=0):
            try:
                self.root.attributes('-alpha', .90 + .01 * index)
                self.fade_job = self.root.after(16, step, index+1) if index < 10 else None
            except tk.TclError:
                self.fade_job = None
        step()

    def open_overlay(self):
        if self.overlay is not None: return
        w = self.overlay = tk.Toplevel(self.root)
        w.withdraw(); w.overrideredirect(True); w.attributes('-topmost', True)
        w.geometry(f'900x240+{max(0,(self.root.winfo_screenwidth()-900)//2)}+{max(0,self.root.winfo_screenheight()-320)}')
        key = '#010203'
        try:
            w.attributes('-transparentcolor', key)
        except tk.TclError:
            messagebox.showinfo('Subtitle overlay', 'Transparent backgrounds require Windows. This system will use a dark subtitle panel.', parent=self.root)
            key = '#17191d'
        w.configure(bg=key)
        self.canvas = tk.Canvas(w, bg=key, highlightthickness=0, cursor='fleur')
        self.canvas.pack(fill='both', expand=True)
        self.toolbar = ttk.Frame(w, padding=6)
        ttk.Label(self.toolbar, text='Drag text to move').pack(side='left', padx=8)
        ttk.Button(self.toolbar, text='A−', command=lambda: self.resize_overlay(-2)).pack(side='left')
        ttk.Button(self.toolbar, text='A+', command=lambda: self.resize_overlay(2)).pack(side='left', padx=4)
        ttk.Button(self.toolbar, text='Exit Overlay', command=self.exit_overlay).pack(side='left')
        self.toolbar.place(relx=.5, y=2, anchor='n')
        self.overlay_hide_job = None
        def reveal(e=None):
            if self.overlay_hide_job: w.after_cancel(self.overlay_hide_job)
            self.toolbar.place(relx=.5, y=2, anchor='n')
            self.overlay_hide_job = w.after(2200, lambda: self.toolbar.place_forget())
        self.canvas.bind('<Motion>', reveal)
        self.canvas.bind('<ButtonPress-1>', lambda e: setattr(self, 'drag', (e.x_root-w.winfo_x(), e.y_root-w.winfo_y())))
        self.canvas.bind('<B1-Motion>', lambda e: w.geometry(f'+{max(0,e.x_root-self.drag[0])}+{max(0,e.y_root-self.drag[1])}'))
        self.canvas.bind('<Configure>', self.redraw_overlay)
        w.bind('<Escape>', lambda e: self.exit_overlay())
        w.protocol('WM_DELETE_WINDOW', self.exit_overlay)
        w.deiconify(); w.lift(); w.focus_force()
        self.root.withdraw(); self.history_window.withdraw(); self.settings_window.withdraw()
        self.redraw_overlay(); reveal()

    def resize_overlay(self, delta):
        self.font_size.set(max(18, min(54, self.font_size.get()+delta)))
        self.save(); self.redraw_overlay()

    def redraw_overlay(self, *args):
        if self.overlay is None: return
        c = self.canvas; c.delete('all')
        width = max(c.winfo_width(), 400)
        text = self.app.subtitle.get()
        opts = dict(text=text, font=('Segoe UI', self.font_size.get(), 'bold'), width=width-64, justify='center', anchor='n')
        # Grow vertically for wrapped subtitles rather than clipping long sentences.
        item = c.create_text(width/2, 68, fill='white', **opts)
        bounds = c.bbox(item)
        if bounds:
            height = max(190, bounds[3]+28)
            height = min(height, self.root.winfo_screenheight()-80)
            if abs(self.overlay.winfo_height()-height)>2:
                self.overlay.geometry(f'{width}x{height}')
        c.delete('all')
        for dx, dy in ((-2,-2),(-2,0),(-2,2),(0,-2),(0,2),(2,-2),(2,0),(2,2)):
            c.create_text(width/2+dx, 68+dy, fill='#111111', **opts)
        c.create_text(width/2, 68, fill='#ffffff', **opts)

    def exit_overlay(self):
        if self.overlay is None: return
        if self.overlay_hide_job:
            self.overlay.after_cancel(self.overlay_hide_job)
        self.overlay.destroy(); self.overlay = None
        self.root.deiconify(); self.root.lift()
        self.root.attributes('-topmost', self.app.keep.get())
