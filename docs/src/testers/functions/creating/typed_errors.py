# @sniptest filename=typed_errors.py
# @sniptest show=1-23
class ExpectedFunctionError(Exception):
    """A deliberate refusal: the run ends as "rejected" and is never self-healed."""


class RetryableFunctionError(Exception):
    """A temporary problem: the run fails, is not self-healed, and the caller may retry."""


class AccountNotUnique(ValueError, ExpectedFunctionError):
    status_code = 409


class PortalUnavailable(RetryableFunctionError):
    pass


def run(email: str, account_ids: list[str], portal_up: bool = True):
    if not portal_up:
        raise PortalUnavailable("The portal is down, try again later")
    if len(account_ids) != 1:
        raise AccountNotUnique(f"{len(account_ids)} accounts match {email}")

    return {"account_id": account_ids[0]}


def raised(account_ids: list[str], portal_up: bool = True) -> type[Exception] | None:
    try:
        run("user@example.com", account_ids, portal_up)
    except Exception as error:
        return type(error)
    return None


assert run("a@example.com", ["acct_1"]) == {"account_id": "acct_1"}
assert raised(["acct_1", "acct_2"]) is AccountNotUnique
assert raised(["acct_1"], portal_up=False) is PortalUnavailable
# A built-in base keeps `except ValueError` working when you run the code locally.
assert issubclass(AccountNotUnique, ValueError)
results = [True]
