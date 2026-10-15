(el) => {
    const isDisabled = (node) =>
        node.disabled === true ||
        node.inert === true ||
        node.getAttribute('disabled') !== null ||
        node.getAttribute('aria-disabled') === 'true';
    let node = el;
    while (node !== null) {
        if (isDisabled(node)) {
            return true;
        }
        if (node.assignedSlot) {
            node = node.assignedSlot;
            continue;
        }
        const root = node.getRootNode && node.getRootNode();
        node = root instanceof ShadowRoot ? root.host : node.parentElement;
    }
    return false;
}
