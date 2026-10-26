// Whether a point in the parent viewport reaches the iframe, including through shadow hosts.
(element, {x, y}) => {
    let target = element;
    while (target) {
        const root = target.getRootNode();
        if (root.elementFromPoint(x, y) !== target) return false;
        target = root.host;
    }
    return true;
}
