from typing import Literal

# Bot turn disposition types
BotTurnDisposition = Literal['match', 'no_match', 'no_input']

# Event entities for bot interactions
class EventEntityBargeIn(dict):
    """Represents a barge-in event"""
    def __init__(self):
        super().__init__(type='barge_in', data={})

class EventEntityBotTurnResponse(dict):
    """Represents a bot turn response event"""
    def __init__(self, disposition: BotTurnDisposition, text: str = None, confidence: float = None):
        data = {
            'disposition': disposition
        }
        if text is not None:
            data['text'] = text
        if confidence is not None:
            data['confidence'] = confidence
        
        super().__init__(type='bot_turn_response', data=data)
