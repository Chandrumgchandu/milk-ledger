(function () {
  const config = window.MILK_LEDGER_CONFIG || {};
  const apiUrl = (config.API_URL || "").replace(/\/+$/, "");
  const backendUrlText = document.getElementById("backendUrlText");
  const dashboardLink = document.getElementById("openDashboard");
  const healthLink = document.getElementById("openHealth");
  const healthBadge = document.getElementById("healthBadge");
  const healthText = document.getElementById("healthText");
  const healthDetail = document.getElementById("healthDetail");

  function setHealth(state, message, detail) {
    const dot = healthBadge.querySelector(".dot");
    dot.classList.remove("ok", "bad", "warn");
    dot.classList.add(state);
    healthText.textContent = message;
    if (healthDetail && detail) {
      healthDetail.textContent = detail;
    }
  }

  if (!apiUrl) {
    backendUrlText.textContent = "API_URL is not configured on Vercel.";
    dashboardLink.removeAttribute("href");
    healthLink.removeAttribute("href");
    setHealth("bad", "Missing API_URL", "Set API_URL in Vercel to point at the Render backend.");
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
      if (payload.ok) {
        setHealth("ok", "Backend healthy", "The Render backend responded successfully.");
      } else {
        setHealth("warn", "Backend degraded", "The backend responded, but one or more dependency checks reported degraded health.");
      }
    })
    .catch(function (error) {
      setHealth("warn", "Backend unavailable", "The demo frontend is live. The backend may be sleeping, blocked, or awaiting Render/Supabase environment verification.");
      console.error("Backend health check failed", error);
    });
})();
