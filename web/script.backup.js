function renderHrTop10(sport) {
  const rows = sport.daily_hr_top_10;
  if (!rows || !rows.length) return "";

  return `
    <section class="hr-leaderboard">
      <h2>Daily HR Top 10</h2>
      ${rows.slice(0, 10).map((p, i) => `
        <div class="hr-row">
          <div class="rank">#${i + 1}</div>
          <div class="info">
            <strong>${p.player || "Unknown"} — ${p.team || ""}</strong>
            <div class="form">
              L10 ${p.last10 || "--"} | L5 ${p.last5 || "--"} | L3 ${p.last3 || "--"}
            </div>
          </div>
        </div>
      `).join("")}
    </section>
  `;
}
