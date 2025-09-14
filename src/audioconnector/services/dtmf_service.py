import logging
from typing import Callable, Any

class DTMFService:
    """
    Provides DTMF (Dual-Tone Multi-Frequency) support for incoming digits.
    
    This is a placeholder implementation that simulates DTMF digit capture.
    In a real-world scenario, this would be replaced with an actual DTMF processing mechanism.
    """
    def __init__(self):
        self._state = 'None'
        self._digits = ''
        self._listeners = {}
        self._logger = logging.getLogger(__name__)

    def on(self, event: str, listener: Callable[..., None]) -> 'DTMFService':
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
        Get current state of the DTMF service
        
        Returns:
            Current state as a string
        """
        return self._state

    def process_digit(self, digit: str) -> 'DTMFService':
        """
        Process an incoming DTMF digit
        
        Args:
            digit: DTMF digit to process
        
        Returns:
            Self, for method chaining
        """
        if self._state == 'Complete':
            self._emit('error', 'DTMF digits already received.')
            return self

        self._state = 'Processing'
        
        # If terminating digit is received, mark as complete and emit final digits
        if digit == '#':
            self._state = 'Complete'
            self._emit('final-digits', self._digits)
            self._digits = ''
            return self

        self._digits += digit
        return self
