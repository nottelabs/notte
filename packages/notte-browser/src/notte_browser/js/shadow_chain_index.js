(elements, steps) => {
    // The index among `elements` of the element an XPath chain through shadow roots leads to (see
    // `selectors_through_shadow_dom`), or -1. The first step starts at the document; each other step at the
    // element of the step before: in its light tree when it starts with "/", else in its shadow root.
    // The steps are walked here, not by `document.evaluate`: XPath cannot start at a shadow root, and its name
    // tests do not match SVG elements in an HTML document (`svg/a`). Native getters: a form field named
    // `children` or `shadowRoot` hides the property of its form
    const getter = (prototype, name) => Object.getOwnPropertyDescriptor(prototype, name).get;
    const elementChildren = getter(Element.prototype, "children");
    const fragmentChildren = getter(DocumentFragment.prototype, "children");
    const documentChildren = getter(Document.prototype, "children");
    const shadowRootOf = getter(Element.prototype, "shadowRoot");
    const nodeNameOf = getter(Node.prototype, "nodeName");
    const childrenOf = (parent) => {
        if (parent instanceof Document) return documentChildren.call(parent);
        if (parent instanceof DocumentFragment) return fragmentChildren.call(parent);
        return elementChildren.call(parent);
    };
    // a step of a generated XPath: a tag, with its 1-based position among its siblings of that tag when it has some
    const childAt = (parent, segment) => {
        const [, tagName, position] = /^([^[\]]+)(?:\[(\d+)\])?$/.exec(segment) ?? [];
        if (tagName === undefined) return null;
        const sameTag = Array.from(childrenOf(parent)).filter((child) => nodeNameOf.call(child).toLowerCase() === tagName);
        return sameTag[Number(position ?? 1) - 1] ?? null;
    };
    const walk = (path, context) => {
        let node = context;
        for (const segment of path.split("/").filter(Boolean)) {
            node = childAt(node, segment);
            if (node === null) return null;
        }
        return node;
    };
    let target = walk(steps[0], document);
    for (const step of steps.slice(1)) {
        if (target === null) return -1;
        if (step.startsWith("/")) {
            target = walk(step, target);
        } else {
            const root = shadowRootOf.call(target);
            target = root === null ? null : walk(step, root);
        }
    }
    return target === null ? -1 : elements.indexOf(target);
}
