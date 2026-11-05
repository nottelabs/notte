# Your API key is the password, the username picks the exit.
# The proxy URL goes in an environment variable, not on the command line,
# so the key does not show in the process list.
https_proxy="https://country-gb_sticky-checkout-42:$NOTTE_API_KEY@proxy.notte.cc:443" \
  curl --noproxy "" https://api.ipify.org
