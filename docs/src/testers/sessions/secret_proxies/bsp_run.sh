# Basic auth that Notte sends with every CONNECT
export SECRET_PROXY_USERNAME=proxy-user
export SECRET_PROXY_PASSWORD='a-long-random-password'

./bin/browser-secret-proxy \
  -listen 127.0.0.1:8080 \
  -ca-cert ca.pem -ca-key ca.key \
  -hosts 'api.example.com' \
  -swaps swaps.json
