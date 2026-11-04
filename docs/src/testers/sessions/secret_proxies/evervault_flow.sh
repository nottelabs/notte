# 1. Mint a Notte gateway credential pinned to one residential exit
GATEWAY=$(curl -s -X POST https://api.notte.cc/proxies/gateway/credentials \
  -H "Authorization: Bearer $NOTTE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"country": "us", "sticky_session": "checkout-4821"}')

# 2. Create Browser Tokens; Evervault's egress goes through Notte's gateway
TOKENS=$(jq -n --argjson gw "$GATEWAY" '{
  data: [
    {category: "card.number", value: "ev:encrypted:...", id: "card-number"},
    {category: "card.cvv", value: "ev:encrypted:...", id: "card-cvv"}
  ],
  permissions: [{action: "decrypt", target: "api.stripe.com"}],
  ttl: 900,
  proxySettings: {
    type: "custom",
    scheme: "https",
    hostname: "proxy.notte.cc",
    port: 443,
    username: $gw.username,
    password: $gw.password
  }
}' | curl -s -X POST https://api.evervault.com/browser-tokens \
  -u "$EVERVAULT_APP_ID:$EVERVAULT_API_KEY" \
  -H "Content-Type: application/json" \
  -d @-)

# 3. Start the Notte session: same sticky_session and country, Evervault's relay for the listed host
CA=$(curl -s https://ca.evervault.com)
jq -n --argjson t "$TOKENS" --arg ca "$CA" '{
  proxies: [
    {type: "notte", country: "us", sticky_session: "checkout-4821"},
    {
      type: "secret",
      server: "https://\($t.proxyConfiguration.hostname):\($t.proxyConfiguration.port)",
      username: $t.proxyConfiguration.username,
      password: $t.proxyConfiguration.password,
      ca_certificate: $ca,
      hosts: ["api.stripe.com"]
    }
  ]
}' | curl -s -X POST https://api.notte.cc/sessions/start \
  -H "Authorization: Bearer $NOTTE_API_KEY" \
  -H "Content-Type: application/json" \
  -d @-

# 4. The stand-in values the agent types
echo "$TOKENS" | jq '.data'
