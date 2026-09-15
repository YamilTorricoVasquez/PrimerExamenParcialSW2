let currentData = null;

function showError(message) {
    document.getElementById("processing-box").style.display = "none";
    const errorBox = document.getElementById("error-box");
    errorBox.style.display = "block";
    errorBox.textContent = message;
}

function pollStatus() {
    fetch(`/api/status/${JOB_ID}`)
        .then(r => r.json())
        .then(data => {
            if (data.status === "not_found") {
                showError("No se encontró este análisis. Puede que el servidor se haya reiniciado.");
                return;
            }
            if (data.status === "error") {
                showError("Ocurrió un error durante el análisis: " + (data.error || "desconocido"));
                return;
            }
            if (data.status === "done") {
                document.getElementById("processing-box").style.display = "none";
                loadResults();
                return;
            }
            const pct = data.progress || 0;
            document.getElementById("progress-bar-inner").style.width = pct + "%";
            document.getElementById("progress-text").textContent = `Procesando... ${pct}%`;
            setTimeout(pollStatus, 1500);
        })
        .catch(() => setTimeout(pollStatus, 2000));
}

function activityBadgeClass(level) {
    if (level === "Alto") return "badge-alto";
    if (level === "Medio") return "badge-medio";
    return "badge-bajo";
}

function playerDisplayName(player) {
    return player.name ? player.name : `Jugador #${player.track_id}`;
}

function renderScoreboard(teams) {
    const el = document.getElementById("scoreboard-header");
    if (teams.length < 2) {
        el.innerHTML = teams.map(t => `<span class="team-name" style="color:${t.color_hex}">${t.name}</span>`).join("");
        return;
    }
    el.innerHTML = `
        <span class="team-name" style="color:${teams[0].color_hex}">${teams[0].name}</span>
        <span class="vs">VS</span>
        <span class="team-name" style="color:${teams[1].color_hex}">${teams[1].name}</span>
    `;
}

function renderTeams(teams) {
    const container = document.getElementById("team-swatches");
    container.innerHTML = "";
    teams.forEach(team => {
        const div = document.createElement("div");
        div.className = "team-swatch";
        div.innerHTML = `
            <div class="color-box" style="background:${team.color_hex}"></div>
            <div class="team-label">${team.name}</div>
        `;
        container.appendChild(div);
    });

    const heatmapContainer = document.getElementById("team-heatmaps");
    heatmapContainer.innerHTML = "";
    teams.forEach(team => {
        const block = document.createElement("div");
        block.className = "heatmap-block";
        block.innerHTML = `
            <h3>${team.name}</h3>
            <img src="/image/team_heatmap/${JOB_ID}/${team.cluster_id}.png?t=${Date.now()}" alt="Mapa de calor ${team.name}">
        `;
        heatmapContainer.appendChild(block);
    });
}

function renderComparison(teamComparison) {
    const container = document.getElementById("team-compare");
    if (!teamComparison || teamComparison.length < 2) {
        container.innerHTML = "<p class=\"hint\">No hay suficientes datos de ambos equipos para comparar.</p>";
        return;
    }
    const [a, b] = teamComparison;

    function bar(label, valueA, valueB, unit) {
        const maxVal = Math.max(valueA, valueB, 1);
        const pctA = (valueA / maxVal) * 100;
        const pctB = (valueB / maxVal) * 100;
        return `
            <div class="compare-metric">
                <div class="compare-label">${label}</div>
                <div class="compare-bars">
                    <span class="bar-value" style="color:${a.color_hex}">${valueA}${unit}</span>
                    <div class="bar-track right"><div class="bar-fill" style="width:${pctA}%;background:${a.color_hex}"></div></div>
                    <div class="bar-track"><div class="bar-fill" style="width:${pctB}%;background:${b.color_hex}"></div></div>
                    <span class="bar-value" style="color:${b.color_hex}">${valueB}${unit}</span>
                </div>
            </div>
        `;
    }

    container.innerHTML = `
        <div class="scoreboard" style="margin-bottom:18px;">
            <span class="team-name" style="color:${a.color_hex}">${a.name}</span>
            <span class="vs">VS</span>
            <span class="team-name" style="color:${b.color_hex}">${b.name}</span>
        </div>
        ${bar("Distancia total del equipo", a.total_distance_m, b.total_distance_m, " m")}
        ${bar("Distancia promedio por jugador", a.avg_distance_m, b.avg_distance_m, " m")}
        ${bar("Jugadores con actividad Alta", a.activity_counts.Alto, b.activity_counts.Alto, "")}
        ${bar("Jugadores con actividad Baja", a.activity_counts.Bajo, b.activity_counts.Bajo, "")}
    `;
}

