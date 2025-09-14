import os

DEFAULT_PORT = 8080

def get_port() -> int:
    """
    Retrieve the port number from environment variables, 
    defaulting to DEFAULT_PORT if not set.
    
    Returns:
        int: Port number for the server
    """
    return int(os.getenv('PORT', DEFAULT_PORT))
