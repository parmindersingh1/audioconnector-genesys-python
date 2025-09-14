from abc import ABC, abstractmethod
from typing import Dict, Any

class MessageHandler(ABC):
    """
    Abstract base class for message handlers
    """
    @abstractmethod
    async def handle_message(self, message: Dict[str, Any], session: Any):
        """
        Handle an incoming message
        
        Args:
            message: Parsed message dictionary
            session: Current session object
        """
        pass
