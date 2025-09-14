import logging
from typing import Dict, Any

from ..message_handler import MessageHandler

class PlaybackCompletedMessageHandler(MessageHandler):
    """
    Handler for playback completed message type
    """
    def __init__(self):
        self.logger = logging.getLogger(__name__)

    async def handle_message(self, message: Dict[str, Any], session: Any):
        """
        Handle playback completed message
        
        Args:
            message: Parsed message dictionary
            session: Current session object
        """
        self.logger.info("Playback completed")
        session.set_is_audio_playing(False)
