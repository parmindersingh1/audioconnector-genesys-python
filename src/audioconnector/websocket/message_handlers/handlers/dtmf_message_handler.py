import logging
from typing import Dict, Any

from ..message_handler import MessageHandler

class DTMFMessageHandler(MessageHandler):
    """
    Handler for DTMF message type
    """
    def __init__(self):
        self.logger = logging.getLogger(__name__)

    async def handle_message(self, message: Dict[str, Any], session: Any):
        """
        Handle DTMF message
        
        Args:
            message: Parsed message dictionary
            session: Current session object
        """
        digit = message.get('parameters', {}).get('digit')
        
        if digit:
            self.logger.info(f"Received DTMF digit: {digit}")
            session.process_dtmf(digit)
