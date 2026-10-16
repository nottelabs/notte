(element, delta) => {
    const max = Math.max(0, element.scrollHeight - element.clientHeight);
    const style = getComputedStyle(element);
    const isContainer = element === document.scrollingElement ||
        /^(auto|scroll|overlay)$/.test(style.overflowY) ||
        (max > 0 && style.overflowY === 'hidden');
    const reversed = /^(flex|inline-flex)$/.test(style.display) && style.flexDirection === 'column-reverse';
    const lower = reversed ? -max : 0;
    const upper = reversed ? 0 : max;
    return isContainer && (delta > 0 ? element.scrollTop >= upper - 1 : element.scrollTop <= lower + 1);
}
