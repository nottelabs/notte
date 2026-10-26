(elements, steps) => {
    // The index among `elements` of the element an XPath chain through shadow roots leads to (see
    // `selectors_through_shadow_dom`), or -1. The first step starts at the document; each other step at the
    // element of the step before: in its light tree when it starts with "/", else in its shadow root.
    const at = (path, context) =>
        document.evaluate(path, context, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
    // XPath cannot start at a shadow root: the first step of the path (`tag` or `tag[2]`) is matched here
    const inShadowRoot = (path, root) => {
        const [first, ...rest] = path.split("/");
        const [, tagName, position] = /^([^[\]]+)(?:\[(\d+)\])?$/.exec(first) ?? [];
        if (tagName === undefined) return null;
        const sameTag = Array.from(root.children).filter((element) => element.nodeName.toLowerCase() === tagName);
        const child = sameTag[Number(position ?? 1) - 1];
        if (child === undefined) return null;
        return rest.length === 0 ? child : at(`./${rest.join("/")}`, child);
    };
    let target = at(steps[0], document);
    for (const step of steps.slice(1)) {
        if (target === null) return -1;
        if (step.startsWith("/")) {
            target = at(`.${step}`, target);
        } else {
            target = target.shadowRoot === null ? null : inShadowRoot(step, target.shadowRoot);
        }
    }
    return target === null ? -1 : elements.indexOf(target);
}
