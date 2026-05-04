"""TCP audio receiver — accepts a single client and provides a read interface
that mimics a PyAudio stream, so wake_word and audio_capture can use it.

Listens on 0.0.0.0:PORT and waits for the Mac sender to connect.
"""

import socket
import logging
import threading

logger = logging.getLogger(__name__)

DEFAULT_PORT = 9999


class NetworkAudioStream:
    """Drop-in replacement for a PyAudio input stream, fed over TCP."""

    def __init__(self, port: int = DEFAULT_PORT):
        self.port = port
        self._server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server.bind(("0.0.0.0", port))
        self._server.listen(1)
        self._conn = None
        self._lock = threading.Lock()

    def wait_for_connection(self):
        """Block until a client (Mac sender) connects."""
        logger.info("Waiting for network audio on port %d...", self.port)
        self._conn, addr = self._server.accept()
        logger.info("Audio client connected from %s", addr)

    def read(self, num_bytes: int) -> bytes:
        """Read exactly num_bytes from the TCP stream."""
        data = b""
        while len(data) < num_bytes:
            chunk = self._conn.recv(num_bytes - len(data))
            if not chunk:
                raise ConnectionError("Audio client disconnected")
            data += chunk
        return data

    def close(self):
        if self._conn:
            self._conn.close()
        self._server.close()
