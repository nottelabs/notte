# Through your proxy, a listed host must present a certificate issued by your CA
curl -sv -o /dev/null \
  --proxy https://secret-proxy.example.com:443 \
  --proxy-user "YOUR_PROXY_USERNAME:YOUR_PROXY_PASSWORD" \
  --cacert your-ca.pem \
  https://api.stripe.com/
