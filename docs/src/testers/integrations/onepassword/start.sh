curl -s https://api.notte.cc/sessions/start \
  -H "Authorization: Bearer $NOTTE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"onepassword": true}'
