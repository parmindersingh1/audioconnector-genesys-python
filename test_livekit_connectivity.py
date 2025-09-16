import asyncio
import aiohttp
import logging
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_livekit_connectivity(agent_service_url):
    """
    Test connectivity to the LiveKit token endpoint
    
    Args:
        agent_service_url (str): URL of the agent service to test
    
    Returns:
        bool: True if connectivity test passes, False otherwise
    """
    try:
        async with aiohttp.ClientSession() as session:
            # Use the actual token endpoint
            endpoint = f"{agent_service_url}/token"
            logger.info(f"Testing connectivity to: {endpoint}")
            
            # Prepare payload matching the example
            payload = {
                "identity": "+919121212121",
                "metadata": {
                    "email": "super_admin@whilter.ai",
                    "mobile_number": "+919121212121",
                    "stt": "Self-Hosted",
                    "llm": "Self-Hosted",
                    "tts": "Self-Hosted",
                    "orgId": "68908ae07c3fca39e1b8d1c0"
                }
            }
            
            # Set headers similar to the curl request
            headers = {
                'accept': 'application/json, text/plain, */*',
                'accept-language': 'en-IN,en-GB;q=0.9,en;q=0.8,en-US;q=0.7'
            }
            
            async with session.post(endpoint, json=payload, headers=headers, timeout=10) as response:
                logger.info(f"Response status: {response.status}")
                
                if response.status == 200:
                    data = await response.json()
                    logger.info("Token generation successful!")
                    
                    # Validate response structure
                    required_keys = ['token', 'room', 'identity']
                    missing_keys = [key for key in required_keys if key not in data]
                    
                    if missing_keys:
                        logger.error(f"Missing keys in response: {missing_keys}")
                        return False
                    
                    # Log token details (without full token for security)
                    logger.info(f"Room: {data['room']}")
                    logger.info(f"Identity: {data['identity']}")
                    logger.info(f"Token length: {len(data['token'])} characters")
                    
                    return True
                else:
                    logger.error(f"Token generation failed. Status code: {response.status}")
                    logger.error(f"Response text: {await response.text()}")
                    return False
    
    except aiohttp.ClientConnectorError as e:
        logger.error(f"Connection error: {e}")
        return False
    except asyncio.TimeoutError:
        logger.error("Connectivity test timed out")
        return False
    except Exception as e:
        logger.error(f"Unexpected error during connectivity test: {e}")
        return False

async def main():
    agent_service_url = "https://lks.whilter.ai"
    result = await test_livekit_connectivity(agent_service_url)
    print(f"Connectivity Test Result: {'PASSED' if result else 'FAILED'}")

if __name__ == "__main__":
    asyncio.run(main())
