// The frame's visible bounds and child-to-parent coordinate transform, in parent viewport coordinates.
element => {
    const scrollingElement = Object.getOwnPropertyDescriptor(Document.prototype, 'scrollingElement').get.call(document);
    const box = element.getBoundingClientRect();
    if (box.width <= 0 || box.height <= 0 || element.offsetWidth <= 0 || element.offsetHeight <= 0) return null;
    const scaleX = box.width / element.offsetWidth;
    const scaleY = box.height / element.offsetHeight;
    let left = Math.max(box.left, 0);
    let top = Math.max(box.top, 0);
    let right = Math.min(box.right, window.innerWidth);
    let bottom = Math.min(box.bottom, window.innerHeight);
    for (let node = element.parentElement || element.getRootNode().host; node;
        node = node.parentElement || node.getRootNode().host) {
        if (node === scrollingElement) continue;
        const style = getComputedStyle(node);
        if (style.display === 'inline' || style.display === 'contents') continue;
        const rect = node.getBoundingClientRect();
        if (style.overflowX !== 'visible') {
            const scale = node.offsetWidth > 0 ? rect.width / node.offsetWidth : 0;
            left = Math.max(left, rect.left + node.clientLeft * scale);
            right = Math.min(right, rect.left + (node.clientLeft + node.clientWidth) * scale);
        }
        if (style.overflowY !== 'visible') {
            const scale = node.offsetHeight > 0 ? rect.height / node.offsetHeight : 0;
            top = Math.max(top, rect.top + node.clientTop * scale);
            bottom = Math.min(bottom, rect.top + (node.clientTop + node.clientHeight) * scale);
        }
    }
    return {
        left, top, right, bottom, scaleX, scaleY,
        originX: box.left + element.clientLeft * scaleX,
        originY: box.top + element.clientTop * scaleY,
    };
}
