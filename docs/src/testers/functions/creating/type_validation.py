# @sniptest filename=type_validation.py
def run(count: int):
    # count is automatically validated as int
    for i in range(count):
        print(i)
