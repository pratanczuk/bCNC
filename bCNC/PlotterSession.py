"""Persistent connection preferences and bounded diagnostic history, without widgets."""
from dataclasses import dataclass
from collections import deque


@dataclass
class ConnectionPreferences:
    port: str = ''
    baud: int = 115200
    controller: str = 'AUTO'
    autoconnect: bool = False

    @classmethod
    def load(cls):
        import Utils
        return cls(Utils.getStr('Connection', 'port'),
                   Utils.getInt('Connection', 'baud', 115200),
                   Utils.getStr('Connection', 'firmware_mode', 'AUTO'),
                   Utils.getBool('Connection', 'openserial'))

    def save(self):
        import Utils
        for key in list(Utils.config['bCNC']):
            if key in ('page','ribbon') or key.endswith(('.page','.ribbon')):
                Utils.config.remove_option('bCNC', key)
        Utils.setStr('Connection', 'port', self.port)
        Utils.setInt('Connection', 'baud', self.baud)
        Utils.setStr('Connection', 'firmware_mode', self.controller)
        Utils.setBool('Connection', 'openserial', self.autoconnect)


class DiagnosticLog:
    def __init__(self, limit=1000):
        self.entries = deque(maxlen=limit)

    def record(self, kind, text):
        self.entries.append((kind, text))

    def clear(self, event=None):
        self.entries.clear()

    def text(self):
        return '\n'.join(text for _, text in self.entries)
