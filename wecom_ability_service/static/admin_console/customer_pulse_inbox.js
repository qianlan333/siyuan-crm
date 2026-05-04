(function () {
  "use strict";

  document.addEventListener("DOMContentLoaded", () => {
    const CustomerPulseInbox = window.CustomerPulseInbox || {};
    if (typeof CustomerPulseInbox.boot === "function") {
      CustomerPulseInbox.boot();
    }
  });
})();
