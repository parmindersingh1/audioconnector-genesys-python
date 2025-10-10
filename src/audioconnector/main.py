# import os
# import logging
# from dotenv import load_dotenv

# from fastapi import FastAPI, WebSocket
# from fastapi.middleware.cors import CORSMiddleware

# from .websocket.server import WebSocketServer

# # Load environment variables
# load_dotenv()

# # Configure logging
# def configure_logging():
#     """
#     Configure logging to ensure logs are displayed
#     """
#     # Configure root logger
#     logging.basicConfig(
#         level=logging.INFO,
#         format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
#         handlers=[
#             logging.StreamHandler()  # Ensure logs go to console
#         ]
#     )

#     # Configure uvicorn loggers
#     uvicorn_loggers = ['uvicorn', 'uvicorn.access', 'uvicorn.error']
#     for logger_name in uvicorn_loggers:
#         logger = logging.getLogger(logger_name)
#         logger.handlers = []  # Remove existing handlers
#         logger.propagate = True  # Ensure logs propagate to root logger

# # Configure logging before creating the app
# configure_logging()

# # Create logger
# logger = logging.getLogger(__name__)

# # Create FastAPI app
# app = FastAPI(
#     title="AudioConnector Server",
#     description="WebSocket-based audio processing server",
#     version="0.1.0"
# )

# # Add CORS middleware
# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["*"],
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )

# @app.on_event("startup")
# async def startup_event():
#     """
#     Startup event handler for additional initialization
#     """
#     logger.info("*****************")
#     logger.info("Starting AudioConnector server")
#     logger.info(os.getenv('PORT'))
#     logger.info("*****************")

# @app.websocket("/ws")
# async def websocket_endpoint(websocket: WebSocket):
#     """
#     WebSocket endpoint for handling connections
    
#     Args:
#         websocket: Incoming WebSocket connection
#     """
#     ws_server = WebSocketServer()
#     await ws_server.handle_websocket(websocket)

# if __name__ == "__main__":
#     import uvicorn
    
#     # Get port from environment, default to 8080
#     port = int(os.getenv('PORT', 8080))
    
#     logger.info(f"Starting server on port {port}")
#     uvicorn.run(
#         "audioconnector.main:app", 
#         host="0.0.0.0", 
#         port=port,
#         reload=True  # Enable auto-reload for development
#     )





########################### Pipecat ##############################


#
# bot_fast_api.py
#
# Complete FastAPI WebSocket server that speaks the expected Genesys-style protocol:
# - accepts headers and an "open" JSON message
# - responds with "opened"
# - echoes binary audio back
# - sends a synthetic "event" transcript
#
# Works directly with the provided test_client.js.
#

import os
import json
import asyncio
import logging
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# ---------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("AudioConnector")

app = FastAPI(
    title="AudioConnector",
    description="FastAPI WebSocket server for audio streaming & transcripts",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------


async def send_opened_message(websocket: WebSocket, open_msg: dict):
    """Send an 'opened' message after receiving an 'open' handshake."""
    session_id = open_msg.get("id", "session-123")
    version = open_msg.get("version", "2")
    seq = int(open_msg.get("seq", 1))

    opened_msg = {
        "id": session_id,
        "version": version,
        "seq": seq + 1,
        "serverseq": 0,
        "type": "opened",
        "parameters": {
            "sessionId": open_msg.get("parameters", {}).get("conversationId"),
            "media": open_msg.get("parameters", {}).get("media", []),
        },
    }

    await websocket.send_text(json.dumps(opened_msg))
    logger.info("Sent 'opened' message ✅")


async def send_transcript_event(websocket: WebSocket, text: str):
    """Send a synthetic transcript event."""
    event = {
        "id": "compat-session",
        "version": "2",
        "seq": 9999,
        "serverseq": 0,
        "type": "event",
        "parameters": {
            "entities": [
                {
                    "type": "transcript",
                    "data": {
                        "alternatives": [
                            {
                                "interpretations": [
                                    {"transcript": text}
                                ]
                            }
                        ]
                    },
                }
            ]
        },
    }

    try:
        await websocket.send_text(json.dumps(event))
        logger.info("Sent transcript event 🗣️")
    except Exception as e:
        logger.warning(f"Failed to send transcript event: {e}")


# ---------------------------------------------------------------------
# WebSocket Endpoint
# ---------------------------------------------------------------------


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Main WebSocket handler compatible with test_client.js"""
    await websocket.accept()
    logger.info("WebSocket connection accepted.")

    audio_chunks = 0
    last_audio_time = None
    silence_timeout = 2.0  # seconds

    try:
        while True:
            try:
                message = await asyncio.wait_for(websocket.receive(), timeout=1.0)
            except asyncio.TimeoutError:
                # if no audio for a while, send transcript
                if last_audio_time and (
                    asyncio.get_event_loop().time() - last_audio_time > silence_timeout
                ):
                    await send_transcript_event(websocket, "This is a test transcript.")
                    last_audio_time = None
                continue

            if message["type"] == "websocket.disconnect":
                logger.info("Client disconnected.")
                break

            # Handle binary (audio)
            if message.get("bytes") is not None:
                chunk = message["bytes"]
                audio_chunks += 1
                last_audio_time = asyncio.get_event_loop().time()
                logger.debug(f"Received {len(chunk)} bytes of audio (chunk {audio_chunks})")

                # Echo the same audio bytes back
                await websocket.send_bytes(chunk)
                continue

            # Handle text (JSON)
            if message.get("text"):
                text = message["text"]
                try:
                    data = json.loads(text)
                except json.JSONDecodeError:
                    logger.warning(f"Invalid JSON: {text}")
                    continue

                msg_type = data.get("type", "").lower()

                if msg_type == "open":
                    logger.info("Received 'open' handshake")
                    await send_opened_message(websocket, data)

                elif msg_type == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))

                else:
                    logger.debug(f"Received other JSON message: {msg_type}")

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected cleanly.")
    except Exception as e:
        logger.exception(f"Error in websocket loop: {e}")
    finally:
        # Before closing, send one final transcript
        try:
            await send_transcript_event(websocket, "Final transcript from server.")
            await websocket.close()
        except Exception:
            pass
        logger.info(f"Connection closed after {audio_chunks} audio chunks.")


# ---------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    logger.info(f"🚀 Starting AudioConnector server on port {port}")
    uvicorn.run("bot_fast_api:app", host="0.0.0.0", port=port, reload=True)



########## uvicorn src.audioconnector.main:app --host 0.0.0.0 --port 8000