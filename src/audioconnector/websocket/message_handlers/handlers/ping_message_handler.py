import logging
from typing import Dict, Any

from ..message_handler import MessageHandler

class PingMessageHandler(MessageHandler):
    """
    Handler for ping message type
    """
    def __init__(self):
        self.logger = logging.getLogger(__name__)

    async def handle_message(self, message: Dict[str, Any], session: Any):
        """
        Handle ping message
        
        Args:
            message: Parsed message dictionary
            session: Current session object
        """
        self.logger.info("Received ping message")
        pong_message = session.create_message('pong', {})
        await session.send(pong_message)