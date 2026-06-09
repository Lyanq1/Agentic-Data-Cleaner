"""WebSocket Connection Manager for Real-Time Streaming."""
import logging
from typing import Dict, List
from fastapi import WebSocket

logger = logging.getLogger(__name__)

class ConnectionManager:
    def __init__(self):
        # Maps run_id to a list of active WebSocket connections
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, run_id: str):
        """Accept a new websocket connection for a given run_id."""
        await websocket.accept()
        if run_id not in self.active_connections:
            self.active_connections[run_id] = []
        self.active_connections[run_id].append(websocket)
        logger.info(f"WebSocket connected for run_id={run_id}")

    def disconnect(self, websocket: WebSocket, run_id: str):
        """Remove a websocket connection."""
        if run_id in self.active_connections:
            if websocket in self.active_connections[run_id]:
                self.active_connections[run_id].remove(websocket)
            if not self.active_connections[run_id]:
                del self.active_connections[run_id]
        logger.info(f"WebSocket disconnected for run_id={run_id}")

    async def broadcast_to_run(self, run_id: str, message: dict):
        """Broadcast a JSON message to all websockets listening to this run_id."""
        if run_id in self.active_connections:
            for connection in self.active_connections[run_id]:
                try:
                    await connection.send_json(message)
                except Exception as e:
                    logger.warning(f"Failed to send message to a websocket for run_id={run_id}: {e}")

manager = ConnectionManager()
