# @sniptest filename=use_variables.py
# Good - parameterized
result = function.run(url=dynamic_url, query=user_input)

# Bad - hardcoded
result = function.run()  # URL hardcoded in function
