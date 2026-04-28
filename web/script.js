async function loadBoard() {
  const res = await fetch("./board-data.json?v=" + Date.now());
  const data = await res.json();

  const sports = data.sports || {};
  const mlb = sports.mlb || {};
  const nba = sports.nba || {};

  document.getElementById("subtitle").textContent =
    `${data.updatedAt || "Today"} · ${data.sourceMode || "Live board"}`;

  document.getElementById("side").innerHTML = `
    ${renderPickOfDay(mlb, "MLB Pick of the Day")}
    ${renderHrTop10(mlb)}
  `;

  document.getElementById("main").innerHTML = `
    ${renderSportSection("MLB Board", mlb)}
    ${renderSportSection("NBA Board", nba)}
  `;
}

function safe(v, fallback = "--") {
  return v === undefined || v === null || v === "" ? fallback : v;
}

function renderPickOfDay(sport, title) {
  const pick = sport.pickOfDay;

  if (!pick) {
    return `
      <section class="card">
        <h2>${title}</h2>
        <div class="empty">No pick available yet.</div>
      </section>
    `;
  }

  return `
    <section class="card">
      <h2>${title}</h2>
      <div class="muted">${safe(pick.team)}</div>
      <div class="pick-name">${safe(pick.player)}</div>
      <div>
        <span class="pill">${safe(pick.market)}</span>
        <span class="pill">${safe(pick.line)}</span>
        <span class="pill">${safe(pick.score)}</span>
      </div>
      <p class="muted">${safe(pick.rate)}</p>
    </section>
  `;
}

function renderHrTop10(sport) {
  const rows = sport.daily_hr_top_10 || [];

  if (!rows.length) {
    return `
      <section class="card">
        <h2>Daily HR Top 10</h2>
        <div class="empty">HR board updates as player data confirms.</div>
      </section>
    `;
  }

  return `
    <section class="card">
      <h2>Daily HR Top 10</h2>
      ${rows.slice(0, 10).map((p, i) => `
        <div class="hr-row">
          <div class="hr-rank">#${i + 1}</div>
          <div class="hr-player">
            <strong>${safe(p.player || p.name, "Unknown")} — ${safe(p.team, "")}</strong>
            <span>L10 ${safe(p.last10)} | L5 ${safe(p.last5)} | L3 ${safe(p.last3)}</span>
          </div>
        </div>
      `).join("")}
    </section>
  `;
}

function renderSportSection(title, sport) {
  const games = sport.games || [];

  return `
    <section class="card">
      <h2>${title}</h2>
      <div class="muted">${safe(sport.note, "Live board")}</div>
    </section>

    <div class="games">
      ${games.length ? games.map(renderGameCard).join("") : `
        <div class="card empty">No games available yet.</div>
      `}
    </div>
  `;
}

function renderGameCard(game) {
  const picks = game.topPicks || [];

  return `
    <article class="game">
      <div class="game-head">
        <div>
          <div class="game-title">${safe(game.title)}</div>
          <div class="game-meta">${safe(game.start)} · ${safe(game.meta)}</div>
        </div>
        <span class="pill">${safe(game.status)}</span>
      </div>

      <div class="muted">${safe(game.attackNote)}</div>

      <div class="top-picks">
        ${picks.length ? picks.map(renderTopPick).join("") : `
          <div class="empty">No plays yet. Signals update as lineups confirm.</div>
        `}
      </div>
    </article>
  `;
}

function renderTopPick(pick) {
  return `
    <div class="play">
      <div>
        <strong>${safe(pick.name)}</strong>
        <span>${safe(pick.market)} · ${safe(pick.line)} · ${safe(pick.why)}</span>
      </div>
      <span class="pill">${safe(pick.tier)}</span>
    </div>
  `;
}

loadBoard().catch((err) => {
  console.error(err);
  document.getElementById("main").innerHTML = `
    <div class="card">
      <h2>Board failed to load</h2>
      <div class="muted">${err.message}</div>
    </div>
  `;
});
