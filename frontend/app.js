(function () {
  const config = window.MILK_LEDGER_CONFIG || {};
  const apiUrl = (config.API_URL || "").replace(/\/+$/, "");
  const backendUrlText = document.getElementById("backendUrlText");
  const dashboardLink = document.getElementById("openDashboard");
  const healthLink = document.getElementById("openHealth");
  const healthBadge = document.getElementById("healthBadge");
  const healthText = document.getElementById("healthText");

  function setHealth(ok, message) {
    const dot = healthBadge.querySelector(".dot");
    dot.classList.remove("ok", "bad");
    dot.classList.add(ok ? "ok" : "bad");
    healthText.textContent = message;
  }

  if (!apiUrl) {
    backendUrlText.textContent = "API_URL is not configured on Vercel.";
    dashboardLink.removeAttribute("href");
    healthLink.removeAttribute("href");
    setHealth(false, "Missing API_URL");
    return;
  }

  backendUrlText.textContent = apiUrl;
  dashboardLink.href = apiUrl + "/login";
  healthLink.href = apiUrl + "/health/live";

  fetch(apiUrl + "/health/live")
    .then(function (response) {
      if (!response.ok) {
        throw new Error("HTTP " + response.status);
      }
      return response.json();
    })
    .then(function (payload) {
      setHealth(Boolean(payload.ok), payload.ok ? "Backend healthy" : "Backend reports degraded health");
    })
    .catch(function (error) {
      setHealth(false, "Health check failed");
      console.error("Backend health check failed", error);
    });
})();
