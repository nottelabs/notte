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

/* Developer-manual effects: sidebar decode-on-hover, hero ASCII clusters, binary card backgrounds. */
(function () {
  if (window.__notteManualFx) {
    return;
  }
  window.__notteManualFx = true;

  var LETTERS = "abcdefghijklmnopqrstuvwxyz";
  var CLUSTER_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789#@&+=";
  var reduceMotion = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function randomLetter() {
    return LETTERS.charAt(Math.floor(Math.random() * LETTERS.length));
  }

  function labelOf(link) {
    return link.querySelector("span.min-w-0") || link.querySelector("div > span");
  }

  function tagLabels(root) {
    var links = root.querySelectorAll("#navigation-items .sidebar-group li > a, #navigation-items .sidebar-group li > button");
    for (var i = 0; i < links.length; i++) {
      var label = labelOf(links[i]);
      if (label && !label.classList.contains("nv-label")) {
        label.classList.add("nv-label");
      }
    }
  }

  // A few decodes may overlap (oldest cancelled past MAX_RUNNING). Everything they need lives
  // in inline styles on the label, which Mintlify's re-renders leave alone (they can reset the
  // className mid-animation).
  var HOVER_INTENT_MS = 25;
  var MAX_RUNNING = 3;
  var running = [];
  var pending = null;

  function isRunning(label) {
    for (var i = 0; i < running.length; i++) {
      if (running[i].label === label) {
        return true;
      }
    }
    return false;
  }

  function stopScramble(state) {
    var index = running.indexOf(state);
    if (index !== -1) {
      running.splice(index, 1);
    }
    state.cancelled = true;
    if (state.overlay.parentNode) {
      state.overlay.parentNode.removeChild(state.overlay);
    }
    state.label.style.removeProperty("-webkit-text-fill-color");
    state.label.style.removeProperty("position");
  }

  function cancelPending() {
    if (pending) {
      clearTimeout(pending.timer);
      pending = null;
    }
  }

  function scramble(label) {
    if (reduceMotion || !label.isConnected || isRunning(label)) {
      return;
    }
    var text = label.textContent;
    if (!text) {
      return;
    }
    while (running.length >= MAX_RUNNING) {
      stopScramble(running[0]);
    }
    var overlay = document.createElement("span");
    overlay.className = "nv-scramble";
    overlay.setAttribute("aria-hidden", "true");
    overlay.style.cssText =
      "position:absolute;left:0;top:0;white-space:pre;pointer-events:none;-webkit-text-fill-color:currentColor;";
    var clear = document.createElement("span");
    var enc = document.createElement("span");
    enc.style.opacity = "0.25";
    overlay.appendChild(clear);
    overlay.appendChild(enc);
    label.style.setProperty("position", "relative");
    label.style.setProperty("-webkit-text-fill-color", "transparent");
    label.appendChild(overlay);

    var state = { label: label, overlay: overlay, cancelled: false };
    running.push(state);
    var duration = Math.min(420, 90 + text.length * 22);
    var start = performance.now();

    function frame(now) {
      if (state.cancelled) {
        return;
      }
      if (!overlay.isConnected) {
        stopScramble(state);
        return;
      }
      var progress = Math.min(1, (now - start) / duration);
      var revealed = Math.floor(progress * text.length);
      var tail = "";
      for (var i = revealed; i < text.length; i++) {
        tail += text.charAt(i) === " " ? " " : randomLetter();
      }
      clear.textContent = text.slice(0, revealed);
      enc.textContent = tail;
      if (progress < 1) {
        setTimeout(function () {
          requestAnimationFrame(frame);
        }, 30);
        return;
      }
      stopScramble(state);
    }

    requestAnimationFrame(frame);
  }

  function sidebarLabelAt(target) {
    if (!target || !target.closest) {
      return null;
    }
    var link = target.closest("#navigation-items .sidebar-group li > a, #navigation-items .sidebar-group li > button");
    if (!link) {
      return null;
    }
    var label = labelOf(link);
    // Only the text itself activates the effect, not the whole row.
    return label && label.contains(target) ? label : null;
  }

  document.addEventListener("mouseover", function (event) {
    var label = sidebarLabelAt(event.target);
    if (!label) {
      cancelPending();
      return;
    }
    if (isRunning(label) || (pending && pending.label === label)) {
      return;
    }
    cancelPending();
    label.classList.add("nv-label");
    pending = {
      label: label,
      timer: setTimeout(function () {
        pending = null;
        scramble(label);
      }, HOVER_INTENT_MS)
    };
  });

  document.addEventListener("mouseout", function (event) {
    if (pending && pending.label.contains(event.target) && !pending.label.contains(event.relatedTarget)) {
      cancelPending();
    }
  });

  // Seeded so the card backgrounds stay identical across client navigations.
  function seeded(seed) {
    var state = seed >>> 0;
    return function () {
      state = (state * 1664525 + 1013904223) >>> 0;
      return state / 4294967296;
    };
  }

  function fillBinary(root) {
    var blocks = root.querySelectorAll(".nv-binary:not([data-nv-filled])");
    for (var b = 0; b < blocks.length; b++) {
      var rand = seeded(7919 * (b + 1));
      var bits = "";
      for (var i = 0; i < 4200; i++) {
        bits += rand() < 0.5 ? "0" : "1";
      }
      blocks[b].textContent = bits;
      blocks[b].setAttribute("data-nv-filled", "true");
    }
  }

  function clusterChar() {
    return Math.random() < 0.35 ? " " : CLUSTER_CHARS.charAt(Math.floor(Math.random() * CLUSTER_CHARS.length));
  }

  var OPACITIES = [0.45, 0.58, 0.76, 0.99];

  function buildClusters(root) {
    var clusters = root.querySelectorAll(".nv-cluster:not([data-nv-built])");
    for (var c = 0; c < clusters.length; c++) {
      var cluster = clusters[c];
      for (var l = 1; l <= 8; l++) {
        var line = document.createElement("div");
        line.className = "nv-cluster__line";
        var chars = l * 3;
        var str = "";
        for (var k = 0; k < chars; k++) {
          str += clusterChar() + (k < chars - 1 ? "\n" : "");
        }
        line.textContent = str;
        line.style.opacity = OPACITIES[Math.floor(Math.random() * OPACITIES.length)];
        cluster.appendChild(line);
      }
      cluster.setAttribute("data-nv-built", "true");
    }
  }

  function twinkle() {
    if (reduceMotion || document.hidden) {
      return;
    }
    var lines = document.querySelectorAll(".nv-cluster__line");
    for (var i = 0; i < lines.length; i++) {
      if (Math.random() < 0.3) {
        lines[i].style.opacity = OPACITIES[Math.floor(Math.random() * OPACITIES.length)];
      }
      if (Math.random() < 0.25) {
        var parts = lines[i].textContent.split("\n");
        var idx = Math.floor(Math.random() * parts.length);
        parts[idx] = clusterChar();
        lines[i].textContent = parts.join("\n");
      }
    }
  }

  function apply() {
    tagLabels(document);
    fillBinary(document);
    buildClusters(document);
  }

  function watch() {
    apply();
    var pending = false;
    new MutationObserver(function () {
      if (pending) {
        return;
      }
      pending = true;
      requestAnimationFrame(function () {
        pending = false;
        apply();
      });
    }).observe(document.body, { childList: true, subtree: true });
    setInterval(twinkle, 900);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", watch);
  } else {
    watch();
  }
})();

