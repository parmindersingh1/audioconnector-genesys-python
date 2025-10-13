import logging
import json
from typing import Dict, Any, List

from ..message_handler import MessageHandler

class OpenMessageHandler(MessageHandler):
    """
    Handler for open message type
    """
    def __init__(self):
        self.logger = logging.getLogger(__name__)

    async def handle_message(self, message: Dict[str, Any], session: Any):
        """
        Handle open message
        
        Args:
            message: Parsed message dictionary
            session: Current session object
        """
        parsed_message = message

        if not parsed_message:
            error_message = 'Invalid request parameters.'
            self.logger.error(error_message)
            await session.send_disconnect('error', error_message, {})
            return

        # Set conversation ID
        if 'parameters' in parsed_message and 'conversationId' in parsed_message['parameters']:
            session.set_conversation_id(parsed_message['parameters']['conversationId'])

        self.logger.info('Received an Open Message.')

        selected_media = None

        if 'parameters' in parsed_message and 'media' in parsed_message['parameters']:
            for element in parsed_message['parameters']['media']:
                if element.get('format') == 'PCMU' and element.get('rate') == 8000:
                    selected_media = element
                    break

        if not selected_media:
            error_message = 'No supported media type was found.'
            self.logger.error(error_message)
            await session.send_disconnect('error', error_message, {})
            return

        self.logger.info(f'Using MediaParameter {json.dumps(selected_media)}')

        session.set_selected_media(selected_media)

        if 'parameters' in parsed_message and 'inputVariables' in parsed_message['parameters']:
            session.set_input_variables(parsed_message['parameters']['inputVariables'])

        # Check if bot exists
        bot_exists = await session.check_if_bot_exists()
        
        if not bot_exists:
            error_message = 'The specific Bot does not exist.'
            self.logger.error(error_message)
            await session.send_disconnect('error', error_message, {})
            return

        if selected_media:
            # Create and send 'opened' message with media
            opened_message = session.create_message('opened', {
                'media': [selected_media]
            })
            await session.send(opened_message)
            
            # Send out the turn response for the start of a conversation.
            await session.process_bot_start()