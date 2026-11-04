# @sniptest filename=workspace_session.py
# @sniptest typecheck_only=true
from notte_sdk import NotteClient
from notte_sdk.types import NotteProxy, ProxySettings, SecretProxy

client = NotteClient()

# Use the workspace's saved secret proxy as it is
saved: list[ProxySettings] = [NotteProxy(), SecretProxy()]
with client.Session(proxies=saved) as session:
    print(session.session_id)

# Use the saved secret proxy with a different password for this session
override: list[ProxySettings] = [NotteProxy(), SecretProxy(password="SESSION_PASSWORD")]
with client.Session(proxies=override) as session:
    print(session.session_id)