/* Single light/dark toggle at the right end of the tab bar; drives Mintlify's own theme switch. */
(function () {
  if (window.__notteThemeToggle) {
    return;
  }
  window.__notteThemeToggle = true;

  var ID = "notte-theme-toggle";
  var SUN =
    '<svg class="notte-theme-toggle__sun" xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="4"></circle><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41"></path></svg>';
  var MOON =
    '<svg class="notte-theme-toggle__moon" xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"></path></svg>';

  function isDark() {
    var root = document.documentElement;
    return root.classList.contains("dark") || root.getAttribute("data-theme") === "dark";
  }

  function sync(btn) {
    var label = isDark() ? "Switch to light theme" : "Switch to dark theme";
    btn.setAttribute("aria-label", label);
    btn.setAttribute("title", label);
  }

  function toggle() {
    var target = isDark() ? "light" : "dark";
    var option = document.querySelector('button[data-theme-preference-value="' + target + '"]');
    if (option) {
      option.click();
    }
  }

  var ACTIONS_ID = "notte-topbar-actions";
  var CONSOLE_HTML =
    '<a class="notte-console-link" href="https://console.notte.cc" target="_blank" rel="noopener noreferrer">Console' +
    '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M15 3h6v6"></path><path d="M10 14 21 3"></path><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path></svg>' +
    "</a>";

  function ensure() {
    var btn = document.getElementById(ID);
    if (!btn) {
      var actions = document.createElement("div");
      actions.id = ACTIONS_ID;
      actions.className = "notte-topbar-actions";
      btn = document.createElement("button");
      btn.id = ID;
      btn.type = "button";
      btn.className = "notte-theme-toggle";
      btn.innerHTML = SUN + MOON;
      btn.addEventListener("click", toggle);
      actions.appendChild(btn);
      actions.insertAdjacentHTML("beforeend", CONSOLE_HTML);
      document.body.appendChild(actions);
    }
    sync(btn);
  }

  function watch() {
    if (!document.body) {
      requestAnimationFrame(watch);
      return;
    }
    ensure();
    new MutationObserver(ensure).observe(document.documentElement, { attributes: true, attributeFilter: ["class", "data-theme"] });
    new MutationObserver(function () {
      if (!document.getElementById(ID)) {
        ensure();
      }
    }).observe(document.body, { childList: true });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", watch);
  } else {
    watch();
  }
})();

