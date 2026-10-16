// position of an iframe element among its document's elements (iframes in a shadow root take their host's position)
el => {
    let node = el;
    while (node.getRootNode() instanceof ShadowRoot) node = node.getRootNode().host;
    return Array.prototype.indexOf.call(node.ownerDocument.getElementsByTagName("*"), node);
}
