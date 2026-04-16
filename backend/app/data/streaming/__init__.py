"""Real-time market-data streaming.

Three components:
- ``StreamHub`` (``hub.py``): in-process pub/sub. Anyone (HTTP WebSocket
  router, OHLCV writer, strategy run loop) subscribes to a per-symbol channel.
- ``OhlcvWriter`` (``ohlcv_writer.py``): rolls ticks into 1-minute bars and
  flushes them to the ``ohlcv_candles`` hypertable.
- ``StreamingManager`` (``manager.py``): owns broker WebSocket connections,
  fans incoming ticks into the hub.

Brokers don't share a wire protocol, so each broker's adapter exposes a
``stream_ticks(symbols)`` async generator (when supported); the manager uses
that uniformly. Adapters that don't support streaming yet simply don't appear.
"""

from app.data.streaming.hub import StreamHub
from app.data.streaming.manager import StreamingManager
from app.data.streaming.ohlcv_writer import OhlcvWriter
from app.data.streaming.types import Tick

__all__ = ["StreamHub", "StreamingManager", "OhlcvWriter", "Tick"]
