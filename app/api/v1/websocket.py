"""WebSocket router for live log streaming."""
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.core.websocket_manager import manager

logger = logging.getLogger(__name__)
router = APIRouter()

@router.websocket("/ws/{run_id}")
async def websocket_endpoint(websocket: WebSocket, run_id: str):
    await manager.connect(websocket, run_id)
    try:
        while True:
            # We don't expect the client to send much, but we need to keep the connection open
            # and listen for disconnects.
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket, run_id)
    except Exception as e:
        logger.error(f"WebSocket error for run_id={run_id}: {e}")
        manager.disconnect(websocket, run_id)
