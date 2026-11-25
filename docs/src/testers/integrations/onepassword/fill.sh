curl -s https://api.notte.cc/sessions/$SESSION_ID/onepassword/fill \
  -H "Authorization: Bearer $NOTTE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"grant_id": "'"$GRANT_ID"'", "url": "https://merchant.example.com/login"}'
