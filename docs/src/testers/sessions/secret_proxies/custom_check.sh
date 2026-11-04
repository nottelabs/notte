# Through your proxy, a listed host must present a certificate issued by your CA.
# --proxy-cacert verifies the proxy's own certificate with your CA; drop it if the
# proxy uses a certificate from a public CA.
curl -sv -o /dev/null \
  --proxy https://secret-proxy.example.com:443 \
  --proxy-user "YOUR_PROXY_USERNAME:YOUR_PROXY_PASSWORD" \
  --proxy-cacert your-ca.pem \
  --cacert your-ca.pem \
  https://api.stripe.com/
