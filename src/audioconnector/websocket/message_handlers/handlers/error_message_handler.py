import logging
from typing import Dict, Any

from ..message_handler import MessageHandler

class ErrorMessageHandler(MessageHandler):
    """
    Handler for error message type
    """
    def __init__(self):
        self.logger = logging.getLogger(__name__)

    async def handle_message(self, message: Dict[str, Any], session: Any):
        """
        Handle error message
        
        Args:
            message: Parsed message dictionary
            session: Current session object
        """
        self.logger.error(f"Received error message: {message}")
        await session.send_disconnect('error', 'Error occurred', {})
