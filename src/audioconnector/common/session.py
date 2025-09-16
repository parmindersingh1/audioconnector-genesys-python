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
from ..services.livekit_agent_service import AgentBotService, AgentBotResource, AgentBotResponse, LiveKitAgentService
from ..services.dtmf_service import DTMFService  # Keep DTMF service for local processing

class Session:
    def __init__(self, ws: WebSocket, session_id: str, 
                 livekit_url: str, 
                 email: Optional[str] = None,
                 mobile_number: Optional[str] = None,
                 stt: str = 'Self-Hosted',
                 llm: str = 'Self-Hosted',
                 tts: str = 'Self-Hosted',
                 org_id: Optional[str] = None):
        self.MAXIMUM_BINARY_MESSAGE_SIZE = 64000
        self.disconnecting = False
        self.closed = False
        self.ws = ws

        self.message_handler_registry = MessageHandlerRegistry()
        
        # Prepare input variables for LiveKit agent service
        self.input_variables = {
            'session_id': session_id,
            'email': email,
            'mobile_number': mobile_number,
            'stt': stt,
            'llm': llm,
            'tts': tts,
            'orgId': org_id
        }
        
        # Replace bot_service with agent-based service
        self.bot_service = AgentBotService(livekit_url)
        
        # Remove ASR service - handled by LiveKit agent
        self.agent_service: Optional[LiveKitAgentService] = None
        
        # Keep DTMF service for local DTMF processing if needed
        self.dtmf_service: Optional[DTMFService] = None
        
        self.client_session_id = session_id
        self.conversation_id: Optional[str] = None
        self.last_server_sequence_number = 0
        self.last_client_sequence_number = 0
        self.selected_media: Optional[MediaParameter] = None
        self.selected_bot: Optional[AgentBotResource] = None
        self.is_capturing_dtmf = False
        self.is_audio_playing = False
        self.logger = logging.getLogger(__name__)

    async def close(self):
        """Close the WebSocket connection and disconnect from agent"""
        if self.closed:
            return

        # Disconnect from LiveKit agent
        if self.agent_service:
            await self.agent_service.disconnect()

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
        # Add session ID for agent identification
        self.input_variables['session_id'] = self.client_session_id

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
        """Check if bot exists and connect to LiveKit agent"""
        # Use the LiveKit URL or a connection URL from input variables
        connection_url = self.input_variables.get('connection_url', 'https://lks.whilter.ai')
        
        selected_bot = await self.bot_service.get_bot_if_exists(connection_url, self.input_variables)
        self.selected_bot = selected_bot
        
        if self.selected_bot:
            # Get the agent service reference from the bot resource
            self.agent_service = self.selected_bot.agent_service
            
            # Setup agent event handlers for this session
            self.agent_service.on('agent_transcript', self._handle_agent_transcript)
            self.agent_service.on('agent_audio_track', self._handle_agent_audio)
            self.agent_service.on('agent_error', self._handle_agent_error)
            self.agent_service.on('disconnected', self._handle_agent_disconnected)
        
        return self.selected_bot is not None

    async def process_bot_start(self):
        """Process bot start"""
        if not self.selected_bot:
            return

        print("^^^^^^^^^^^^^^^^^^")    

        response = await self.selected_bot.get_initial_response()
        if response.text:
            await self.send_turn_response('match', response.text, response.confidence)

        # For LiveKit agents, audio is handled through audio tracks, not direct bytes
        if response.audio_track:
            # Audio will be streamed through the LiveKit connection
            # We might need to notify the WebSocket client about audio availability
            pass

    async def process_binary_message(self, data: bytes):
        """
        Process incoming binary message (audio) - send to LiveKit agent
        
        Args:
            data: Binary audio data from WebSocket
        """
        if self.disconnecting or self.closed or not self.selected_bot:
            return

        # Ignore audio if capturing DTMF
        if self.is_capturing_dtmf:
            return

        # Ignore input while audio is playing
        if self.is_audio_playing:
            return

        # Send audio data to LiveKit agent instead of local ASR
        if self.agent_service and self.agent_service.get_state() == 'connected':
            await self.agent_service.send_audio(data)

    def process_dtmf(self, digit: str):
        """
        Process DTMF digit - can send to agent or handle locally
        
        Args:
            digit: DTMF digit received
        """
        if self.disconnecting or self.closed or not self.selected_bot:
            return

        # Ignore input while audio is playing
        if self.is_audio_playing:
            return

        # Send DTMF to LiveKit agent
        if self.agent_service and self.agent_service.get_state() == 'connected':
            asyncio.create_task(self.agent_service.send_dtmf(digit))
        else:
            # Fallback to local DTMF processing
            self._process_local_dtmf(digit)

    def _process_local_dtmf(self, digit: str):
        """Process DTMF locally if agent is not available"""
        if not self.is_capturing_dtmf:
            self.is_capturing_dtmf = True

        if not self.dtmf_service or self.dtmf_service.get_state() == 'Complete':
            self.dtmf_service = DTMFService()
            self.dtmf_service.on('error', self._handle_dtmf_error)
            self.dtmf_service.on('final-digits', self._handle_final_dtmf)

        self.dtmf_service.process_digit(digit)

    # Agent event handlers
    async def _handle_transcription(self, text: str, role: str, identity: str):
        """Handle transcription from LiveKit agent"""
        self.logger.info(f"Transcription from {role}: {text}")
        # You might want to emit this as an intermediate transcript event
        # or forward it to the WebSocket client

    async def _handle_agent_audio(self, audio_track):
        """Handle audio track from LiveKit agent"""
        self.logger.info("Agent audio track available")
        # The audio will be handled by the LiveKit client
        # You might want to notify the WebSocket about audio availability

    async def _handle_agent_error(self, error: str):
        """Handle error from LiveKit agent"""
        self.logger.error(f"Agent error: {error}")
        await self.send_disconnect('error', f'Agent error: {error}', {})

    async def _handle_agent_disconnected(self):
        """Handle agent disconnection"""
        self.logger.info("Agent disconnected")
        await self.send_disconnect('completed', 'Agent session ended', {})

    # Legacy DTMF handlers (fallback)
    async def _handle_dtmf_error(self, error: Any):
        """Handle DTMF service errors"""
        message = 'Error during DTMF Capture.'
        self.logger.error(f"{message}: {error}")
        await self.send_disconnect('error', message, {})

    async def _handle_final_dtmf(self, digits: str):
        """Handle final DTMF digits"""
        if not self.selected_bot:
            return

        response = await self.selected_bot.get_bot_response(digits)
        
        if response.text:
            await self.send_turn_response('match', response.text, response.confidence)

        if response.end_session:
            await self.send_disconnect('completed', '', {})

        self.is_capturing_dtmf = False