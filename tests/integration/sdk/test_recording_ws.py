import asyncio
from pathlib import Path

import pytest
from notte_sdk.client import NotteClient
from notte_sdk.websockets.recording import SessionRecordingWebSocket


@pytest.mark.asyncio
async def test_recording_websocket():
    # Initialize the Notte client and start a session
    client = NotteClient()
    with client.Session(proxies=False, max_steps=1) as session:
        # Get debug info to obtain the token
        debug_info = session.debug_info()

        # Initialize the WebSocket client
        ws_client = SessionRecordingWebSocket(session_id=session.session_id, token=debug_info.token)

        # Create a temporary file for the recording
        output_path = Path("test_recording.bin")

        # Save some recording data
        try:
            # We'll limit this to 5 seconds for testing
            async with asyncio.timeout(5):
                await ws_client.save_recording(output_path)
        except TimeoutError:
            pass  # Expected after 5 seconds

        # Verify the recording file exists and has content
        assert output_path.exists()
        assert output_path.stat().st_size > 0

        # Clean up
        output_path.unlink()
