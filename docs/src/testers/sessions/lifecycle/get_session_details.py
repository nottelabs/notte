from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    # Get full session status
    status = session.status()

    print(f"Session ID: {status.session_id}")
    print(f"Status: {status.status}")
    print(f"Created at: {status.created_at}")
    print(f"Last accessed: {status.last_accessed_at}")
    print(f"Idle timeout: {status.idle_timeout_minutes} minutes")
    print(f"Max duration: {status.max_duration_minutes} minutes")
    print(f"Duration: {status.duration}")

    # Get CDP URL for external connections
    cdp_url = session.cdp_url()
    print(f"CDP WebSocket: {cdp_url}")
