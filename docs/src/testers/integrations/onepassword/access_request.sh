curl -s https://api.notte.cc/sessions/$SESSION_ID/onepassword/access-requests \
  -H "Authorization: Bearer $NOTTE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "goal": "Download this month'\''s invoices",
    "entries": [{"website": "https://merchant.example.com", "reason": "Sign in to the merchant portal"}]
  }'
