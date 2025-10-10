import asyncio
import audioop
import io
import websockets
import ffmpeg
from typing import Optional
from pipecat.frames.frames import OutputAudioRawFrame, EndFrame
from pipecat.serializers.protobuf import ProtobufFrameSerializer

class PipecatService:
    """
    Service for connecting to Pipecat WebSocket server and bridging audio.
    Uses pipecat-ai for protobuf frame serialization.
    """
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
        self.logger = session.logger  # Reuse session logger

    async def start(self):
        """Connect to Pipecat WS and start receive loop."""
        try:
            self.ws = await websockets.connect(self._pipecat_url)
            self.logger.info("Connected to Pipecat WebSocket server.")
            self.receive_task = asyncio.create_task(self._receive_loop())
        except Exception as e:
            self.logger.error(f"Failed to connect to Pipecat: {e}")
            await self.session.send_disconnect('error', 'Failed to connect to bot service', {})

    async def _receive_loop(self):
        """Receive frames from Pipecat and forward audio to Genesys."""
        try:
            while True:
                message = await self.ws.recv()
                frame = await self.serializer.deserialize(message)
                if isinstance(frame, EndFrame):
                    self.logger.info("Received EndFrame from Pipecat; disconnecting.")
                    await self.session.send_disconnect('completed', '', {})
                    return
                elif isinstance(frame, OutputAudioRawFrame):
                    # Extract and convert audio
                    pcm_pipecat = frame.audio
                    sample_rate = frame.sample_rate or self._pipecat_sample_rate
                    # Resample to 8kHz with FFmpeg (in-memory)
                    pcm_genesys = await self._resample_audio(pcm_pipecat, sample_rate, self._genesys_sample_rate)
                    # Encode to G.711 μ-law
                    g711_bytes = audioop.lin2ulaw(pcm_genesys, self._sample_width)
                    await self.session.send_audio(g711_bytes)
                    self.logger.debug(f"Forwarded {len(g711_bytes)} G.711 bytes to Genesys.")
                # Add handlers for other frames (e.g., TextFrame for transcripts) if needed
        except websockets.exceptions.ConnectionClosed:
            self.logger.info("Pipecat WebSocket closed.")
        except Exception as e:
            self.logger.error(f"Error in Pipecat receive loop: {e}")
            await self.session.send_disconnect('error', 'Bot service error', {})

    async def send_user_audio(self, g711_bytes: bytes):
        """Forward G.711 audio from Genesys to Pipecat."""
        if not self.ws:
            self.logger.warning("Pipecat not connected.")
            return
        try:
            # Decode G.711 μ-law to PCM 8kHz
            pcm_genesys = audioop.ulaw2lin(g711_bytes, self._sample_width)
            # Resample to 16kHz with FFmpeg (in-memory)
            pcm_pipecat = await self._resample_audio(pcm_genesys, self._genesys_sample_rate, self._pipecat_sample_rate)
            # Create and send frame
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
        """
        Resample PCM bytes from input_rate to output_rate using FFmpeg (in-memory).
        
        Args:
            pcm_in: Input PCM bytes (16-bit mono).
            input_rate: Input sample rate (Hz).
            output_rate: Output sample rate (Hz).
        
        Returns:
            Resampled PCM bytes.
        """
        try:
            # Use BytesIO for in-memory input/output
            process = (
                ffmpeg
                .input('pipe:', format='s16le', acodec='pcm_s16le', ar=input_rate, ac=1)
                .output('pipe:', format='s16le', acodec='pcm_s16le', ar=output_rate, ac=1)
                .overwrite_output()
                .run_async(pipe_stdin=True, pipe_stdout=True, pipe_stderr=True, quiet=True)
            )
            stdout, stderr = process.communicate(input=pcm_in)
            if process.returncode != 0:
                raise RuntimeError(f"FFmpeg resampling failed: {stderr.decode()}")
            return stdout
        except Exception as e:
            self.logger.error(f"FFmpeg resampling error: {e}")
            # Fallback: Return original (no resample) to avoid blocking
            return pcm_in

    async def stop(self):
        """Close Pipecat connection."""
        if self.receive_task:
            self.receive_task.cancel()
            try:
                await self.receive_task
            except asyncio.CancelledError:
                pass
        if self.ws:
            await self.ws.close()
            self.logger.info("Pipecat connection closed.")