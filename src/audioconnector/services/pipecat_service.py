import asyncio
import audioop
import base64
import io
import websockets
import time
from typing import Optional
from pipecat.frames.frames import (
    OutputAudioRawFrame, EndFrame, InputTransportMessageFrame, 
    TTSAudioRawFrame, InputAudioRawFrame
)
from pipecat.serializers.protobuf import ProtobufFrameSerializer

class PipecatService:
    def __init__(self, session):
        self.session = session
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.serializer = ProtobufFrameSerializer()
        self.receive_task: Optional[asyncio.Task] = None
        self._pipecat_url = "ws://localhost:7860/ws"
        self._genesys_sample_rate = 8000
        self._pipecat_sample_rate = 16000
        self._channels = 1
        self._sample_width = 2  # 16-bit
        self.logger = session.logger
        
        # Audio buffering with dynamic rate control
        self.audio_buffer = bytearray()
        self.audio_send_task = None
        
        # Dynamic rate limiting
        self.base_send_interval = 0.100  # Start at 100ms (conservative)
        self.current_send_interval = self.base_send_interval
        self.min_send_interval = 0.080  # Fastest we'll go
        self.max_send_interval = 0.200  # Slowest (if rate limited)
        
        # Rate limit detection
        self.rate_limit_count = 0
        self.last_rate_limit_time = 0
        self.successful_sends = 0
        
        # Configuration
        self.chunk_size = 800  # 100ms at 8kHz 
        self.max_buffer_size = 40000  # 5 seconds max buffer
        
        # Statistics
        self.total_bytes_sent = 0
        self.send_start_time = None

    async def start(self):
        try:
            self.ws = await websockets.connect(self._pipecat_url)
            self.logger.info("Connected to Pipecat WebSocket server.")
            self.receive_task = asyncio.create_task(self._receive_loop())
            self._start_audio_sender()
        except Exception as e:
            self.logger.error(f"Failed to connect to Pipecat: {e}")
            await self.session.send_disconnect('error', 'Failed to connect to bot service', {})

    def _start_audio_sender(self):
        """Start periodic audio sender task"""
        if self.audio_send_task is None or self.audio_send_task.done():
            self.audio_send_task = asyncio.create_task(self._audio_send_loop())
            self.send_start_time = time.time()

    async def _audio_send_loop(self):
        """Continuously send audio chunks with adaptive rate limiting"""
        try:
            while True:
                await asyncio.sleep(self.current_send_interval)
                
                if self.session.disconnecting or self.session.closed:
                    break
                
                # Only send one chunk per interval
                if len(self.audio_buffer) >= self.chunk_size:
                    chunk = bytes(self.audio_buffer[:self.chunk_size])
                    del self.audio_buffer[:self.chunk_size]
                    
                    try:
                        await self.session.send_audio(chunk)
                        self.total_bytes_sent += len(chunk)
                        self.successful_sends += 1
                        
                        # Log periodically
                        if self.successful_sends % 50 == 0:
                            elapsed = time.time() - self.send_start_time
                            rate = self.total_bytes_sent / elapsed if elapsed > 0 else 0
                            self.logger.info(
                                f"Audio stats: {self.successful_sends} chunks sent, "
                                f"{self.total_bytes_sent} bytes, "
                                f"{rate:.0f} bytes/sec, "
                                f"interval: {self.current_send_interval*1000:.0f}ms, "
                                f"buffer: {len(self.audio_buffer)} bytes"
                            )
                        
                        # Adaptive rate: gradually speed up if no issues
                        if self.successful_sends % 20 == 0 and self.rate_limit_count == 0:
                            self._adjust_send_rate(faster=True)
                        
                    except Exception as e:
                        self.logger.error(f"Error sending audio chunk: {e}")
                        self._handle_send_error()
                        
        except asyncio.CancelledError:
            self.logger.info("Audio sender task cancelled")
        except Exception as e:
            self.logger.error(f"Error in audio send loop: {e}")

    def _adjust_send_rate(self, faster=False):
        """Dynamically adjust send rate based on success/failure"""
        old_interval = self.current_send_interval
        
        if faster:
            # Speed up by 5ms, but don't go below minimum
            self.current_send_interval = max(
                self.min_send_interval,
                self.current_send_interval - 0.005
            )
        else:
            # Slow down by 20ms when rate limited
            self.current_send_interval = min(
                self.max_send_interval,
                self.current_send_interval + 0.020
            )
        
        if old_interval != self.current_send_interval:
            self.logger.info(
                f"Adjusted send rate: {old_interval*1000:.0f}ms → "
                f"{self.current_send_interval*1000:.0f}ms"
            )

    def _handle_send_error(self):
        """Handle send errors by slowing down"""
        self.rate_limit_count += 1
        self.last_rate_limit_time = time.time()
        self.successful_sends = 0  # Reset success counter
        self._adjust_send_rate(faster=False)

    async def _receive_loop(self):
        """Receive frames from Pipecat and forward audio to Genesys."""
        try:
            while True:
                if self.session.disconnecting or self.session.closed:
                    self.logger.info("Session closed; exiting receive loop.")
                    return
                    
                message = await self.ws.recv()
                frame = await self.serializer.deserialize(message)
                
                self.logger.debug(f"Received frame of type: {type(frame).__name__}")
                
                if isinstance(frame, EndFrame):
                    self.logger.info("Received EndFrame from Pipecat; disconnecting.")
                    await self._flush_remaining_audio()
                    await self.session.send_disconnect('completed', '', {})
                    return
                
                elif isinstance(frame, InputTransportMessageFrame):
                    msg_type = frame.message.get('type')
                    msg_data = frame.message.get('data', {})
                    
                    # Handle transcripts (user and bot)
                    if msg_type == 'user-transcription':
                        text = msg_data.get('text', '')
                        is_final = msg_data.get('final', False)
                        if text:
                            await self.session.on_pipecat_transcript(text, is_final, 'user')
                    
                    elif msg_type == 'bot-transcription':
                        text = msg_data.get('text', '')
                        if text:
                            await self.session.on_pipecat_transcript(text, True, 'agent')
                    
                    # Handle bot speaking state
                    elif msg_type == 'bot-started-speaking':
                        await self.session.on_pipecat_bot_started_speaking()
                    
                    elif msg_type == 'bot-stopped-speaking':
                        await self.session.on_pipecat_bot_stopped_speaking()
                    
                    # Handle audio from bot
                    elif msg_type == 'bot-tts-audio':
                        if self.session.disconnecting or self.session.closed:
                            continue
                            
                        audio_b64 = msg_data.get('audio')
                        if not audio_b64:
                            self.logger.warning("bot-tts-audio frame missing audio data")
                            continue
                        try:
                            pcm_pipecat = base64.b64decode(audio_b64)
                            sample_rate = msg_data.get('sample_rate', self._pipecat_sample_rate)
                            num_channels = msg_data.get('num_channels', self._channels)
                            
                            await self._process_and_buffer_audio(pcm_pipecat, sample_rate, num_channels)
                        except Exception as e:
                            self.logger.error(f"Error processing bot-tts-audio: {e}")
                            continue
                    
                    elif msg_type == 'error' and msg_data.get('code') == 429:
                        self.logger.warning(
                            f"⚠️  Genesys rate limit hit (#{self.rate_limit_count + 1}): "
                            f"{msg_data.get('message')} - slowing down"
                        )
                        self._handle_send_error()
                
                elif isinstance(frame, InputAudioRawFrame):
                    if self.session.disconnecting or self.session.closed:
                        continue
                        
                    pcm_pipecat = frame.audio
                    sample_rate = frame.sample_rate or self._pipecat_sample_rate
                    num_channels = getattr(frame, 'num_channels', self._channels)
                    
                    try:
                        await self._process_and_buffer_audio(pcm_pipecat, sample_rate, num_channels)
                    except Exception as e:
                        self.logger.error(f"Error processing InputAudioRawFrame: {e}")
                        continue
                
                elif isinstance(frame, (TTSAudioRawFrame, OutputAudioRawFrame)):
                    if self.session.disconnecting or self.session.closed:
                        continue
                        
                    pcm_pipecat = frame.audio
                    sample_rate = frame.sample_rate or self._pipecat_sample_rate
                    num_channels = getattr(frame, 'num_channels', self._channels)
                    
                    try:
                        await self._process_and_buffer_audio(pcm_pipecat, sample_rate, num_channels)
                    except Exception as e:
                        self.logger.error(f"Error processing legacy TTS: {e}")
                        continue
                
        except websockets.exceptions.ConnectionClosed:
            self.logger.info("Pipecat WebSocket closed.")
        except Exception as e:
            self.logger.error(f"Error in Pipecat receive loop: {e}")
            await self.session.send_disconnect('error', 'Bot service error', {})

    async def _process_and_buffer_audio(self, pcm_data: bytes, sample_rate: int, num_channels: int):
        """Process audio and add to buffer - send happens in separate loop"""
        try:
            # Step 1: Mix to mono if needed
            if num_channels > 1:
                pcm_data = await self._mix_to_mono(pcm_data, num_channels)
            
            # Step 2: Resample to Genesys rate
            if sample_rate != self._genesys_sample_rate:
                pcm_data = await self._resample_audio(pcm_data, sample_rate, self._genesys_sample_rate)
            
            # Step 3: Convert to G.711 u-law
            g711_bytes = audioop.lin2ulaw(pcm_data, self._sample_width)
            
            # Step 4: Add to buffer with overflow protection
            if len(self.audio_buffer) + len(g711_bytes) > self.max_buffer_size:
                overflow = (len(self.audio_buffer) + len(g711_bytes)) - self.max_buffer_size
                del self.audio_buffer[:overflow]
                self.logger.warning(f"Audio buffer overflow, dropped {overflow} bytes")
            
            self.audio_buffer.extend(g711_bytes)
            
        except Exception as e:
            self.logger.error(f"Error processing audio: {e}", exc_info=True)

    async def _flush_remaining_audio(self):
        """Flush any remaining audio in buffer"""
        self.logger.info(f"Flushing {len(self.audio_buffer)} remaining bytes")
        
        while len(self.audio_buffer) > 0:
            chunk_size = min(len(self.audio_buffer), self.chunk_size)
            chunk = bytes(self.audio_buffer[:chunk_size])
            del self.audio_buffer[:chunk_size]
            
            try:
                await self.session.send_audio(chunk)
                await asyncio.sleep(0.050)  # 50ms between final chunks
            except Exception as e:
                self.logger.error(f"Error flushing audio: {e}")
                break

    async def _mix_to_mono(self, pcm_multi: bytes, num_channels: int) -> bytes:
        """Mix multi-channel audio to mono with proper averaging."""
        try:
            samples_per_channel = len(pcm_multi) // (num_channels * self._sample_width)
            pcm_mono = bytearray()
            
            for i in range(samples_per_channel):
                offset = i * num_channels * self._sample_width
                samples = []
                
                for j in range(num_channels):
                    sample_offset = offset + j * self._sample_width
                    sample_bytes = pcm_multi[sample_offset:sample_offset + self._sample_width]
                    sample = int.from_bytes(sample_bytes, 'little', signed=True)
                    samples.append(sample)
                
                # Average and clamp to prevent overflow
                avg_sample = sum(samples) // num_channels
                avg_sample = max(-32768, min(32767, avg_sample))
                pcm_mono.extend(avg_sample.to_bytes(self._sample_width, 'little', signed=True))
            
            return bytes(pcm_mono)
        except Exception as e:
            self.logger.error(f"Mono mix error: {e}")
            return pcm_multi

    async def send_user_audio(self, g711_bytes: bytes):
        """Send user audio to Pipecat."""
        if not self.ws:
            self.logger.warning("Pipecat not connected.")
            return
        try:
            pcm_genesys = audioop.ulaw2lin(g711_bytes, self._sample_width)
            
            # Resample if needed
            if self._genesys_sample_rate != self._pipecat_sample_rate:
                pcm_pipecat = await self._resample_audio(pcm_genesys, self._genesys_sample_rate, self._pipecat_sample_rate)
            else:
                pcm_pipecat = pcm_genesys
            
            frame = OutputAudioRawFrame(
                audio=pcm_pipecat,
                sample_rate=self._pipecat_sample_rate,
                num_channels=self._channels
            )
            serialized = await self.serializer.serialize(frame)
            await self.ws.send(serialized)
        except Exception as e:
            self.logger.error(f"Error sending audio to Pipecat: {e}")

    async def _resample_audio(self, pcm_in: bytes, input_rate: int, output_rate: int) -> bytes:
        """Resample audio using audioop."""
        if input_rate == output_rate:
            return pcm_in
        
        try:
            resampled, _ = audioop.ratecv(pcm_in, self._sample_width, 1, input_rate, output_rate, None)
            return resampled
        except Exception as e:
            self.logger.error(f"Resampling error ({input_rate}Hz -> {output_rate}Hz): {e}")
            return pcm_in

    async def stop(self):
        """Stop the Pipecat service and cleanup."""
        # Cancel audio sender
        if self.audio_send_task:
            self.audio_send_task.cancel()
            try:
                await self.audio_send_task
            except asyncio.CancelledError:
                pass
        
        # Flush any remaining audio
        if self.audio_buffer:
            try:
                await self._flush_remaining_audio()
            except Exception as e:
                self.logger.error(f"Error flushing audio buffer: {e}")
        
        if self.receive_task:
            self.receive_task.cancel()
            try:
                await self.receive_task
            except asyncio.CancelledError:
                pass
        
        if self.ws:
            await self.ws.close()
            self.logger.info("Pipecat connection closed.")