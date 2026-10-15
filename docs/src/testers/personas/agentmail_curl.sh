# create a persona with an AgentMail inbox
curl -X POST https://api.notte.cc/personas/create \
  -H "Authorization: Bearer $NOTTE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"email_provider": "agentmail"}'

# read the persona's emails
curl "https://api.notte.cc/personas/YOUR_PERSONA_ID/emails?limit=10" \
  -H "Authorization: Bearer $NOTTE_API_KEY"
