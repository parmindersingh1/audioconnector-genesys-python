import json
import logging
from typing import Dict, Any, Optional, Union, List

from fastapi import WebSocket

from ..protocol.core import JsonStringMap, MediaParameter
from ..protocol.message import (
    ClientMessage, DisconnectParameters, DisconnectReason, 
    EventParameters, ServerMessage, ServerMessageType, 
    SelectParametersForType
)
from ..protocol.voice_bots import (
    BotTurnDisposition, EventEntityBargeIn, 
    EventEntityBotTurnResponse
)
from ..websocket.message_handlers.message_handler_registry import MessageHandlerRegistry
from ..services.pipecat_service import PipecatService

class Session:
    def __init__(self, ws: WebSocket, session_id: str, url: str):
        self.MAXIMUM_BINARY_MESSAGE_SIZE = 64000
        self.disconnecting = False
        self.closed = False
        self.ws = ws

        self.message_handler_registry = MessageHandlerRegistry()
        self.pipecat_service: Optional[PipecatService] = None
        self.url = url
        self.client_session_id = session_id
        self.conversation_id: Optional[str] = None
        self.last_server_sequence_number = 0
        self.last_client_sequence_number = 0
        self.input_variables: JsonStringMap = {}
        self.selected_media: Optional[MediaParameter] = None
        self.is_capturing_dtmf = False
        self.is_audio_playing = False
        self.logger = logging.getLogger(__name__)

    async def close(self):
        """Close the WebSocket connection"""
        if self.closed:
            return

        if self.pipecat_service:
            await self.pipecat_service.stop()

        try:
            await self.ws.close()
        except Exception:
            pass

        self.closed = True

    def set_conversation_id(self, conversation_id: str):
        """Set the conversation ID"""
        self.conversation_id = conversation_id

    def set_input_variables(self, input_variables: JsonStringMap):
        """Set input variables"""
        self.input_variables = input_variables

    def set_selected_media(self, selected_media: MediaParameter):
        """Set selected media"""
        self.selected_media = selected_media

    def set_is_audio_playing(self, is_audio_playing: bool):
        """Set audio playing status"""
        self.is_audio_playing = is_audio_playing

    async def process_text_message(self, data: str):
        """Process incoming text message"""
        if self.closed:
            return

        try:
            message = json.loads(data)
        except json.JSONDecodeError:
            self.logger.error("Invalid JSON message")
            await self.send_disconnect('error', 'Invalid message format', {})
            return

        # Validate sequence numbers and session ID
        if message.get('seq') != self.last_client_sequence_number + 1:
            self.logger.error(f"Invalid client sequence number: {message.get('seq')}")
            await self.send_disconnect('error', 'Invalid client sequence number', {})
            return

        self.last_client_sequence_number = message.get('seq', 0)

        if message.get('serverseq', 0) > self.last_server_sequence_number:
            self.logger.error(f"Invalid server sequence number: {message.get('serverseq')}")
            await self.send_disconnect('error', 'Invalid server sequence number', {})
            return

        if message.get('id') != self.client_session_id:
            self.logger.error(f"Invalid Client Session ID: {message.get('id')}")
            await self.send_disconnect('error', 'Invalid ID specified', {})
            return

        # Find and execute message handler
        handler = self.message_handler_registry.get_handler(message.get('type'))
        if not handler:
            self.logger.error(f"Cannot find a message handler for '{message.get('type')}'")
            return

        await handler.handle_message(message, self)

    def create_message(self, type: ServerMessageType, parameters: Any) -> ServerMessage:
        """Create a server message"""
        # Increment last_server_sequence_number before creating the message
        self.last_server_sequence_number += 1
        
        message = {
            'id': self.client_session_id,
            'version': '2',
            'seq': self.last_server_sequence_number,
            'clientseq': self.last_client_sequence_number,
            'type': type,
            'parameters': parameters
        }
        return message

    async def send(self, message: ServerMessage):
        """Send a message over WebSocket"""
        if message['type'] == 'event':
            self.logger.info(f"Sending an event message: {message['parameters']['entities'][0]['type']}")
        else:
            self.logger.info(f"Sending a {message['type']} message")
        
        await self.ws.send_text(json.dumps(message))

    async def send_audio(self, bytes_data: bytes):
        """Send audio data, potentially chunked"""
        if len(bytes_data) <= self.MAXIMUM_BINARY_MESSAGE_SIZE:
            self.logger.info(f"Sending {len(bytes_data)} binary bytes in 1 message")
            await self.ws.send_bytes(bytes_data)
        else:
            current_position = 0
            while current_position < len(bytes_data):
                send_bytes = bytes_data[current_position:current_position + self.MAXIMUM_BINARY_MESSAGE_SIZE]
                self.logger.info(f"Sending {len(send_bytes)} binary bytes in chunked message")
                await self.ws.send_bytes(send_bytes)
                current_position += self.MAXIMUM_BINARY_MESSAGE_SIZE

    async def send_barge_in(self):
        """Send barge-in event"""
        barge_in_event: EventEntityBargeIn = {
            'type': 'barge_in',
            'data': {}
        }
        message = self.create_message('event', {
            'entities': [barge_in_event]
        })
        await self.send(message)

    async def send_turn_response(self, disposition: BotTurnDisposition, text: Optional[str], confidence: Optional[float]):
        """Send bot turn response event"""
        bot_turn_response_event: EventEntityBotTurnResponse = {
            'type': 'bot_turn_response',
            'data': {
                'disposition': disposition,
                'text': text,
                'confidence': confidence
            }
        }
        message = self.create_message('event', {
            'entities': [bot_turn_response_event]
        })
        await self.send(message)

    async def send_disconnect(self, reason: DisconnectReason, info: str, output_variables: JsonStringMap):
        """Send disconnect message"""
        self.disconnecting = True
        
        disconnect_parameters: DisconnectParameters = {
            'reason': reason,
            'info': info,
            'outputVariables': output_variables
        }
        message = self.create_message('disconnect', disconnect_parameters)
        await self.send(message)

    async def send_closed(self):
        """Send closed message"""
        message = self.create_message('closed', {})
        await self.send(message)

    async def check_if_bot_exists(self) -> bool:
        """Check if bot exists"""
        return True  # Pipecat always "exists"

    async def process_bot_start(self):
        """Process bot start"""
        if not self.pipecat_service:
            self.pipecat_service = PipecatService(self)
        await self.pipecat_service.start()

    async def process_binary_message(self, data: bytes):
        """
        Process incoming binary message (audio)
        
        Args:
            data: Binary audio data
        """
        if self.disconnecting or self.closed:
            return

        # Ignore input while audio is playing
        if self.is_audio_playing:
            return

        if self.pipecat_service:
            await self.pipecat_service.send_user_audio(data)
        else:
            self.logger.warning("Pipecat not started; ignoring audio.")

    def process_dtmf(self, digit: str):
        """
        Process DTMF digit
        
        Args:
            digit: DTMF digit received
        """
        self.logger.info(f"Ignoring DTMF digit: {digit}")