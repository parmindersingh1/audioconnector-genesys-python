import logging
from typing import Callable, Any, Optional

class Transcript:
    """Represents a transcript with text and confidence"""
    def __init__(self, text: str, confidence: float):
        self.text = text
        self.confidence = confidence

class ASRService:
    """
    Provides ASR (Automatic Speech Recognition) support for incoming audio.
    
    This is a placeholder implementation that simulates ASR behavior.
    In a real-world scenario, this would be replaced with an actual ASR engine.
    """
    def __init__(self):
        self._state = 'None'
        self._byte_count = 0
        self._listeners = {}
        self._logger = logging.getLogger(__name__)

    def on(self, event: str, listener: Callable[..., None]) -> 'ASRService':
        """
        Register an event listener
        
        Args:
            event: Event name to listen for
            listener: Callback function for the event
        
        Returns:
            Self, for method chaining
        """
        if event not in self._listeners:
            self._listeners[event] = []
        self._listeners[event].append(listener)
        return self

    def _emit(self, event: str, *args):
        """
        Emit an event to all registered listeners
        
        Args:
            event: Event name
            *args: Event arguments
        """
        if event in self._listeners:
            for listener in self._listeners[event]:
                listener(*args)

    def get_state(self) -> str:
        """
        Get current state of the ASR service
        
        Returns:
            Current state as a string
        """
        return self._state

    def process_audio(self, data: bytes) -> 'ASRService':
        """
        Process incoming audio data
        
        Args:
            data: Audio bytes to process
        
        Returns:
            Self, for method chaining
        """
        if self._state == 'Complete':
            self._emit('error', 'Speech recognition has already completed.')
            return self

        self._byte_count += len(data)

        # Simulate ASR completion after 40k bytes
        # In a real implementation, this would be replaced with actual ASR processing
        if self._byte_count >= 40000:
            self._state = 'Complete'
            self._emit('final-transcript', Transcript(
                text='I would like to check my account balance.',
                confidence=1.0
            ))
            self._byte_count = 0
            return self

        self._state = 'Processing'
        return self
