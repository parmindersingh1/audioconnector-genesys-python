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
```bash
# Create .env file
touch .env
```

Add the following content to the `.env` file:
```
# Server Configuration
PORT=8080
LOG_LEVEL=INFO

# Add any additional environment-specific configurations
```

## Running the Application

### Development Mode
```bash
uvicorn src.audioconnector.main:app --reload
```

### Production Mode
```bash
uvicorn src.audioconnector.main:app --host 0.0.0.0 --port 8080
```

## WebSocket Endpoint
- URL: `ws://localhost:8080/ws`

## Project Structure
- `src/audioconnector/`: Main application code
  - `main.py`: FastAPI application entry point
  - `websocket/`: WebSocket server implementation
  - `services/`: Core service implementations
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