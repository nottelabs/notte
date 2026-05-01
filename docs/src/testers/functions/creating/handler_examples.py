# @sniptest filename=handler_examples.py
# @sniptest show=5-16


def perform_task():
    return "result"


# Correct
def run(param1, param2):
    return "result"


# Wrong - different name
def execute(param1, param2):
    return "result"


# Wrong - no function
result = perform_task()
