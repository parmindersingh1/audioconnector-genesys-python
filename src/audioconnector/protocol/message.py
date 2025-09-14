from typing import Dict, Union, List, Literal, TypedDict, Optional, Any

from .core import JsonStringMap
from .voice_bots import BotTurnDisposition

# Message type definitions
ServerMessageType = Literal['event', 'disconnect', 'closed']
DisconnectReason = Literal['error', 'completed']

class EventEntity(TypedDict):
    type: str
    data: Dict[str, Any]

class EventParameters(TypedDict):
    entities: List[EventEntity]

class DisconnectParameters(TypedDict):
    reason: DisconnectReason
    info: str
    outputVariables: JsonStringMap

class ServerMessageBase(TypedDict):
    id: str
    version: str
    seq: int
    clientseq: int
    type: ServerMessageType
    parameters: Union[EventParameters, DisconnectParameters, Dict[str, Any]]

# Type for selecting parameters based on message type
def SelectParametersForType(type: ServerMessageType, message: 'ServerMessage') -> Union[EventParameters, DisconnectParameters, Dict[str, Any]]:
    # This is a type hint helper function, not meant to be called at runtime
    return {}

# Alias for server message to match TypeScript implementation
ServerMessage = ServerMessageBase
ClientMessage = Dict[str, Any]
