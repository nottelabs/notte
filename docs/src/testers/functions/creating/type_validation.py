# @sniptest filename=type_validation.py
def run(count: int):
    # Type hints document the expected input but are not enforced:
    # convert explicitly if the caller may send a string
    count = int(count)
    for i in range(count):
        print(i)
