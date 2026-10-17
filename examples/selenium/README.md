# Selenium with Notte

Use normal Selenium WebDriver commands with a hosted Notte browser. A small loopback bridge connects local ChromeDriver to Notte's authenticated CDP connection. Chrome runs on Notte.

Requires Python 3.12+, a [Notte API key](https://console.notte.cc), and a local ChromeDriver matching the hosted browser's major version. TypeScript also requires Node.js 24+.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export NOTTE_API_KEY=your-notte-api-key
export CHROMEDRIVER_PATH="$(python install_driver.py)"
python main.py
```

The setup script briefly creates a Notte session to discover its browser version, closes it, and downloads only ChromeDriver from [Chrome for Testing](https://googlechromelabs.github.io/chrome-for-testing/). Alternatively, set `CHROMEDRIVER_PATH` to an existing matching binary. No local Chrome installation is needed.

For TypeScript, keep the same environment, run `npm ci`, then `npm start`. Both demos print `Example Domain` and close their driver, bridge and Notte session.

Use `connect_driver` / `connectDriver` with the bridge address for existing Selenium code. The bridge binds to `127.0.0.1` on an ephemeral port and uses a random WebSocket path. Keep its lifetime inside the owned Notte session. ChromeDriver's [remote debugging restrictions](https://developer.chrome.com/docs/chromedriver/help/operation-not-supported-when-using-remote-debugging) apply, including unsupported window resizing.

For live tests, choose `NOTTE_API_URL` explicitly, set `NOTTE_SELENIUM_LIVE=1`, then run `python -m unittest -v test_selenium` and `npm run test:live`. The tests exercise the unchanged demos, native waits/typing/clicks, reconnecting to the same browser, and cleanup after a real command failure.