/* Live status of the Core APIs on status.notte.cc (Better Stack's public index.json), at the bottom of the sidebar. */
(function () {
  if (window.__notteStatus) {
    return;
  }
  window.__notteStatus = true;

  var PAGE_URL = "https://status.notte.cc";
  var JSON_URL = PAGE_URL + "/index.json";
  var ID = "notte-status";
  var CACHE_KEY = "notte-docs-status-core";
  var CACHE_MS = 60000;
  var REFRESH_MS = 120000;
  var STATES = {
    operational: ["ok", "All systems operational"],
    degraded: ["degraded", "Degraded performance"],
    downtime: ["incident", "Ongoing incident"],
    maintenance: ["maintenance", "Under maintenance"]
  };
  var UNKNOWN = ["unknown", "System status"];
  var current = UNKNOWN;

  function render() {
    var sidebar = document.getElementById("sidebar");
    if (!sidebar) {
      return;
    }
    var link = document.getElementById(ID);
    if (!link) {
      link = document.createElement("a");
      link.id = ID;
      link.className = "notte-status";
      link.href = PAGE_URL;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      sidebar.appendChild(link);
    }
    if (link.getAttribute("data-variant") !== current[0]) {
      link.setAttribute("data-variant", current[0]);
    }
    if (link.textContent !== current[1]) {
      link.textContent = current[1];
    }
  }

  // Worst state among the "Core APIs" section's monitored services; the page's overall
  // state only if that section is missing.
  var SECTION = "Core APIs";
  var SEVERITY = ["operational", "maintenance", "degraded", "downtime"];

  function coreState(data) {
    var included = (data && data.included) || [];
    var sectionId = null;
    for (var i = 0; i < included.length; i++) {
      var item = included[i];
      if (item.type === "status_page_section" && item.attributes && item.attributes.name === SECTION) {
        sectionId = String(item.id);
      }
    }
    if (sectionId === null) {
      return data && data.data && data.data.attributes && data.data.attributes.aggregate_state;
    }
    var worst = "operational";
    for (var j = 0; j < included.length; j++) {
      var resource = included[j];
      var attrs = resource.attributes || {};
      if (resource.type !== "status_page_resource" || String(attrs.status_page_section_id) !== sectionId) {
        continue;
      }
      if (SEVERITY.indexOf(attrs.status) > SEVERITY.indexOf(worst)) {
        worst = attrs.status;
      }
    }
    return worst;
  }

  function load() {
    try {
      var cached = JSON.parse(sessionStorage.getItem(CACHE_KEY) || "null");
      if (cached && Date.now() - cached.t < CACHE_MS) {
        current = cached.s;
        render();
        return;
      }
    } catch (err) {
      /* ignore */
    }
    fetch(JSON_URL, { cache: "no-store" })
      .then(function (response) {
        return response.json();
      })
      .then(function (data) {
        current = STATES[coreState(data)] || UNKNOWN;
        try {
          sessionStorage.setItem(CACHE_KEY, JSON.stringify({ t: Date.now(), s: current }));
        } catch (err) {
          /* ignore */
        }
        render();
      })
      .catch(function () {
        current = UNKNOWN;
        render();
      });
  }

  function watch() {
    if (!document.body) {
      requestAnimationFrame(watch);
      return;
    }
    render();
    load();
    setInterval(load, REFRESH_MS);
    new MutationObserver(function () {
      if (!document.getElementById(ID)) {
        render();
      }
    }).observe(document.body, { childList: true, subtree: true });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", watch);
  } else {
    watch();
  }
})();

