# sandbox.pem is the VGS certificate from your dashboard's "Code snippets" section
jq -n --arg ca "$(cat sandbox.pem)" '{
  proxies: [
    {type: "notte", country: "us"},
    {
      type: "secret",
      server: "https://tntXXXXXXXXX.sandbox.verygoodproxy.com:8443",
      username: "YOUR_VGS_ACCESS_CREDENTIAL_USERNAME",
      password: "YOUR_VGS_ACCESS_CREDENTIAL_PASSWORD",
      ca_certificate: $ca,
      hosts: ["api.stripe.com"]
    }
  ]
}' | curl -s -X POST https://api.notte.cc/sessions/start \
  -H "Authorization: Bearer $NOTTE_API_KEY" \
  -H "Content-Type: application/json" \
  -d @-
