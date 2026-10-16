// Capture the wheel target's ancestors before the browser performs its default
// scroll. Keeping element references avoids mistaking DOM replacement for motion,
// and composedPath includes scroll containers inside open shadow roots.
() => {
    const initialY = window.scrollY;
    const positions = new Map();
    const onWheel = (event) => {
        for (const node of event.composedPath()) {
            if (node instanceof Element && !positions.has(node)) {
                positions.set(node, node.scrollTop);
            }
        }
    };
    // A passive listener can run after compositor scrolling has already happened.
    // This listener never cancels the event, but must snapshot before its default action.
    window.addEventListener('wheel', onWheel, {capture: true, passive: false});
    return {
        hasScrolled: () => window.scrollY !== initialY ||
            Array.from(positions).some(([node, top]) => node.isConnected && node.scrollTop !== top),
        dispose: () => {
            window.removeEventListener('wheel', onWheel, true);
            positions.clear();
        },
    };
}
