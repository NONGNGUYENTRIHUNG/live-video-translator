"""UI-owned session generation: stale results never reach the next video's screen."""
class SessionState:
    def __init__(self): self.generation=0; self.stopped=True
    def start(self):
        self.generation+=1; self.stopped=False; return self.generation
    def stop(self): self.stopped=True
    def accepts(self,generation,kind):
        if generation is None: return True  # Engine readiness, not video content.
        return generation==self.generation and (not self.stopped or kind=='done')
