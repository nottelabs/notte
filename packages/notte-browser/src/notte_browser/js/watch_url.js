// `watchUrl(onChange)` calls `onChange()` when the page's URL changes within the document (pushState, replaceState,
// a hash change), even with no DOM change, and returns a function that stops watching. The Navigation API's
// `currententrychange` fires within the change; a 50 ms poll covers the rest.
(onChange) => {
    let url = location.href;
    const check = () => {
        if (location.href === url) return;
        url = location.href;
        onChange();
    };
    const navigation = window.navigation;
    if (navigation) navigation.addEventListener("currententrychange", check);
    window.addEventListener("hashchange", check);
    window.addEventListener("popstate", check);
    const poll = setInterval(check, 50);
    return () => {
        if (navigation) navigation.removeEventListener("currententrychange", check);
        window.removeEventListener("hashchange", check);
        window.removeEventListener("popstate", check);
        clearInterval(poll);
    };
}
