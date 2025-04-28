import asyncio
from pathlib import Path

import pytest
from dotenv import load_dotenv
from notte_sdk.client import NotteClient
from notte_sdk.websockets.recording import SessionRecordingWebSocket

_ = load_dotenv()


@pytest.mark.skip("Skipping on CICD as this is not deployed yet")
@pytest.mark.asyncio
async def test_recording_websocket():
    # Initialize the Notte client and start a session
    client = NotteClient()
    with client.Session(proxies=False, max_steps=1) as session:
        # Get debug info to obtain the token
        # debug_info = session.debug_info()
        info = session.debug_info()

        # Create a temporary file for the recording
        output_path = Path("test_recording.bin")
        # wss_url = f"ws://localhost:8000/sessions/{session.session_id}/debug/recording?token={client.sessions.token}"
        # Initialize the WebSocket client
        ws_client = SessionRecordingWebSocket(
            wss_url=info.ws.recording,
            display_image=False,
            output_path=output_path,
        )

        # Save some recording data
        try:
            # We'll limit this to 5 seconds for testing
            async with asyncio.timeout(5):
                await ws_client.watch()
        except TimeoutError:
            pass  # Expected after 5 seconds

        # Verify the recording file exists and has content
        assert output_path.exists()
        assert output_path.stat().st_size > 0

        # Clean up
        output_path.unlink()
