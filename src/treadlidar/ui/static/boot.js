"use strict";
(async function () {
  const { State, api, render } = App;
  App.applyTheme();
  try {
    State.info = await api("GET", "/api/info");
    await App.refreshScans();
  } catch (e) {
    document.getElementById("view").append(App.h("div", { class: "empty" }, App.h("h3", null, "Cannot reach the local service"), App.h("p", null, e.message)));
    return;
  }
  // honour a deep link such as ?view=tread (used by tests and bookmarks)
  const q = new URLSearchParams(location.search);
  if (q.get("view")) State.view = q.get("view");
  App.render();
  window.__ready = true;
})();
