import logging
import json
from typing import Dict, Any

from ..message_handler import MessageHandler

class OpenMessageHandler(MessageHandler):
    """
    Handler for open message type
    """
    def __init__(self):
        self.logger = logging.getLogger(__name__)

    async def handle_message(self, message: Dict[str, Any], session: Any):
        """
        Handle open message
        
        Args:
            message: Parsed message dictionary
            session: Current session object
        """
        self.logger.info("Handling open message")
        
        # Send 'opened' message to confirm connection
        opened_message = {
            'id': message.get('id', session.client_session_id),
            'version': '2',
            'seq': 1,
            'serverseq': 0,
            'type': 'opened',
            'parameters': {}
        }
        await session.send(opened_message)
        
        # Check if bot exists
        bot_exists = await session.check_if_bot_exists()
        
        if bot_exists:
            # Process bot start
            await session.process_bot_start()
