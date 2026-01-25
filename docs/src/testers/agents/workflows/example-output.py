from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    # Step 1: Navigate to login page
    session.execute(type="goto", url="https://example.com/login")

    # Step 2: Fill email field
    session.execute(type="fill", selector="input[name='email']", value="user@example.com")

    # Step 3: Fill password field
    session.execute(type="fill", selector="input[name='password']", value="********")

    # Step 4: Click login button
    session.execute(type="click", selector="button[type='submit']")

    # Step 5: Wait for dashboard
    session.execute(type="goto", url="https://example.com/dashboard")
