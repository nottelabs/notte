# Browser Snapshot Preprocessing

This pipeline is used to preprocess browser snapshots.

There are 3 alternative routes you can take for this pipeline:

1. `html`: only extract the HTML content of the page and process it (no javascript)
2. `dom`: interacts with the DOM of the page to extract relevant content
3. `a11y`: works at accessibility tree level
