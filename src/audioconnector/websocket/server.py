import logging
from fastapi import WebSocket, WebSocketDisconnect
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

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
        # Get LiveKit URL from environment, with a default fallback
        self.livekit_url = os.getenv('LIVEKIT_TOKEN_URL', 'https://lks.whilter.ai/token').replace('/token', '')

    async def handle_websocket(self, websocket: WebSocket):
        """
        Handle incoming WebSocket connection
        
        Args:
            websocket: Incoming WebSocket connection
        """
        session = None
        try:
            # Verify request signature
            verify_result = await verify_websocket_signature(websocket, self.secret_service)
            
            if verify_result.get('code') != 'VERIFIED':
                self.logger.warning(f"Authentication failed: {verify_result.get('reason', 'Unknown reason')}")
                # Use a try-except to handle potential errors during close
                try:
                    await websocket.close(code=4001)
                except Exception as close_error:
                    self.logger.error(f"Error closing websocket: {close_error}")
                return

            await websocket.accept()
            self.logger.info('Authentication was successful.')

            # Create session
            session_id = websocket.headers.get('audiohook-session-id', '')
            session = Session(
                websocket, 
                session_id, 
                livekit_url=self.livekit_url
            )
            self.session_map[websocket] = session

            while True:
                try:
                    # Receive either text or binary message
                    data = await websocket.receive()
                    
                    if data['type'] == 'websocket.receive':
                        if 'text' in data:
                            await session.process_text_message(data['text'])
                        elif 'bytes' in data:
                            await session.process_binary_message(data['bytes'])
                except WebSocketDisconnect:
                    self.logger.info('WebSocket connection closed by client.')
                    break

        except Exception as e:
            self.logger.error(f'WebSocket error: {e}')
            # Ensure we don't try to close an already closed connection
            try:
                if websocket.client_state != websocket.DISCONNECTED:
                    await websocket.close(code=4000)
            except Exception as close_error:
                self.logger.error(f"Error during websocket close: {close_error}")
        
        finally:
            # Always attempt to delete the connection, even if there was an error
            if session and websocket in self.session_map:
                try:
                    await self.delete_connection(websocket)
                except Exception as delete_error:
                    self.logger.error(f"Error deleting connection: {delete_error}")

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
            except Exception as close_error:
                self.logger.error(f"Error closing session: {close_error}")
            
            try:
                del self.session_map[websocket]
            except Exception as del_error:
                self.logger.error(f"Error removing session from map: {del_error}")
            
            self.logger.info('Deleting session.')
