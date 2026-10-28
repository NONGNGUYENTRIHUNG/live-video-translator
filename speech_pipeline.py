"""Audio windows retain overlap; timestamps prevent replaying committed words."""
from dataclasses import dataclass
import re
import numpy as np

RATE=16000

@dataclass
class AudioWindow:
    audio: object
    start: float
    final: bool
    overlap: float=0.8

class WindowBuilder:
    def __init__(self, rate=RATE, max_seconds=4.0, overlap=.8, silence=.6):
        self.rate=rate; self.limit=int(rate*max_seconds); self.overlap=int(rate*overlap)
        self.silence=int(rate*silence); self.data=np.empty(0,dtype=np.float32)
        self.start=0; self.quiet=0; self.heard=False
    def feed(self, block):
        # Called in fixed 100ms blocks. Even low-energy audio is retained.
        self.data=np.concatenate((self.data,block))
        if np.sqrt(np.mean(block**2)) >= .0004:
            self.heard=True; self.quiet=0
        else: self.quiet+=len(block)
        final=self.heard and self.quiet>=self.silence
        if not final and len(self.data)<self.limit: return None
        result=AudioWindow(self.data.copy(),self.start/self.rate,final,self.overlap/self.rate)
        keep=0 if final else self.overlap
        consumed=len(self.data)-keep
        self.start+=consumed
        self.data=self.data[-keep:].copy() if keep else np.empty(0,dtype=np.float32)
        self.heard=bool(keep and np.sqrt(np.mean(self.data**2))>=.0004); self.quiet=0
        return result

class WordCommitter:
    def __init__(self): self.last_end=-1.0
    def accept(self, window, words):
        cutoff=window.start+len(window.audio)/RATE-(0 if window.final else window.overlap)
        output=[]
        for word in words:
            end=window.start+word.end
            if end>cutoff+.001: continue  # Retry unstable tail in the next window.
            if end<=self.last_end+.04: continue
            output.append(word.word)
            self.last_end=end
        return ''.join(output).strip()

class SentenceBuffer:
    def __init__(self): self.pending=''
    def add(self,text,final=False):
        if text: self.pending=(self.pending+' '+text).strip()
        # Avoid splitting common abbreviations and decimals. This is a heuristic.
        ready=[]
        while True:
            match=re.search(r'[.!?]["\u201d\u2019\']?(?:\s+|$)',self.pending)
            if not match: break
            head=self.pending[:match.end()].strip()
            if re.search(r'\b(?:Mr|Mrs|Ms|Dr|Prof|St|vs|etc)\.$',head,re.I):
                # Keep the abbreviation together; find a later boundary.
                tail=self.pending[match.end():]
                later=re.search(r'[!?]|\.(?=\s|$)',tail)
                if not later: break
                end=match.end()+later.end()
            else: end=match.end()
            ready.append(self.pending[:end].strip()); self.pending=self.pending[end:].strip()
        if final and self.pending:
            ready.append(self.pending); self.pending=''
        # Bound very long unpunctuated speech at a clause when possible.
        if len(self.pending)>420:
            split=max(self.pending.rfind(',',0,420),self.pending.rfind(';',0,420))
            if split<100: split=self.pending.rfind(' ',0,420)
            if split>0:
                ready.append(self.pending[:split+1].strip()); self.pending=self.pending[split+1:].strip()
        return ready
