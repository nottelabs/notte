# @sniptest filename=test_before_prod.py
from notte_sdk import NotteClient


def validate_before_production():
    client = NotteClient()

    # Test locally first - decryption key needed for local execution
    function = client.Function(function_id="func_abc123", decryption_key="your-key")

    # Run with local=True for testing
    test_result = function.run(url="https://test-site.com", local=True)

    if test_result.status == "closed":
        print("Test passed, ready to update production")
        function.update(path="tested_function.py")
    else:
        print(f"Test failed: {test_result.result}")
