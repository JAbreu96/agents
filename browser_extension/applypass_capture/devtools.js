// The only job of the devtools page is to register the panel. Everything else
// lives in panel.js, which Chrome does not load until the panel is first shown.
chrome.devtools.panels.create(
  "ApplyPass Capture",
  null,
  "panel.html",
  () => {}
);