function renderPlayerSelect(players) {
    const select = document.getElementById("player-select");
    select.innerHTML = "";
    players.forEach(p => {
        const opt = document.createElement("option");
        opt.value = p.track_id;
        opt.textContent = `${playerDisplayName(p)} — ${p.team_name} (${p.distance_m} m)`;
        select.appendChild(opt);
    });
    if (players.length > 0) renderPlayerDetail(players[0]);
    select.addEventListener("change", () => {
        const player = currentData.players.find(p => p.track_id == select.value);
        if (player) renderPlayerDetail(player);
    });
}

function renderPlayerDetail(player) {
    const container = document.getElementById("player-detail");
    const fatigueHtml = player.fatigue_alert
        ? `<div class="fatigue-warning">Este jugador mostró una baja notable de actividad en la segunda mitad del video respecto a la primera.</div>`
        : "";
    const badgeLabel = player.jersey_guess || player.track_id;

    container.innerHTML = `
        <div class="player-header">
            <div class="jersey-badge" style="background:${player.team_color}">${badgeLabel}</div>
            <div class="names">
                <h3>${playerDisplayName(player)}</h3>
                <div class="subtitle">${player.team_name}</div>
                <span class="zone-chip">${player.zone}</span>
            </div>
        </div>
        <span class="badge ${activityBadgeClass(player.activity_level)}">Nivel de actividad: ${player.activity_level}</span>
        <div class="metrics-row">
            <div class="metric-box"><div class="value">${player.distance_m} m</div><div class="label">Distancia recorrida</div></div>
            <div class="metric-box"><div class="value">${player.avg_speed_kmh} km/h</div><div class="label">Velocidad promedio</div></div>
            <div class="metric-box"><div class="value">${player.max_speed_kmh} km/h</div><div class="label">Velocidad máxima</div></div>
        </div>
        ${fatigueHtml}
        <div class="heatmap-block">
            <img src="/image/player_heatmap/${JOB_ID}/${player.track_id}.png?t=${Date.now()}" alt="Mapa de calor jugador ${player.track_id}">
        </div>
        <a class="btn-secondary" href="/download/pdf/${JOB_ID}/${player.track_id}">Descargar ficha del jugador (PDF)</a>
    `;
}

function renderNameAssignment(players, rosterNames) {
    const datalist = document.getElementById("roster-datalist");
    datalist.innerHTML = rosterNames.map(n => `<option value="${n}">`).join("");

    const container = document.getElementById("name-assign-rows");
    container.innerHTML = players.map(p => `
        <div class="name-assign-row" data-track-id="${p.track_id}">
            <div class="tid-chip" style="border-left:3px solid ${p.team_color}">#${p.track_id}${p.jersey_guess ? " (dorsal " + p.jersey_guess + "?)" : ""}</div>
            <div class="hint" style="align-self:center;">${p.team_name}</div>
            <input type="text" class="name-input" list="roster-datalist" placeholder="Nombre del jugador" value="${p.name || ""}">
        </div>
    `).join("");
}

function saveNames() {
    const names = {};
    document.querySelectorAll("#name-assign-rows .name-assign-row").forEach(row => {
        const trackId = row.dataset.trackId;
        const value = row.querySelector(".name-input").value.trim();
        names[trackId] = value;
    });

    const statusEl = document.getElementById("save-names-status");
    statusEl.textContent = "Guardando...";

    fetch(`/api/player_names/${JOB_ID}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ names }),
    })
        .then(r => r.json())
        .then(() => {
            statusEl.textContent = "Nombres guardados.";
            loadResults();
        })
        .catch(() => { statusEl.textContent = "No se pudieron guardar los nombres."; });
}

function loadResults() {
    fetch(`/api/data/${JOB_ID}`)
        .then(r => r.json())
        .then(data => {
            currentData = data;
            document.getElementById("results-box").style.display = "block";
            document.getElementById("summary-text").textContent = data.summary_text;
            renderScoreboard(data.teams);
            renderTeams(data.teams);
            renderComparison(data.team_comparison);
            renderPlayerSelect(data.players);
            renderNameAssignment(data.players, data.roster_names || []);
            document.getElementById("download-csv").href = `/download/csv/${JOB_ID}`;
        })
        .catch(() => showError("No se pudieron cargar los resultados."));
}

document.getElementById("swap-btn").addEventListener("click", () => {
    fetch(`/api/swap/${JOB_ID}`, { method: "POST" }).then(r => r.json()).then(() => loadResults());
});

document.getElementById("save-names-btn").addEventListener("click", saveNames);

document.querySelectorAll(".tab-btn").forEach(btn => {
    btn.addEventListener("click", () => {
        document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
        document.querySelectorAll(".tab-content").forEach(c => c.classList.remove("active"));
        btn.classList.add("active");
        document.getElementById(btn.dataset.tab).classList.add("active");
    });
});

pollStatus();
