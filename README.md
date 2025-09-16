# AudioConnector Server - FastAPI Reference Implementation

## Overview
This is a Python FastAPI implementation of the AudioConnector server, providing WebSocket-based communication for audio processing and bot interactions.

## Prerequisites
- Python 3.9+
- pip
- (Optional) venv or conda for virtual environment

## Setup

### 1. Clone the Repository
```bash
git clone <repository-url>
cd audioconnector-server-reference-implementation
```

### 2. Create a Virtual Environment (Recommended)
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows, use `venv\Scripts\activate`
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Environment Configuration
Create a `.env` file in the project root with the following configurations:
```
# Server Configuration
PORT=8080
LOG_LEVEL=INFO

# LiveKit Configuration
LIVEKIT_API_KEY=your_livekit_api_key
LIVEKIT_API_SECRET=your_livekit_api_secret
LIVEKIT_SOCKET_URL=wss://your-livekit-domain.livekit.cloud

# Agent Configuration (Optional)
AGENT_STT=default_stt_service
AGENT_LLM=default_llm_service
AGENT_TTS=default_tts_service
```

### LiveKit Environment Variables

You can configure LiveKit connection parameters using the following environment variables:

| Variable | Description | Default Value |
|----------|-------------|---------------|
| `LIVEKIT_TOKEN_URL` | URL for token generation | `https://lks.whilter.ai/token` |
| `LIVEKIT_WS_URL` | WebSocket URL for LiveKit connection | `wss://livekit.whilter.ai` |
| `LIVEKIT_API_KEY` | Optional API key for LiveKit | `None` |
| `LIVEKIT_API_SECRET` | Optional API secret for LiveKit | `None` |

#### Example .env File

```
LIVEKIT_TOKEN_URL=https://lks.whilter.ai/token
LIVEKIT_WS_URL=wss://livekit.whilter.ai
LIVEKIT_API_KEY=your_api_key
LIVEKIT_API_SECRET=your_api_secret
```

Note: Make sure to install `python-dotenv` to use environment variables.

## Running the Application

### Development Mode
```bash
uvicorn src.audioconnector.main:app --reload
```

### Running LiveKit Agent Example
```bash
python -m src.audioconnector.examples.livekit_service_example
```

## WebSocket Endpoint
- URL: `ws://localhost:8080/ws`

## LiveKit Integration

### Connection Parameters

The LiveKit session now supports advanced configuration with the following parameters:

| Parameter | Type | Description | Default |
|-----------|------|-------------|---------|
| `session_id` | `str` | Unique identifier for the session | Required |
| `livekit_url` | `str` | URL of the LiveKit token service | `'https://lks.whilter.ai'` |
| `email` | `str` | User's email address | `'user@example.com'` |
| `mobile_number` | `str` | User's mobile number | `'+919121212121'` |
| `stt` | `str` | Speech-to-text service | `'Self-Hosted'` |
| `llm` | `str` | Language model service | `'Self-Hosted'` |
| `tts` | `str` | Text-to-speech service | `'Self-Hosted'` |
| `org_id` | `str` | Organization identifier | `'default-org-id'` |

### Example Usage

```python
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
```

### Token Generation

The LiveKit integration now supports a more flexible token generation process:
- Generates unique session and participant identities
- Supports custom metadata
- Provides default values for optional parameters
- Improved error handling and logging

## Project Structure
- `src/audioconnector/`: Main application code
  - `main.py`: FastAPI application entry point
  - `services/`: Core service implementations
    - `livekit_service.py`: LiveKit service implementation
  - `websocket/`: WebSocket server implementation
  - `auth/`: Authentication and signature verification
  - `protocol/`: Message and protocol definitions

## Development Notes
- This is a reference implementation with placeholder services
- Replace placeholder services with actual implementations as needed
- Implement proper error handling and logging in production

## Contributing
1. Fork the repository
2. Create your feature branch
3. Commit your changes
4. Push to the branch
5. Create a new Pull Request

## License
[Specify your license here]