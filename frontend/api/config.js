module.exports = (req, res) => {
  const apiUrl = process.env.API_URL || "";
  res.setHeader("Content-Type", "application/javascript; charset=utf-8");
  res.setHeader("Cache-Control", "no-store");
  res.status(200).send(`window.MILK_LEDGER_CONFIG = ${JSON.stringify({ API_URL: apiUrl })};`);
};
