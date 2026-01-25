from pydantic import ValidationError

try:
    result = agent.run(
        task="Extract product data",
        response_format=Product,
    )
    product = result.answer
except ValidationError as e:
    print(f"Agent returned invalid data: {e}")
