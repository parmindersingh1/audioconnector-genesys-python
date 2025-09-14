from typing import Any, Dict, List, Union, Optional
import re

# Type aliases to match TypeScript implementation
BareItem = Union[str, int, bool, bytes]
Dictionary = Dict[str, Any]
InnerList = Dict[str, Any]

def is_string(value: Any) -> bool:
    return isinstance(value, str)

def is_integer(value: Any) -> bool:
    return isinstance(value, int)

def is_boolean(value: Any) -> bool:
    return isinstance(value, bool)

def is_byte_sequence(value: Any) -> bool:
    return isinstance(value, bytes)

def is_inner_list(value: Any) -> bool:
    return isinstance(value, dict) and 'value' in value and isinstance(value['value'], list)

def is_item(value: Any) -> bool:
    return isinstance(value, dict) and 'value' in value

def canonicalize_header_field_value(value: str) -> str:
    """
    Canonicalize header field value according to HTTP signature draft spec
    """
    return re.sub(r'[ \t]*\r\n[ \t]+', ' ', value.strip())

def parse_dictionary_field(value: str) -> Dictionary:
    """
    Parse a dictionary field (placeholder implementation)
    """
    # This is a simplified version and might need more robust parsing
    return {}

def encode_bare_item(item: BareItem) -> str:
    """
    Encode a bare item to a string representation
    """
    if isinstance(item, str):
        return f'"{item}"'
    elif isinstance(item, int):
        return str(item)
    elif isinstance(item, bool):
        return str(item).lower()
    elif isinstance(item, bytes):
        return f'b"{item.decode()}"'
    return str(item)

def encode_item(item: Dict[str, Any]) -> str:
    """
    Encode an item with optional parameters
    """
    base = encode_bare_item(item['value'])
    if 'params' in item and item['params']:
        params_str = ';'.join(f"{p['key']}={encode_bare_item(p['value'])}" for p in item['params'])
        return f"{base};{params_str}"
    return base

def encode_inner_list(inner_list: InnerList) -> str:
    """
    Encode an inner list
    """
    # Simplified implementation
    return str(inner_list)
