from typing import Dict, Any, Optional

from .message_handler import MessageHandler
from .handlers.open_message_handler import OpenMessageHandler
from .handlers.close_message_handler import CloseMessageHandler
from .handlers.error_message_handler import ErrorMessageHandler
from .handlers.ping_message_handler import PingMessageHandler
from .handlers.playback_started_message_handler import PlaybackStartedMessageHandler
from .handlers.playback_completed_message_handler import PlaybackCompletedMessageHandler
from .handlers.dtmf_message_handler import DTMFMessageHandler

class MessageHandlerRegistry:
    """
    Registry for managing message handlers
    """
    def __init__(self):
        self._handlers: Dict[str, MessageHandler] = {
            'open': OpenMessageHandler(),
            'close': CloseMessageHandler(),
            'error': ErrorMessageHandler(),
            'ping': PingMessageHandler(),
            'playback_started': PlaybackStartedMessageHandler(),
            'playback_completed': PlaybackCompletedMessageHandler(),
            'dtmf': DTMFMessageHandler()
        }

    def get_handler(self, message_type: str) -> Optional[MessageHandler]:
        """
        Get a message handler for a specific message type
        
        Args:
            message_type: Type of message to get handler for
        
        Returns:
            Matching MessageHandler or None
        """
        return self._handlers.get(message_type)