/* Quickstart "Connect your agent" menu: every item copies the setup prompt (links still open
   their app), and the menu closes on an outside click or Escape. Same behavior as the console. */
(function () {
  if (window.__notteAgentMenu) {
    return;
  }
  window.__notteAgentMenu = true;

  function copy(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      return navigator.clipboard.writeText(text).catch(function () {});
    }
    return Promise.resolve();
  }

  function setOpen(menu, open) {
    menu.classList.toggle("is-open", open);
    var trigger = menu.querySelector(".nv-agent-menu__trigger");
    if (trigger) {
      trigger.setAttribute("aria-expanded", open ? "true" : "false");
    }
  }

  document.addEventListener("click", function (event) {
    var target = event.target;
    var trigger = target && target.closest ? target.closest(".nv-agent-menu__trigger") : null;
    if (trigger) {
      var menu = trigger.closest(".nv-agent-menu");
      setOpen(menu, !menu.classList.contains("is-open"));
      return;
    }
    var item = target && target.closest ? target.closest("[data-nv-copy-prompt]") : null;
    if (item) {
      void copy(item.getAttribute("data-nv-copy-prompt"));
      if (item.tagName !== "A") {
        event.preventDefault();
      }
      var label = item.querySelector(".nv-agent-menu__label");
      var copiedLabel = item.getAttribute("data-nv-copied-label");
      var original = label ? label.textContent : null;
      item.classList.add("is-copied");
      if (label && copiedLabel) {
        label.textContent = copiedLabel;
      }
      window.setTimeout(function () {
        item.classList.remove("is-copied");
        if (label && copiedLabel) {
          label.textContent = original;
        }
      }, 1600);
      return;
    }
    var open = document.querySelectorAll(".nv-agent-menu.is-open");
    for (var i = 0; i < open.length; i++) {
      if (!open[i].contains(target)) {
        setOpen(open[i], false);
      }
    }
  });

  document.addEventListener("keydown", function (event) {
    if (event.key !== "Escape") {
      return;
    }
    var open = document.querySelectorAll(".nv-agent-menu.is-open");
    for (var i = 0; i < open.length; i++) {
      setOpen(open[i], false);
      var trigger = open[i].querySelector(".nv-agent-menu__trigger");
      if (trigger) {
        trigger.focus();
      }
    }
  });
})();
