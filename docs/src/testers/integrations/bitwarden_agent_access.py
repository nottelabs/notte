# @sniptest filename=bitwarden_agent_access.py
# @sniptest typecheck_only=true
from notte_core.credentials.aac import AacVault

import notte

# Pairs with the token from `aac listen`, read from AAC_TOKEN (or pass token="ABC-DEF-GHI")
with AacVault() as vault, notte.Session(vault=vault) as session:
    _ = session.execute(type="goto", url="https://github.com/login")
    # Bitwarden returns the github.com login; the browser gets it, your code only sees placeholders
    _ = session.execute(type="form_fill", value={"username": notte.USERNAME, "current_password": notte.PASSWORD})
