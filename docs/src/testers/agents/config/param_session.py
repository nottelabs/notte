# @sniptest filename=param_session.py
with client.Session(headless=False) as session:
    agent = client.Agent(session=session)
