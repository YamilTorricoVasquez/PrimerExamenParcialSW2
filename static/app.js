document.addEventListener("DOMContentLoaded", () => {
    // -----------------------------------------------------------------
    // Sugerencia de nombres desde el marcador (OCR experimental)
    // -----------------------------------------------------------------
    const scoreboardBtn = document.getElementById("scoreboard-btn");
    const videoInput = document.getElementById("video-input");
    const statusEl = document.getElementById("scoreboard-status");
    const suggestionsEl = document.getElementById("scoreboard-suggestions");
    const teamAInput = document.getElementById("team_a_name");
    const teamBInput = document.getElementById("team_b_name");

    if (scoreboardBtn) {
        scoreboardBtn.addEventListener("click", async () => {
            if (!videoInput.files || videoInput.files.length === 0) {
                statusEl.textContent = "Primero selecciona un video arriba.";
                return;
            }
            statusEl.textContent = "Analizando el marcador... esto puede tardar un momento.";
            suggestionsEl.innerHTML = "";
            scoreboardBtn.disabled = true;

            const formData = new FormData();
            formData.append("video", videoInput.files[0]);

            try {
                const response = await fetch("/api/scoreboard_suggest", { method: "POST", body: formData });
                const data = await response.json();

                if (data.suggestions && data.suggestions.length > 0) {
                    statusEl.textContent = "Texto encontrado (puede incluir ruido, revisa antes de usarlo):";
                    data.suggestions.forEach((text, i) => {
                        const chip = document.createElement("span");
                        chip.className = "chip";
                        chip.textContent = text;
                        chip.addEventListener("click", () => {
                            if (i % 2 === 0) teamAInput.value = text;
                            else teamBInput.value = text;
                        });
                        suggestionsEl.appendChild(chip);
                    });
                } else {
                    statusEl.textContent = "No se pudo leer ningún nombre del marcador. Usa los campos manuales.";
                }
            } catch (err) {
                statusEl.textContent = "No se pudo analizar el marcador (error de conexión). Usa los campos manuales.";
            } finally {
                scoreboardBtn.disabled = false;
            }
        });
    }

    // -----------------------------------------------------------------
    // Plantilla dinámica de jugadores (número + nombre)
    // -----------------------------------------------------------------
    const rosterRowsEl = document.getElementById("roster-rows");
    const addRosterBtn = document.getElementById("add-roster-row");
    const rosterJsonInput = document.getElementById("roster_json");
    const form = document.getElementById("analyze-form");

    function addRosterRow(number = "", name = "") {
        const row = document.createElement("div");
        row.className = "roster-row";
        row.innerHTML = `
            <input type="text" placeholder="N°" class="roster-number" value="${number}">
            <input type="text" placeholder="Nombre del jugador" class="roster-name" value="${name}">
            <button type="button" title="Quitar">✕</button>
        `;
        row.querySelector("button").addEventListener("click", () => row.remove());
        rosterRowsEl.appendChild(row);
    }

    if (addRosterBtn) {
        addRosterBtn.addEventListener("click", () => addRosterRow());
        // Arranca con 3 filas vacías para no obligar a hacer clic antes de escribir
        addRosterRow();
        addRosterRow();
        addRosterRow();
    }

    if (form) {
        form.addEventListener("submit", () => {
            const roster = [];
            document.querySelectorAll(".roster-row").forEach(row => {
                const number = row.querySelector(".roster-number").value.trim();
                const name = row.querySelector(".roster-name").value.trim();
                if (number && name) roster.push({ number, name });
            });
            rosterJsonInput.value = JSON.stringify(roster);
        });
    }
});
