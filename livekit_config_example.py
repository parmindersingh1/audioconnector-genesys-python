import asyncio
from src.audioconnector.common.session import Session
from fastapi import WebSocket

async def create_livekit_session(
    session_id: str,
    livekit_url: str = 'https://lks.whilter.ai',
    email: str = 'user@example.com',
    mobile_number: str = '+919121212121',
    stt: str = 'Self-Hosted',
    llm: str = 'Self-Hosted',
    tts: str = 'Self-Hosted',
    org_id: str = 'default-org-id'
):
    """
    Example function to create a LiveKit session with custom parameters
    
    Args:
        session_id: Unique identifier for the session
        livekit_url: URL of the LiveKit token service
        email: User's email address
        mobile_number: User's mobile number
        stt: Speech-to-text service
        llm: Language model service
        tts: Text-to-speech service
        org_id: Organization identifier
    
    Returns:
        Session object configured with LiveKit parameters
    """
    # Simulate WebSocket (in a real scenario, this would be a real WebSocket connection)
    class MockWebSocket:
        async def send_text(self, message):
            print(f"Sending text: {message}")
        
        async def send_bytes(self, message):
            print(f"Sending bytes: {len(message)} bytes")
        
        async def close(self):
            print("WebSocket closed")
    
    # Create session with LiveKit parameters
    session = Session(
        ws=MockWebSocket(),  # Replace with actual WebSocket in production
        session_id=session_id,
        livekit_url=livekit_url,
        email=email,
        mobile_number=mobile_number,
        stt=stt,
        llm=llm,
        tts=tts,
        org_id=org_id
    )
    
    return session

# Example usage
async def main():
    # Create a session with default parameters
    default_session = await create_livekit_session('test-session-1')
    
    # Create a session with custom parameters
    custom_session = await create_livekit_session(
        session_id='custom-session-1',
        email='custom_user@whilter.ai',
        mobile_number='+911234567890',
        stt='custom-stt',
        llm='custom-llm',
        tts='custom-tts',
        org_id='custom-org-id'
    )

if __name__ == '__main__':
    asyncio.run(main())
