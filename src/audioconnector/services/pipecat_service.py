import asyncio
import audioop
import base64
import io
import websockets
import ffmpeg
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
        
        # Audio buffering and rate limiting (similar to Ultravox pattern)
        self.audio_buffer = []
        self.audio_buffer_size = 0
        self.max_audio_buffer_size = 16000  # 2 seconds at 8kHz
        self.audio_send_interval = None
        self.audio_send_rate = 100  # Send every 100ms (matching Ultravox)
        self.audio_chunk_size = 1600  # 200ms chunks at 8kHz (matching Ultravox)

    async def start(self):
        try:
            self.ws = await websockets.connect(self._pipecat_url)
            self.logger.info("Connected to Pipecat WebSocket server.")
            self.receive_task = asyncio.create_task(self._receive_loop())
            self._start_audio_processing()
        except Exception as e:
            self.logger.error(f"Failed to connect to Pipecat: {e}")
            await self.session.send_disconnect('error', 'Failed to connect to bot service', {})

    def _start_audio_processing(self):
        """Start the audio buffer processing interval."""
        if self.audio_send_interval:
            self.audio_send_interval.cancel()
        
        async def process_loop():
            while True:
                await asyncio.sleep(self.audio_send_rate / 1000.0)  # Convert ms to seconds
                await self._flush_audio_buffer()
        
        self.audio_send_interval = asyncio.create_task(process_loop())

    def _stop_audio_processing(self):
        """Stop the audio buffer processing interval."""
        if self.audio_send_interval:
            self.audio_send_interval.cancel()
            self.audio_send_interval = None
        self.audio_buffer = []
        self.audio_buffer_size = 0

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
                    # Flush any remaining buffered audio
                    await self._flush_audio_buffer(force=True)
                    await self.session.send_disconnect('completed', '', {})
                    return
                
                elif isinstance(frame, InputTransportMessageFrame):
                    msg_type = frame.message.get('type')
                    msg_data = frame.message.get('data', {})
                    self.logger.debug(f"RTVI message type: {msg_type}, data keys: {list(msg_data.keys())}")
                    
                    if msg_type == 'bot-tts-audio':
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
                        self.logger.warning(f"Genesys rate limit hit: {msg_data.get('message')}")
                        # Slow down sending
                        await asyncio.sleep(1.0)
                
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
        """Process audio and add to buffer instead of sending immediately."""
        # Step 1: Mix to mono if needed
        if num_channels > 1:
            pcm_data = await self._mix_to_mono(pcm_data, num_channels)
            self.logger.debug(f"Mixed {num_channels} channels to mono")
        
        # Step 2: Resample to Genesys rate
        pcm_genesys = await self._resample_audio(pcm_data, sample_rate, self._genesys_sample_rate)
        
        # Step 3: Convert to G.711 u-law
        g711_bytes = audioop.lin2ulaw(pcm_genesys, self._sample_width)
        
        # Step 4: Add to buffer (DON'T send immediately)
        self.audio_buffer.append(g711_bytes)
        self.audio_buffer_size += len(g711_bytes)
        
        # Step 5: If buffer is too large, flush immediately
        if self.audio_buffer_size >= self.max_audio_buffer_size:
            self.logger.warning(f"Audio buffer overflow ({self.audio_buffer_size} bytes), flushing")
            await self._flush_audio_buffer(force=True)

    async def _flush_audio_buffer(self, force=False):
        """Flush audio buffer by sending in controlled chunks."""
        if len(self.audio_buffer) == 0 or self.session.closed:
            return
        
        # Only flush if we have enough data or force is True
        if not force and self.audio_buffer_size < self.audio_chunk_size:
            return
        
        # Combine all buffered audio
        total_size = self.audio_buffer_size
        combined_buffer = bytearray(total_size)
        offset = 0
        
        for buffer in self.audio_buffer:
            combined_buffer[offset:offset + len(buffer)] = buffer
            offset += len(buffer)
        
        # Clear buffer
        self.audio_buffer = []
        self.audio_buffer_size = 0
        
        # Send in controlled chunks
        await self._send_audio_chunked(bytes(combined_buffer))

    async def _send_audio_chunked(self, audio_bytes: bytes):
        """Send audio in chunks with delays to prevent rate limiting."""
        if len(audio_bytes) <= self.audio_chunk_size:
            self.logger.info(f"Sending {len(audio_bytes)} binary bytes in 1 message")
            await self.session.send_audio(audio_bytes)
        else:
            current_position = 0
            chunk_count = 0
            
            while current_position < len(audio_bytes):
                if self.session.disconnecting or self.session.closed:
                    return
                
                end_position = min(current_position + self.audio_chunk_size, len(audio_bytes))
                chunk = audio_bytes[current_position:end_position]
                
                self.logger.info(f"Sending {len(chunk)} binary bytes in chunked message (chunk {chunk_count + 1})")
                await self.session.send_audio(chunk)
                
                current_position = end_position
                chunk_count += 1
                
                # Add delay between chunks to prevent rate limiting
                if current_position < len(audio_bytes):
                    # Calculate delay based on audio duration
                    chunk_duration_ms = (len(chunk) / self._genesys_sample_rate) * 1000
                    delay_ms = max(10, chunk_duration_ms * 0.9)  # 90% of actual duration
                    self.logger.debug(f"Waiting {delay_ms:.1f}ms before next chunk")
                    await asyncio.sleep(delay_ms / 1000.0)

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
            pcm_pipecat = await self._resample_audio(pcm_genesys, self._genesys_sample_rate, self._pipecat_sample_rate)
            frame = OutputAudioRawFrame(
                audio=pcm_pipecat,
                sample_rate=self._pipecat_sample_rate,
                num_channels=self._channels
            )
            serialized = await self.serializer.serialize(frame)
            await self.ws.send(serialized)
            self.logger.debug(f"Sent {len(serialized)} bytes to Pipecat.")
        except Exception as e:
            self.logger.error(f"Error sending audio to Pipecat: {e}")

    async def _resample_audio(self, pcm_in: bytes, input_rate: int, output_rate: int) -> bytes:
        """Resample audio using audioop (FFmpeg optional)."""
        if input_rate == output_rate:
            return pcm_in
        
        try:
            # Use audioop for simple and reliable resampling
            resampled, _ = audioop.ratecv(pcm_in, self._sample_width, 1, input_rate, output_rate, None)
            self.logger.debug(f"Resampled {len(pcm_in)} bytes ({input_rate}Hz) to {len(resampled)} bytes ({output_rate}Hz)")
            return resampled
        except Exception as e:
            self.logger.error(f"Resampling error ({input_rate}Hz -> {output_rate}Hz): {e}")
            return pcm_in

    async def stop(self):
        """Stop the Pipecat service and cleanup."""
        # Stop audio processing
        self._stop_audio_processing()
        
        # Flush any remaining audio
        if self.audio_buffer:
            try:
                await self._flush_audio_buffer(force=True)
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