# Send browser captures to Box

Capture a page in a hosted Notte browser and store the PNG in Box. The example closes its browser session before uploading, then verifies the file's size and SHA1 metadata through the Box API.

Requires a [Notte API key](https://console.notte.cc), a [Box access token](https://app.box.com/developers/console), and Python 3.12+ or Node.js 24+.

Set `NOTTE_API_KEY` and `BOX_ACCESS_TOKEN`. Optionally set `BOX_FOLDER_ID` to an accessible Box folder; the default `0` is the authenticated account's root folder.

For Python, create a virtual environment, install `requirements.txt`, and run `python main.py`. For TypeScript, run `npm ci` then `npm start`. Neither needs a local browser installation.

The result contains the new `box_file_id` and stopped browser's `session_id`. The uploaded file remains in your Box folder.

A [developer token](https://developer.box.com/guides/authentication/tokens/developer-tokens/) lasts 60 minutes and is intended for testing. Use [Box OAuth or server authentication](https://developer.box.com/guides/authentication/) for a deployed workflow.

Run offline upload-contract checks with `python -m unittest test_upload` or `npm test`. Set `NOTTE_BOX_CAPTURE_LIVE=1` and an explicit `NOTTE_API_URL` to test the hosted capture and browser cleanup with `python -m unittest test_capture` or `npm run test:capture`.

Box upload, metadata verification, and errors are contract-tested; this example was shipped without a live Box account. To run the optional real-account tests, set `NOTTE_BOX_LIVE=1`, `BOX_ACCESS_TOKEN`, and `NOTTE_API_URL`, then run `python -m unittest test_box` or `npm run test:live`. They create an isolated folder and remove only their own files and folder.
