// Report input before a handler can close its tab. The driver timestamps input and requests on one host clock.
(name, token) => {
    const notify = globalThis[name];
    const mark = () => { void notify(token); };
    const onInput = (event) => {
        if (event.isTrusted) mark();
    };
    window.addEventListener("pointerdown", onInput, true);
    return {
        mark,
        dispose: () => window.removeEventListener("pointerdown", onInput, true),
    };
}
