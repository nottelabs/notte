(function () {
  if (window.__notte404Redirect) {
    return;
  }
  window.__notte404Redirect = true;

  function isHome() {
    return location.pathname === "/" || location.pathname === "";
  }

  function isNotFoundPage() {
    if (isHome()) {
      return false;
    }
    var title = document.title || "";
    if (title === "Page Not Found" || title.indexOf("Page Not Found") === 0) {
      return true;
    }
    var heading = document.querySelector("h1");
    var headingText = heading ? heading.textContent.trim() : "";
    if (headingText !== "404" && headingText !== "Page Not Found") {
      return false;
    }
    var body = (document.body && document.body.innerText) || "";
    return body.indexOf("We couldn't find the page") !== -1 || headingText === "Page Not Found";
  }

  function maybeRedirect() {
    if (!isNotFoundPage()) {
      return;
    }
    if (document.documentElement) {
      document.documentElement.style.visibility = "hidden";
    }
    location.replace("/");
  }

  maybeRedirect();

  function watch() {
    maybeRedirect();
    if (!document.body) {
      requestAnimationFrame(watch);
      return;
    }
    new MutationObserver(maybeRedirect).observe(document.documentElement, {
      childList: true,
      subtree: true
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", watch);
  } else {
    watch();
  }
})();

(function () {
  if (window.__notteSidebarToggle === 11) {
    return;
  }
  var shouldBindKeys = !window.__notteSidebarToggle;
  window.__notteSidebarToggle = 11;

  var CLASS = "notte-sidebar-hidden";
  var STORAGE_KEY = "notte-docs-sidebar-hidden";
  var BUTTON_ID = "notte-sidebar-toggle";
  var RAIL_ID = "notte-sidebar-rail-toggle";
  var TIP_ID = "notte-sidebar-tooltip";
  var BUTTON_HTML =
    '<span class="notte-toggle-logo" aria-hidden="true">' +
    '<img class="notte-toggle-logo-light" src="/logo/notte-mark.svg" alt="" />' +
    '<img class="notte-toggle-logo-dark" src="/logo/notte-mark-white.svg" alt="" />' +
    "</span>" +
    '<span class="notte-toggle-icon">' +
    '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect width="18" height="18" x="3" y="3" rx="4"></rect><path d="M9 3v18"></path></svg>' +
    "</span>";

  var tipTimer = null;
  var tipAnchor = null;

  function isMac() {
    return /Mac|iPhone|iPad|iPod/.test(navigator.platform || "");
  }

  function shortcutLabel() {
    return isMac() ? "⌘B" : "Ctrl+B";
  }

  function isTypingTarget(el) {
    if (!el || el.nodeType !== 1) {
      return false;
    }
    var tag = el.tagName;
    if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") {
      return true;
    }
    if (el.isContentEditable) {
      return true;
    }
    return Boolean(el.closest("[contenteditable='true']"));
  }

  function isHidden() {
    return document.documentElement.classList.contains(CLASS);
  }

  function actionLabel() {
    return isHidden() ? "Expand sidebar" : "Collapse sidebar";
  }

  function ensureTip() {
    var tip = document.getElementById(TIP_ID);
    if (tip) {
      return tip;
    }
    tip = document.createElement("div");
    tip.id = TIP_ID;
    tip.setAttribute("role", "tooltip");
    tip.setAttribute("aria-hidden", "true");
    tip.innerHTML =
      '<span class="notte-toggle-tooltip-action"></span>' +
      '<span class="notte-toggle-tooltip-shortcut"></span>';
    document.body.appendChild(tip);
    return tip;
  }

  function hideTip() {
    window.clearTimeout(tipTimer);
    tipTimer = null;
    tipAnchor = null;
    var tip = document.getElementById(TIP_ID);
    if (tip) {
      tip.classList.remove("is-visible");
    }
  }

  function placeTip(anchor, side) {
    var tip = ensureTip();
    var actionEl = tip.querySelector(".notte-toggle-tooltip-action");
    var shortcutEl = tip.querySelector(".notte-toggle-tooltip-shortcut");
    if (actionEl) {
      actionEl.textContent = actionLabel();
    }
    if (shortcutEl) {
      shortcutEl.textContent = shortcutLabel();
    }
    tip.classList.add("is-visible");
    var rect = anchor.getBoundingClientRect();
    var tw = tip.offsetWidth;
    var th = tip.offsetHeight;
    var top;
    var left;
    if (side === "right") {
      top = rect.top + rect.height / 2 - th / 2;
      left = rect.right + 8;
    } else {
      top = rect.bottom + 8;
      left = rect.left;
    }
    tip.style.top = Math.max(8, top) + "px";
    tip.style.left = Math.max(8, left) + "px";
  }

  function showTip(anchor, side) {
    window.clearTimeout(tipTimer);
    tipAnchor = anchor;
    clearTitle(anchor);
    placeTip(anchor, side);
  }

  function clearTitle(btn) {
    if (!btn) {
      return;
    }
    if (btn.hasAttribute("title")) {
      btn.removeAttribute("title");
    }
    var titled = btn.querySelectorAll("[title]");
    for (var i = 0; i < titled.length; i += 1) {
      titled[i].removeAttribute("title");
    }
  }

  function bindTip(btn, side) {
    if (!btn || btn.getAttribute("data-notte-tip") === "1") {
      return;
    }
    btn.setAttribute("data-notte-tip", "1");
    clearTitle(btn);
    btn.addEventListener("mouseenter", function () {
      clearTitle(btn);
      showTip(btn, side);
    });
    btn.addEventListener("mouseleave", hideTip);
    btn.addEventListener("focus", function () {
      clearTitle(btn);
      showTip(btn, side);
    });
    btn.addEventListener("blur", hideTip);
    btn.addEventListener("click", hideTip);
  }

  function setHidden(hidden) {
    document.documentElement.classList.toggle(CLASS, hidden);
    try {
      localStorage.setItem(STORAGE_KEY, hidden ? "1" : "0");
    } catch (err) {
      /* ignore quota / private mode */
    }
    hideTip();
    syncButton();
  }

  function toggle() {
    setHidden(!isHidden());
  }

  function syncToggle(btn) {
    if (!btn) {
      return;
    }
    var action = actionLabel();
    btn.setAttribute("aria-pressed", isHidden() ? "true" : "false");
    btn.setAttribute("aria-label", action);
    clearTitle(btn);
  }

  function syncButton() {
    syncToggle(document.getElementById(BUTTON_ID));
    syncToggle(document.getElementById(RAIL_ID));
  }

  function findMount() {
    var maple = document.getElementById("navbar-transition-maple");
    if (maple) {
      var mapleTabs = maple.querySelector(".nav-tabs");
      return { parent: maple, before: mapleTabs || maple.firstChild };
    }
    var tabs = document.querySelector(".nav-tabs");
    if (tabs && tabs.parentElement) {
      return { parent: tabs.parentElement, before: tabs };
    }
    var logo = document.querySelector("#sidebar .nav-logo") || document.querySelector("#navbar .nav-logo");
    var logoLink = logo && logo.closest("a");
    if (logoLink) {
      var slot = logoLink.nextElementSibling;
      if (
        slot &&
        slot.tagName === "DIV" &&
        slot.classList.contains("hidden") &&
        slot.classList.contains("lg:flex")
      ) {
        return { parent: slot, before: slot.firstChild };
      }
      if (logoLink.parentElement) {
        return { parent: logoLink.parentElement, before: logoLink };
      }
    }
    var row = document.querySelector("#navbar .flex.items-center");
    if (row) {
      return { parent: row, before: row.firstChild };
    }
    return null;
  }

  function ensureButton() {
    var mount = findMount();
    var btn = document.getElementById(BUTTON_ID);
    if (!mount) {
      if (btn) {
        syncButton();
      }
      return;
    }
    if (!btn) {
      btn = document.createElement("button");
      btn.id = BUTTON_ID;
      btn.type = "button";
      btn.className = "notte-sidebar-toggle";
      btn.setAttribute("aria-controls", "sidebar");
      btn.innerHTML = BUTTON_HTML;
      btn.addEventListener("click", toggle);
      mount.parent.insertBefore(btn, mount.before || null);
    } else {
      if (btn.parentElement !== mount.parent) {
        mount.parent.insertBefore(btn, mount.before || null);
      }
      if (btn.innerHTML.indexOf("notte-toggle-logo") === -1) {
        btn.innerHTML = BUTTON_HTML;
      }
    }
    bindTip(btn, "bottom");
    var staleBrand = document.getElementById("notte-header-brand");
    if (staleBrand) {
      staleBrand.remove();
    }
    ensureRailButton();
    syncButton();
  }

  function ensureRailButton() {
    var sidebar = document.getElementById("sidebar");
    var rail = document.getElementById(RAIL_ID);
    if (!sidebar) {
      return;
    }
    if (!rail) {
      rail = document.createElement("button");
      rail.id = RAIL_ID;
      rail.type = "button";
      rail.className = "notte-sidebar-rail-toggle";
      rail.setAttribute("aria-controls", "sidebar");
      rail.innerHTML = BUTTON_HTML;
      rail.addEventListener("click", toggle);
      sidebar.insertBefore(rail, sidebar.firstChild);
    } else {
      if (rail.parentElement !== sidebar) {
        sidebar.insertBefore(rail, sidebar.firstChild);
      }
      if (rail.innerHTML.indexOf("notte-toggle-logo") === -1) {
        rail.innerHTML = BUTTON_HTML;
      }
    }
    bindTip(rail, "right");
  }

  try {
    if (localStorage.getItem(STORAGE_KEY) === "1") {
      document.documentElement.classList.add(CLASS);
    }
  } catch (err) {
    /* ignore */
  }

  if (shouldBindKeys) {
    document.addEventListener("keydown", function (event) {
      if (!(event.metaKey || event.ctrlKey) || event.altKey || event.shiftKey) {
        return;
      }
      if (String(event.key).toLowerCase() !== "b") {
        return;
      }
      if (isTypingTarget(event.target)) {
        return;
      }
      event.preventDefault();
      toggle();
    });
  }

  function watch() {
    if (!document.body) {
      requestAnimationFrame(watch);
      return;
    }
    ensureTip();
    ensureButton();
    new MutationObserver(function () {
      if (!document.getElementById(BUTTON_ID) || !document.getElementById(RAIL_ID)) {
        ensureButton();
      }
    }).observe(document.body, { childList: true, subtree: true });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", watch);
  } else {
    watch();
  }
})();

(function () {
  var FOOTER_HREFS = [
    "https://join.slack.com/t/nottelabs-dev/shared_invite/",
    "https://cal.com/team/notte/demo",
    "https://console.notte.cc"
  ];

  function isFooterHref(href) {
    if (!href) {
      return false;
    }
    return FOOTER_HREFS.some(function (prefix) {
      return href.indexOf(prefix) === 0;
    });
  }

  function hideHeaderFooterLinks(root) {
    if (!root) {
      return;
    }
    Array.prototype.forEach.call(root.querySelectorAll("a[href]"), function (anchor) {
      if (!isFooterHref(anchor.href)) {
        return;
      }
      var item = anchor.closest("li") || anchor;
      item.hidden = true;
    });
  }

  function cleanupHeaderClones() {
    var host = document.getElementById("notte-navbar-links");
    if (host) {
      host.remove();
    }
    Array.prototype.forEach.call(
      document.querySelectorAll("#navbar-transition-maple .notte-navbar-links, #navbar-transition-maple .notte-navbar-link"),
      function (el) {
        el.remove();
      }
    );
    hideHeaderFooterLinks(document.getElementById("navbar-transition-maple"));
    hideHeaderFooterLinks(document.getElementById("navbar"));

    var sidebar = document.getElementById("sidebar");
    if (!sidebar) {
      return;
    }
    Array.prototype.forEach.call(sidebar.querySelectorAll("a[href]"), function (anchor) {
      if (!isFooterHref(anchor.href)) {
        return;
      }
      var item = anchor.closest("li");
      if (item) {
        item.hidden = false;
      }
      var list = anchor.closest("ul");
      if (list) {
        list.hidden = false;
      }
    });
  }

  function watch() {
    cleanupHeaderClones();
    if (!document.body) {
      requestAnimationFrame(watch);
      return;
    }
    new MutationObserver(cleanupHeaderClones).observe(document.body, {
      childList: true,
      subtree: true
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", watch);
  } else {
    watch();
  }
})();
