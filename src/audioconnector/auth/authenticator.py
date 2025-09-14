from typing import Dict, Any
from fastapi import WebSocket

from .signature_verifier import verify_request_signature
from ..services.secret_service import SecretService

async def verify_websocket_signature(
    websocket: WebSocket, 
    secret_service: SecretService
) -> Dict[str, str]:
    """
    Verify the WebSocket request signature
    
    Args:
        websocket: The incoming WebSocket connection
        secret_service: Service for managing secrets
    
    Returns:
        A dictionary with verification result
    """
    try:
        # Extract headers from WebSocket
        headers = dict(websocket.headers)
        print(headers)
        
        # Perform signature verification
        result = await verify_request_signature(headers, secret_service)
        
        # Convert result to dictionary for consistency
        return {
            'code': result.code,
            'reason': result.reason or ''
        }
    except Exception as e:
        # Handle any unexpected errors
        return {
            'code': 'ERROR',
            'reason': str(e)
        }
