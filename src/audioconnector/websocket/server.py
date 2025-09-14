import logging
from fastapi import WebSocket, WebSocketDisconnect

from ..auth.authenticator import verify_websocket_signature
from ..common.session import Session
from ..services.secret_service import SecretService

class WebSocketServer:
    """
    WebSocket server for handling connections and sessions
    """
    def __init__(self):
        self.session_map = {}
        self.secret_service = SecretService()
        self.logger = logging.getLogger(__name__)

    async def handle_websocket(self, websocket: WebSocket):
        """
        Handle incoming WebSocket connection
        
        Args:
            websocket: Incoming WebSocket connection
        """
        try:
            # Verify request signature
            verify_result = await verify_websocket_signature(websocket, self.secret_service)
            
            if verify_result.get('code') != 'VERIFIED':
                self.logger.warning(f"Authentication failed: {verify_result.get('reason', 'Unknown reason')}")
                await websocket.close(code=4001)
                return

            await websocket.accept()
            self.logger.info('Authentication was successful.')

            # Create session
            session_id = websocket.headers.get('audiohook-session-id', '')
            session = Session(websocket, session_id, websocket.url.path)
            self.session_map[websocket] = session

            try:
                while True:
                    # Receive either text or binary message
                    data = await websocket.receive()
                    
                    if data['type'] == 'websocket.receive':
                        if 'text' in data:
                            await session.process_text_message(data['text'])
                        elif 'bytes' in data:
                            await session.process_binary_message(data['bytes'])
            except WebSocketDisconnect:
                self.logger.info('WebSocket connection closed.')
            finally:
                await self.delete_connection(websocket)

        except Exception as e:
            self.logger.error(f'WebSocket error: {e}')
            await websocket.close(code=4000)

    async def delete_connection(self, websocket: WebSocket):
        """
        Delete the connection and associated session
        
        Args:
            websocket: WebSocket connection to delete
        """
        session = self.session_map.get(websocket)
        if session:
            try:
                await session.close()
            except Exception:
                pass
            del self.session_map[websocket]
            self.logger.info('Deleting session.')
