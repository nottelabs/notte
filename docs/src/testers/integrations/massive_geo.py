# @sniptest filename=massive_geo.py
from notte_sdk.types import ExternalProxy

# Target a specific country
us_proxy = ExternalProxy(
    server="http://network.joinmassive.com:65534",
    username="your-username-country-US",
    password="your-password",
)

# Target a specific state
ca_proxy = ExternalProxy(
    server="http://network.joinmassive.com:65534",
    username="your-username-country-US-subdivision-CA",
    password="your-password",
)

# Target a specific city
sf_proxy = ExternalProxy(
    server="http://network.joinmassive.com:65534",
    username="your-username-country-US-subdivision-CA-city-San Francisco",
    password="your-password",
)

# Target mobile devices
mobile_proxy = ExternalProxy(
    server="http://network.joinmassive.com:65534",
    username="your-username-device-mobile",
    password="your-password",
)

# Combine geo + device targeting
combined_proxy = ExternalProxy(
    server="http://network.joinmassive.com:65534",
    username="your-username-country-US-subdivision-NY-city-New York-device-mobile",
    password="your-password",
)
