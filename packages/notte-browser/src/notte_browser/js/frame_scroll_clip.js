// The visible part of a frame element, relative to its bounding box in its parent document.
element => {
    const box = element.getBoundingClientRect();
    let left = Math.max(box.left, 0);
    let top = Math.max(box.top, 0);
    let right = Math.min(box.right, window.innerWidth);
    let bottom = Math.min(box.bottom, window.innerHeight);
    for (let node = element.parentElement || element.getRootNode().host; node;
        node = node.parentElement || node.getRootNode().host) {
        const style = getComputedStyle(node);
        const rect = node.getBoundingClientRect();
        if (style.overflowX !== 'visible') {
            left = Math.max(left, rect.left + node.clientLeft);
            right = Math.min(right, rect.left + node.clientLeft + node.clientWidth);
        }
        if (style.overflowY !== 'visible') {
            top = Math.max(top, rect.top + node.clientTop);
            bottom = Math.min(bottom, rect.top + node.clientTop + node.clientHeight);
        }
    }
    return {left: left - box.left, top: top - box.top, right: right - box.left, bottom: bottom - box.top};
}
