# @sniptest filename=typed_errors.py
from notte_sdk.errors import ExpectedFunctionError


class AccountNotUnique(ValueError, ExpectedFunctionError):
    status_code = 409


def run(email: str, account_ids: list[str]):
    if len(account_ids) != 1:
        # A deliberate refusal: the run ends as "rejected" and is not self-healed.
        raise AccountNotUnique(f"{len(account_ids)} accounts match {email}")

    return {"account_id": account_ids[0]}
