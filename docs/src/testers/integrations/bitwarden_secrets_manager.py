# @sniptest filename=bitwarden_secrets_manager.py
# @sniptest typecheck_only=true
from notte_core.credentials.bitwarden import BitwardenVault

import notte

# Reads BWS_ACCESS_TOKEN and BWS_ORGANIZATION_ID
with BitwardenVault() as vault, notte.Session(vault=vault) as session:
    _ = session.execute(type="goto", url="https://github.com/login")
    # The secret whose url matches github.com fills the form
    _ = session.execute(type="form_fill", value={"username": notte.USERNAME, "current_password": notte.PASSWORD})
