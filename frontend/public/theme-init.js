// Sets the theme before the page paints. External (not inline) so the strict Content-Security-Policy
// used by every SLAI application ("script-src 'self'") allows it.
(function () {
  try {
    var stored = localStorage.getItem("slaifi-theme");
    var preferred = matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
    document.documentElement.dataset.theme = stored === "light" || stored === "dark" ? stored : preferred;
  } catch (e) {
    document.documentElement.dataset.theme = "dark";
  }
})();
