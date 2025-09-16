import asyncio
import logging
import json
from typing import Callable, Optional, Dict, Any
from livekit import rtc
import aiohttp
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class LiveKitAgentService:
    """
    Service that connects to existing LiveKit rooms with agents
    Uses your existing agent service to get connection details
    """
    def __init__(self, agent_service_url: Optional[str] = None):
        # Use environment variable or provided URL
        self.agent_service_url = agent_service_url or os.getenv('LIVEKIT_TOKEN_URL', 'https://lks.whilter.ai/token')
        self.livekit_ws_url = os.getenv('LIVEKIT_WS_URL', 'wss://livekit.whilter.ai')
        
        # Optional: API key and secret for additional configuration
        self.api_key = os.getenv('LIVEKIT_API_KEY')
        self.api_secret = os.getenv('LIVEKIT_API_SECRET')
        
        # Rest of the existing initialization remains the same
        self.room: Optional[rtc.Room] = None
        self.room_name: Optional[str] = None
        self.participant_identity: Optional[str] = None
        self.agent_participant: Optional[rtc.RemoteParticipant] = None
        self._listeners: Dict[str, list] = {}
        self._logger = logging.getLogger(__name__)
        self._state = 'disconnected'
        self._audio_source: Optional[rtc.AudioSource] = None
        
    def on(self, event: str, listener: Callable[..., None]) -> 'LiveKitAgentService':
        """Register an event listener"""
        if event not in self._listeners:
            self._listeners[event] = []
        self._listeners[event].append(listener)
        return self
        
    def _emit(self, event: str, *args):
        """Emit an event to all registered listeners"""
        if event in self._listeners:
            for listener in self._listeners[event]:
                try:
                    if asyncio.iscoroutinefunction(listener):
                        asyncio.create_task(listener(*args))
                    else:
                        listener(*args)
                except Exception as e:
                    self._logger.error(f"Error in event listener: {e}")
    
    async def connect_to_existing_agent(self, session_config: Dict[str, Any]) -> bool:
        """
        Connect to an existing LiveKit room with an agent
        Uses your agent service to get connection details
        
        Args:
            session_config: Configuration for the session (identity, stt, llm, tts, etc.)
            
        Returns:
            bool: True if connection successful
        """
        try:
            # Call your existing agent service to create/get room details
            connection_details = await self._get_agent_connection_details(session_config)
            
            if not connection_details:
                self._logger.error("Failed to get connection details from agent service")
                return False
            
            # Use the configured LiveKit WebSocket URL
            livekit_url = connection_details.get('livekit_url', self.livekit_ws_url)
            token = connection_details['token']
            self.room_name = connection_details['room_name']
            self.participant_identity = connection_details.get('participant_identity', f"websocket-{session_config['session_id']}")
            
            # Create room and connect
            self.room = rtc.Room()
            await self._setup_room_handlers()
            
            await self.room.connect(livekit_url, token)
            self._logger.info(f"Connected to LiveKit room: {self.room_name}")
            
            # Create and publish audio track for receiving WebSocket audio
            self._audio_source = rtc.AudioSource(sample_rate=16000, num_channels=1)
            audio_track = rtc.LocalAudioTrack.create_audio_track("websocket-audio", self._audio_source)
            await self.room.local_participant.publish_track(audio_track, rtc.TrackPublishOptions())
            
            self._state = 'connected'
            self._emit('connected')
            return True
            
        except Exception as e:
            self._logger.error(f"Failed to connect to LiveKit agent: {e}")
            self._emit('error', str(e))
            return False
    
    async def _get_agent_connection_details(self, session_config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Get connection details from your existing agent service
        
        Args:
            session_config: Session configuration
            
        Returns:
            Dictionary with connection details or None if failed
        """
        # List of potential token endpoint paths
        token_endpoints = [
            f"{self.agent_service_url}/token",
        ]

        print(f"&&&&&&&& {self.agent_service_url}")
        
        for endpoint in token_endpoints:
            try:
                async with aiohttp.ClientSession() as session:
                    # Prepare payload matching the actual token generation structure
                    payload = {
                        "identity": session_config.get('identity', f"+91{session_config['session_id']}"),
                        "metadata": {
                            "email": session_config.get('email', 'default@whilter.ai'),
                            "mobile_number": session_config.get('mobile_number', f"+91{session_config['session_id']}"),
                            "stt": session_config.get('stt', 'Self-Hosted'),
                            "llm": session_config.get('llm', 'Self-Hosted'),
                            "tts": session_config.get('tts', 'Self-Hosted'),
                            "orgId": session_config.get('orgId', 'default-org-id'),
                            # Include any additional metadata from the original configuration
                            **{k: v for k, v in session_config.get('metadata', {}).items() 
                               if k not in ['email', 'mobile_number', 'stt', 'llm', 'tts', 'orgId']}
                        }
                    }
                    
                    # Set headers similar to the successful token request
                    headers = {
                        'accept': 'application/json, text/plain, */*',
                        'accept-language': 'en-IN,en-GB;q=0.9,en;q=0.8,en-US;q=0.7'
                    }
                    
                    self._logger.info(f"Attempting to get token from endpoint: {endpoint}")
                    
                    async with session.post(endpoint, json=payload, headers=headers, timeout=10) as response:
                        if response.status == 200:
                            data = await response.json()
                            return {
                                'livekit_url': data.get('livekit_url', 'wss://livekit.whilter.ai'),  # Default if not provided
                                'token': data['token'],
                                'room_name': data['room'],
                                'participant_identity': data['identity']
                            }
                        else:
                            self._logger.warning(f"Endpoint {endpoint} returned status {response.status}")
                            continue
                        
            except Exception as e:
                self._logger.warning(f"Failed to call endpoint {endpoint}: {e}")
                continue
        
        # If no endpoint works
        self._logger.error("Failed to get connection details from any token endpoint")
        return None
    
    async def _setup_room_handlers(self):
        """Setup room event handlers"""
        
        @self.room.on("participant_connected")
        def on_participant_connected(participant: rtc.RemoteParticipant):
            self._logger.info(f"Participant connected: {participant.identity}")
            if "agent" in participant.identity.lower():
                self.agent_participant = participant
                self._logger.info("🤖 Agent participant identified")
                self._emit('agent_connected', participant)
        
        @self.room.on("participant_metadata_changed") 
        def on_metadata_changed(metadata: str, participant: rtc.RemoteParticipant):
            if participant == self.agent_participant and metadata:
                try:
                    parsed_metadata = json.loads(metadata)
                    if "agent_state" in parsed_metadata:
                        self._logger.info(f"Agent state: {parsed_metadata['agent_state']}")
                        self._emit('agent_state_changed', parsed_metadata["agent_state"])
                except json.JSONDecodeError:
                    pass
        
        @self.room.on("track_subscribed")
        def on_track_subscribed(track: rtc.RemoteTrack, publication, participant: rtc.RemoteParticipant):
            if participant == self.agent_participant and track.kind == rtc.TrackKind.KIND_AUDIO:
                self._logger.info("🔊 Subscribed to agent audio track")
                self._emit('agent_audio_track', track)
        
        @self.room.on("data_received")
        def on_data_received(data: bytes, participant: rtc.RemoteParticipant):
            if participant == self.agent_participant:
                try:
                    message = json.loads(data.decode('utf-8'))
                    self._handle_agent_message(message)
                except Exception as e:
                    self._logger.error(f"Error handling agent data: {e}")
        
        # Handle transcription messages (similar to your frontend code)
        async def handle_transcription(reader, participant_info):
            """Handle transcription data from LiveKit"""
            try:
                message_string = await reader.readAll()
                if message_string:
                    role = 'assistant' if 'agent' in participant_info.identity.lower() else 'user'
                    self._logger.info(f"📝 Transcription from {role}: {message_string}")
                    self._emit('transcription', message_string, role, participant_info.identity)
            except Exception as e:
                self._logger.error(f"Error handling transcription: {e}")
        
        # Register transcription handler (matching your frontend pattern)
        self.room.registerTextStreamHandler("lk.transcription", handle_transcription)
    
    def _handle_agent_message(self, message: Dict[str, Any]):
        """Handle messages from the agent"""
        message_type = message.get('type')
        
        if message_type == 'transcript':
            self._emit('agent_transcript', message.get('text'), message.get('confidence'))
        elif message_type == 'response':
            self._emit('agent_response', message.get('text'), message.get('disposition', 'match'))
        elif message_type == 'error':
            self._emit('agent_error', message.get('error'))
        elif message_type == 'end_session':
            self._emit('agent_end_session')
    
    async def send_audio(self, audio_data: bytes):
        """
        Send audio data to the agent via LiveKit audio track
        
        Args:
            audio_data: Raw audio bytes from WebSocket
        """
        if not self.room or self._state != 'connected' or not self._audio_source:
            self._logger.warning("Not connected to agent, cannot send audio")
            return
        
        try:
            # Convert WebSocket audio data to LiveKit audio format
            # This assumes the WebSocket sends 16kHz, 16-bit PCM mono audio
            # You may need to adjust based on your WebSocket audio format
            
            # Convert bytes to audio frame
            # Assuming 16-bit PCM, 16kHz, mono
            import numpy as np
            
            # Convert bytes to numpy array
            audio_array = np.frombuffer(audio_data, dtype=np.int16)
            
            # Convert to float32 and normalize to [-1, 1]
            audio_float = audio_array.astype(np.float32) / 32768.0
            
            # Create audio frame
            audio_frame = rtc.AudioFrame(
                data=audio_float.tobytes(),
                sample_rate=16000,
                num_channels=1,
                samples_per_channel=len(audio_float)
            )
            
            # Push to audio source
            await self._audio_source.capture_frame(audio_frame)
                
        except Exception as e:
            self._logger.error(f"Error sending audio to agent: {e}")
            self._emit('error', str(e))
    
    async def send_message(self, message: Dict[str, Any]):
        """
        Send a message to the agent
        
        Args:
            message: Message to send to agent
        """
        if not self.room or self._state != 'connected':
            return
        
        try:
            await self.room.local_participant.publish_data(
                json.dumps(message).encode('utf-8'),
                reliable=True
            )
        except Exception as e:
            self._logger.error(f"Error sending message to agent: {e}")
    
    async def send_dtmf(self, digit: str):
        """Send DTMF digit to the agent"""
        await self.send_message({
            'type': 'dtmf',
            'digit': digit,
            'timestamp': asyncio.get_event_loop().time()
        })
    
    async def send_user_input(self, text: str):
        """Send user text input to agent"""
        await self.send_message({
            'type': 'user_input',
            'text': text,
            'timestamp': asyncio.get_event_loop().time()
        })
    
    async def start_session(self):
        """Send session start message to agent"""
        await self.send_message({
            'type': 'start_session',
            'timestamp': asyncio.get_event_loop().time()
        })
    
    async def disconnect(self):
        """Disconnect from the LiveKit room"""
        if self.room:
            await self.room.disconnect()
            self.room = None
            self.agent_participant = None
            self._audio_source = None
            self._state = 'disconnected'
            self._emit('disconnected')
    
    def get_state(self) -> str:
        """Get current connection state"""
        return self._state


class AgentBotResponse:
    """Response from LiveKit agent"""
    def __init__(self, text: str, disposition: str = 'match', confidence: float = 1.0):
        self.text = text
        self.disposition = disposition
        self.confidence = confidence
        self.audio_track: Optional[rtc.RemoteTrack] = None
        self.end_session = False
    
    def with_audio_track(self, track: rtc.RemoteTrack) -> 'AgentBotResponse':
        self.audio_track = track
        return self
    
    def with_end_session(self, end_session: bool) -> 'AgentBotResponse':
        self.end_session = end_session
        return self


class AgentBotResource:
    """Bot resource that uses existing LiveKit agent"""
    def __init__(self, client_service: LiveKitAgentService):
        self.client_service = client_service
        self._response_queue = asyncio.Queue()
        self._initial_response_received = False
        
        # Setup event handlers
        self.client_service.on('agent_response', self._handle_agent_response)
        self.client_service.on('transcription', self._handle_transcription)
        self.client_service.on('agent_error', self._handle_agent_error)
        self.client_service.on('agent_end_session', self._handle_end_session)
    
    def _handle_agent_response(self, text: str, disposition: str = 'match'):
        """Handle response from agent"""
        response = AgentBotResponse(text, disposition)
        asyncio.create_task(self._response_queue.put(response))
    
    def _handle_transcription(self, text: str, role: str, identity: str):
        """Handle transcription from agent"""
        if role == 'assistant':
            # This is agent speaking, treat as response
            response = AgentBotResponse(text)
            asyncio.create_task(self._response_queue.put(response))
    
    def _handle_agent_error(self, error: str):
        """Handle error from agent"""
        response = AgentBotResponse(f"I'm sorry, there was an error: {error}", 'no_match', 0.0).with_end_session(True)
        asyncio.create_task(self._response_queue.put(response))
    
    def _handle_end_session(self):
        """Handle session end from agent"""
        response = AgentBotResponse("Thank you for using our service. Goodbye!", 'match', 1.0).with_end_session(True)
        asyncio.create_task(self._response_queue.put(response))
    
    async def get_initial_response(self) -> AgentBotResponse:
        """Get initial response from agent"""
        # Start the agent session
        await self.client_service.start_session()
        
        # Wait for initial response
        try:
            response = await asyncio.wait_for(self._response_queue.get(), timeout=10.0)
            self._initial_response_received = True
            return response
        except asyncio.TimeoutError:
            return AgentBotResponse("Hello! I'm your voice assistant. How can I help you?")
    
    async def get_bot_response(self, data: str) -> AgentBotResponse:
        """Get response from agent based on input"""
        # Send user input to agent
        await self.client_service.send_user_input(data)
        
        # Wait for agent response
        try:
            response = await asyncio.wait_for(self._response_queue.get(), timeout=30.0)
            return response
        except asyncio.TimeoutError:
            return AgentBotResponse("I'm sorry, I didn't receive a response. Please try again.", 'no_match', 0.5).with_end_session(True)


class AgentBotService:
    """Service that connects to existing LiveKit agents"""
    def __init__(self, agent_service_url: str):
        self.agent_service_url = agent_service_url
    
    async def get_bot_if_exists(self, connection_url: str, input_variables: Dict[str, Any]) -> Optional[AgentBotResource]:
        """Get agent bot resource by connecting to existing agent service"""
        try:
            client_service = LiveKitAgentService(self.agent_service_url)
            
            # Prepare session configuration
            session_config = {
                'session_id': input_variables.get('session_id', 'default'),
                'identity': input_variables.get('identity', f"+91{input_variables.get('session_id', 'default')}"),
                'email': input_variables.get('email', 'default@whilter.ai'),
                'mobile_number': input_variables.get('mobile_number', f"+91{input_variables.get('session_id', 'default')}"),
                'stt': input_variables.get('stt', 'Self-Hosted'),
                'llm': input_variables.get('llm', 'Self-Hosted'),
                'tts': input_variables.get('tts', 'Self-Hosted'),
                'orgId': input_variables.get('orgId', 'default-org-id'),
                'metadata': {
                    'connection_url': connection_url,
                    **{k: v for k, v in input_variables.items() 
                       if k not in ['session_id', 'identity', 'email', 'mobile_number', 'stt', 'llm', 'tts', 'orgId']}
                }
            }
            
            # Connect to existing agent
            if await client_service.connect_to_existing_agent(session_config):
                return AgentBotResource(client_service)
            else:
                return None
                
        except Exception as e:
            logging.getLogger(__name__).error(f"Failed to create agent bot: {e}")
            return None