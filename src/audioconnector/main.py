import os
import logging
from dotenv import load_dotenv

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware

from .websocket.server import WebSocketServer

# Load environment variables
load_dotenv()

# Configure logging
def configure_logging():
    """
    Configure logging to ensure logs are displayed
    """
    # Configure root logger
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler()  # Ensure logs go to console
        ]
    )

    # Configure uvicorn loggers
    uvicorn_loggers = ['uvicorn', 'uvicorn.access', 'uvicorn.error']
    for logger_name in uvicorn_loggers:
        logger = logging.getLogger(logger_name)
        logger.handlers = []  # Remove existing handlers
        logger.propagate = True  # Ensure logs propagate to root logger

# Configure logging before creating the app
configure_logging()

# Create logger
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="AudioConnector Server",
    description="WebSocket-based audio processing server",
    version="0.1.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    """
    Startup event handler for additional initialization
    """
    logger.info("*****************")
    logger.info("Starting AudioConnector server")
    logger.info(os.getenv('PORT'))
    logger.info("*****************")

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for handling connections
    
    Args:
        websocket: Incoming WebSocket connection
    """
    ws_server = WebSocketServer()
    await ws_server.handle_websocket(websocket)

if __name__ == "__main__":
    import uvicorn
    
    # Get port from environment, default to 8080
    port = int(os.getenv('PORT', 8080))
    
    logger.info(f"Starting server on port {port}")
    uvicorn.run(
        "audioconnector.main:app", 
        host="0.0.0.0", 
        port=port,
        reload=True  # Enable auto-reload for development
    )
