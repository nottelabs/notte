// Records the clicks that reach an enabled file input, whose default action opens its file chooser: a click on the
// input or on its label, or a script calling `input.click()`. Read once the click is over, when a page handler that
// cancels it has run.
() => {
    const clicks = [];
    const onClick = (event) => {
        const input = event.composedPath().find((node) => node instanceof HTMLInputElement && node.type === 'file');
        if (input !== undefined && !input.disabled) clicks.push(event);
    };
    window.addEventListener('click', onClick, true);
    return {
        opened: () => clicks.some((event) => !event.defaultPrevented),
        dispose: () => window.removeEventListener('click', onClick, true),
    };
}
