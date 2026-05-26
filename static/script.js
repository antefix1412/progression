const form = document.querySelector("#search-form");
const statusEl = document.querySelector("#status");
const loaderEl = document.querySelector("#loader");
const elapsedEl = document.querySelector("#elapsed");
const tbody = document.querySelector("#players");
const submit = document.querySelector("#submit");
const copyButton = document.querySelector("#copy");

let allPlayers = [];
let visiblePlayers = [];
let loading = false;
let startedAt = 0;
let timerId = null;
const BATCH_SIZE = 8;

function formatNumber(value) {
  return Math.round(Number(value)).toLocaleString("fr-FR");
}

function formatProgression(value) {
  const formatted = formatNumber(value);
  return value >= 0 ? `+${formatted}` : formatted;
}

function setStatus(message) {
  statusEl.textContent = message;
}


function setLoader(isVisible) {
  loaderEl.hidden = !isVisible;
  if (!isVisible) {
    clearInterval(timerId);
    timerId = null;
    elapsedEl.textContent = "0 s";
    return;
  }

  startedAt = Date.now();
  elapsedEl.textContent = "0 s";
  timerId = setInterval(() => {
    const seconds = Math.floor((Date.now() - startedAt) / 1000);
    elapsedEl.textContent = `${seconds} s`;
  }, 1000);
}

function renderPlayers(players) {
  visiblePlayers = [...players].sort((a, b) => b.progression - a.progression);
  copyButton.disabled = loading || visiblePlayers.length === 0;
  copyButton.classList.toggle("ready", visiblePlayers.length > 0);

  if (!visiblePlayers.length) {
    const emptyText = loading ? "Recherche en cours..." : "Aucune donnée à afficher";
    tbody.innerHTML = `<tr><td class="empty" colspan="5">${emptyText}</td></tr>`;
    return;
  }

  tbody.innerHTML = visiblePlayers.map((player) => {
    const progressionClass = player.progression >= 0 ? "positive" : "negative";
    return `
      <tr>
        <td>${player.prenom}</td>
        <td>${player.nom}</td>
        <td class="num">${formatNumber(player.points_officiels)}</td>
        <td class="num">${formatNumber(player.points_calcules)}</td>
        <td class="num"><span class="progress-pill ${progressionClass}">${formatProgression(player.progression)}</span></td>
      </tr>
    `;
  }).join("");
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const params = new URLSearchParams(new FormData(form));

  loading = true;
  submit.disabled = true;
  submit.innerHTML = '<span aria-hidden="true">🔄</span> Recherche...';
  copyButton.disabled = true;
  copyButton.classList.remove("ready");
  setLoader(true);
  setStatus("Rafraîchissement en cours...");
  allPlayers = [];
  renderPlayers([]);

  try {
    let offset = 0;
    let total = null;
    const refreshedPlayers = [];

    while (total === null || offset < total) {
      params.set("offset", String(offset));
      params.set("batch_size", String(BATCH_SIZE));

      const response = await fetch(`/api/refresh?${params.toString()}`);
      const payload = await readJsonResponse(response);
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${JSON.stringify(payload)}`);
      }

      total = payload.total;
      offset = payload.next_offset;
      refreshedPlayers.push(...payload.players);
      allPlayers = refreshedPlayers;
      renderPlayers(allPlayers);
      setStatus(`Rafraîchissement en cours... ${Math.min(offset, total)} / ${total} joueurs analysés`);

      if (payload.done) {
        break;
      }
    }

    allPlayers = refreshedPlayers;
    renderPlayers(allPlayers);

    setStatus("");
  } catch (error) {
    setStatus(`Erreur de connexion: ${error.message}`);
  } finally {
    loading = false;
    setLoader(false);
    submit.disabled = false;
    submit.innerHTML = '<span aria-hidden="true">🔄</span> Rafraîchir maintenant';
    copyButton.disabled = visiblePlayers.length === 0;
  }
});

async function readJsonResponse(response) {
  const text = await response.text();
  try {
    return JSON.parse(text);
  } catch {
    throw new Error(`Réponse serveur non JSON (${response.status}): ${text.slice(0, 180)}`);
  }
}

copyButton.addEventListener("click", async () => {
  if (!visiblePlayers.length) {
    return;
  }

  const rows = [
    ["PRENOM", "NOM", "POINTS OFFICIELS", "POINTS CALCULES FFTT", "PROGRESSION"],
    ...visiblePlayers.map((player) => [
      player.prenom,
      player.nom,
      formatNumber(player.points_officiels),
      formatNumber(player.points_calcules),
      formatProgression(player.progression),
    ]),
  ];
  const text = rows.map((row) => row.join("\t")).join("\n");

  try {
    await navigator.clipboard.writeText(text);
    setStatus("Tableau copié");
  } catch {
    setStatus("Impossible de copier automatiquement le tableau.");
  }
});
