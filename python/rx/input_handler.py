#!/usr/bin/env python3
import os
import sys

if os.name == "nt":
    import msvcrt
else:
    import select
    import termios
    import tty

class NonBlockingInput:
    """Gestione dell'input per terminale senza attese."""
    def __init__(self):
        self.is_windows = os.name == "nt"
        if not self.is_windows:
            self.fd = sys.stdin.fileno()
            self.old_settings = None

    def __enter__(self):
        if not self.is_windows:
            try:
                self.old_settings = termios.tcgetattr(self.fd)
                tty.setcbreak(self.fd)
            except Exception:
                pass
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if not self.is_windows and self.old_settings is not None:
            try:
                termios.tcsetattr(self.fd, termios.TCSADRAIN, self.old_settings)
            except Exception:
                pass

    def get_key(self):
        return self._get_key_windows() if self.is_windows else self._get_key_unix()

    def _get_key_windows(self):
        if not msvcrt.kbhit():
            return None
        ch = msvcrt.getch()
        if ch in (b"\x00", b"\xe0"):
            ch2 = msvcrt.getch()
            if ch2 == b"H": return "up"
            if ch2 == b"P": return "down"
        elif ch.lower() in (b"w", b"k"): return "up"
        elif ch.lower() in (b"s", b"j"): return "down"
        elif ch.lower() == b"q" or ch == b"\x03": return "exit"
        return None

    def _get_key_unix(self):
        r, _, _ = select.select([sys.stdin], [], [], 0)
        if not r:
            return None
        ch = sys.stdin.read(1)
        if ch == "\x1b":
            r2, _, _ = select.select([sys.stdin], [], [], 0.05)
            if r2:
                seq = sys.stdin.read(2)
                if seq == "[A": return "up"
                if seq == "[B": return "down"
        elif ch.lower() in ("w", "k"): return "up"
        elif ch.lower() in ("s", "j"): return "down"
        elif ch.lower() == "q" or ch == "\x03": return "exit"
        return None