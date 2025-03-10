from notte.utils.code import is_code


def test_positive_code_examples():
    # Python code
    assert is_code("""
def hello_world():
    print("Hello, World!")
    return 42
""")

    # JavaScript code
    assert is_code("""
function calculateSum(a, b) {
    return a + b;
}
const result = calculateSum(5, 3);
""")

    # SQL code
    assert is_code("""
SELECT users.name, orders.order_date
FROM users
INNER JOIN orders ON users.id = orders.user_id
WHERE orders.status = 'completed';
""")


def test_negative_examples():
    # Empty string
    assert not is_code("")

    # Simple text
    assert not is_code("Hello World!")

    # Long natural text
    assert not is_code("""
The journey of personal growth requires consistent effort and dedication.
Embracing challenges helps develop resilience and character in the face of adversity.
When we commit to improving ourselves, we discover inner strength we never knew existed.
Each step forward, no matter how small, contributes to meaningful progress over time.
Setbacks are not failures but opportunities to learn and adapt our approach.
By maintaining focus on our goals while remaining flexible in our methods, we create sustainable paths to success.
The rewards of perseverance extend beyond individual achievement to positively impact those around us.
In moments of doubt, remember that determination often makes the difference between abandoning dreams and realizing them.
True fulfillment comes not from avoiding difficulty but from overcoming obstacles with integrity and purpose.
Those who recognize the value of consistent effort understand that meaningful accomplishment rarely happens by chance,
but through deliberate action and unwavering commitment to personal values.
""")


def test_edge_cases():
    # Whitespace only
    assert not is_code("   \n   \t   ")

    # Single line of punctuation
    assert not is_code("$$$$!!!")

    # Numbers only
    assert not is_code("12345 67890")
