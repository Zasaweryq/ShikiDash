const DATA_URL = "./data/latest.json";

let charts = [];

function destroyCharts() {
  charts.forEach(c => c?.destroy?.());
  charts = [];
}

function card(k, v) {
  const el = document.createElement("div");
  el.className = "card";
  el.innerHTML = `<div class="k">${k}</div><div class="v">${v}</div>`;
  return el;
}

function fmtHours(minutes) {
  if (!Number.isFinite(minutes)) return "—";
  const h = minutes / 60;
  return h >= 100 ? `${Math.round(h)} ч` : `${h.toFixed(1)} ч`;
}

async function loadData() {
  // no-store чтобы не ловить старый JSON из кеша Pages
  const res = await fetch(`${DATA_URL}?v=${Date.now()}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Не могу загрузить ${DATA_URL}: ${res.status}`);
  return res.json();
}

function buildCards(d) {
  const c = document.getElementById("cards");
  c.innerHTML = "";

  const s = d.stats;
  c.append(
    card("Пользователь", d.user.nickname),
    card("Всего тайтлов", s.total_titles),
    card("Completed", s.by_status.completed ?? 0),
    card("Watching", s.by_status.watching ?? 0),
    card("Planned", s.by_status.planned ?? 0),
    card("Dropped", s.by_status.dropped ?? 0),
    card("Средняя оценка (completed)", s.avg_score_completed ?? "—"),
    card("Эпизоды (сумма userRate.episodes)", s.total_episodes ?? "—"),
    card("Время (оценка)", fmtHours(s.total_minutes_estimated)),
    card("Обновлено", new Date(d.generated_at).toLocaleString("ru-RU"))
  );
}

function makeChart(ctxId, type, labels, values) {
  const ctx = document.getElementById(ctxId);
  const chart = new Chart(ctx, {
    type,
    data: {
      labels,
      datasets: [{ label: "", data: values }]
    },
    options: {
      responsive: true,
      plugins: { legend: { display: type !== "bar" } },
      scales: type === "bar" ? { y: { beginAtZero: true } } : {}
    }
  });
  charts.push(chart);
}

function fillTopTable(d) {
  const tb = document.querySelector("#topTable tbody");
  tb.innerHTML = "";
  d.top_completed.forEach((x, i) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${i + 1}</td>
      <td><a href="https://shikimori.one${x.url}" target="_blank" rel="noreferrer">${x.russian || x.name}</a></td>
      <td>${x.score}</td>
      <td>${(x.genres || []).join(", ")}</td>
      <td>${(x.studios || []).join(", ")}</td>
      <td>${x.year ?? "—"}</td>
    `;
    tb.appendChild(tr);
  });
}

async function render() {
  const d = await loadData();

  document.getElementById("subtitle").textContent =
    `@${d.user.nickname} • всего: ${d.stats.total_titles} • updated: ${new Date(d.generated_at).toLocaleString("ru-RU")}`;

  destroyCharts();
  buildCards(d);

  makeChart("chartStatuses", "doughnut",
    Object.keys(d.charts.statuses),
    Object.values(d.charts.statuses)
  );

  makeChart("chartScores", "bar",
    d.charts.scores.labels,
    d.charts.scores.values
  );

  makeChart("chartGenres", "bar",
    d.charts.top_genres.labels,
    d.charts.top_genres.values
  );

  makeChart("chartStudios", "bar",
    d.charts.top_studios.labels,
    d.charts.top_studios.values
  );

  makeChart("chartByYear", "bar",
    d.charts.completed_by_year.labels,
    d.charts.completed_by_year.values
  );

  fillTopTable(d);
}

document.getElementById("refreshBtn").addEventListener("click", async () => {
  // этот “refresh” просто перечитывает JSON; реальные обновления делает Action
  try { await render(); } catch (e) { alert(String(e)); }
});

render().catch(e => {
  console.error(e);
  document.getElementById("subtitle").textContent = `Ошибка: ${e.message}`;
});
