const el = {
    entriesBody: document.getElementById("entriesBody"),
    refreshBtn: document.getElementById("refreshBtn"),
    updatedLabel: document.getElementById("updatedLabel"),
    logBlock: document.getElementById("logBlock"),
    clearBtn: document.getElementById("clearBtn"),
    hideBtn: document.getElementById("hideBtn"),
    versionLabel: document.getElementById("versionLabel"),
    architectureLabel: document.getElementById("architectureLabel"),
    findBtn: document.getElementById("findBtn"),
    findOverlay: document.getElementById("findOverlay"),
    findCloseBtn: document.getElementById("findCloseBtn"),
    findCancelBtn: document.getElementById("findCancelBtn"),
    findSubmitBtn: document.getElementById("findSubmitBtn"),
    findInput: document.getElementById("findInput"),
    findResult: document.getElementById("findResult")
};

const ENTRIES_INTERVAL = 5000;
const LOGS_INTERVAL = 4000;
const SCROLL_EDGE_TOLERANCE = 40; // px from the bottom that still counts as "at the end"

const api = {
    async get(path) {
        const res = await fetch(`./api/${path}`);
        if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
        return res.json();
    },
    entries() {
        return this.get("devices");
    },
    versionInfo() {
        return this.get("info");
    },
    logs() {
        return this.get("logs");
    },
    findMac(query) {
        return this.get(`find?query=${encodeURIComponent(query)}`);
    }
};

function escapeHtml(value) {
    return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}

function field(value) {
    return value ? escapeHtml(value) : '<span class="unset">-</span>';
}

function renderEntries(entries) {
    el.entriesBody.innerHTML = entries.map(entry => {
        const known = entry.status === "known";

        return `
            <tr>
                <td class="status-cell" data-label="Status">
                    <span class="status ${known ? "known" : "unknown"}">
                        <span class="dot"></span>
                        <span class="label">${known ? "Known" : "Unknown"}</span>
                    </span>
                </td>
                <td data-label="Friendly name">${field(entry.friendly_name)}</td>
                <td data-label="MAC address">${field(entry.mac)}</td>
                <td data-label="Virtual IP">${field(entry.virtual_ip)}</td>
                <td data-label="Virtual hostname">${field(entry.virtual_hostname)}</td>
                <td data-label="Hostname">${field(entry.hostname)}</td>
                <td data-label="IP">${field(entry.ip)}</td>
                <td class="time-cell" data-label="Last updated">${field(entry.last_updated)}</td>
                <td class="time-cell" data-label="Last confirmed">${field(entry.last_confirmed)}</td>
            </tr>
        `;
    }).join("");
}

function stampUpdatedTime() {
    el.updatedLabel.textContent = `Updated ${new Date().toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        hour12: false,
    })}`;
}

async function loadEntries() {
    el.refreshBtn.classList.add("spinning");

    try {
        renderEntries(await api.entries());
        stampUpdatedTime();
    } catch (err) {
        console.error("could not load entries:", err);
    } finally {
        // Finish the current spin before stopping.
        await new Promise(resolve => {
            el.refreshBtn.addEventListener("animationiteration", resolve, {
                once: true,
            });
        });

        el.refreshBtn.classList.remove("spinning");
    }
}

async function loadVersionInfo() {
    try {
        const info = await api.versionInfo();
        el.versionLabel.textContent = `v${info.version}`;
        if (el.architectureLabel) el.architectureLabel.textContent = info.architecture;
    } catch (err) {
        console.error("could not load version info:", err);
    }
}

function isScrolledToEnd() {
    const { scrollHeight, scrollTop, clientHeight } = el.logBlock;
    return scrollHeight - scrollTop - clientHeight <= SCROLL_EDGE_TOLERANCE;
}

function appendLog(line) {
    const stickToEnd = isScrolledToEnd();

    const row = document.createElement("div");
    row.className = "log-line";
    row.textContent = line;
    el.logBlock.append(row);

    if (stickToEnd) el.logBlock.scrollTop = el.logBlock.scrollHeight;
}

function pollLogs() {
    let seen = [];

    const check = async () => {
        try {
            const lines = await api.logs();

            // only append the new part of the response
            let overlap = Math.min(seen.length, lines.length);
            while (overlap > 0 && !seen.slice(-overlap).every((line, i) => line === lines[i])) {
                overlap--;
            }

            lines.slice(overlap).forEach(appendLog);
            seen = lines;
        } catch (err) {
            console.error("could not load logs:", err);
        }
    };

    check();
    setInterval(check, LOGS_INTERVAL);
}

function openFindDialog() {
    el.findOverlay.classList.remove("hidden");
    el.findResult.textContent = "";
    el.findResult.className = "modal-result";
    el.findInput.value = "";
    el.findInput.focus();
}

function closeFindDialog() {
    el.findOverlay.classList.add("hidden");
}

async function submitFind() {
    const query = el.findInput.value.trim();
    if (!query) return;

    el.findSubmitBtn.disabled = true;
    el.findResult.className = "modal-result";
    el.findResult.textContent = "Looking...";

    try {
        const data = await api.findMac(query);

        if (data.mac) {
            el.findResult.textContent = data.mac;
            el.findResult.classList.add("found");
        } else {
            el.findResult.classList.add("not-found");
            el.findResult.textContent = data.message;
        }
    } catch (err) {
        el.findResult.textContent = "Lookup failed, try again.";
        el.findResult.classList.add("not-found");
    } finally {
        el.findSubmitBtn.disabled = false;
    }
}

el.refreshBtn.addEventListener("click", loadEntries);

el.clearBtn.addEventListener("click", () => {
    el.logBlock.replaceChildren();
});

el.hideBtn.addEventListener("click", () => {
    const hidden = el.logBlock.classList.toggle("hidden");
    el.hideBtn.textContent = hidden ? "Show" : "Hide";
});

el.findBtn.addEventListener("click", openFindDialog);
el.findCloseBtn.addEventListener("click", closeFindDialog);
el.findCancelBtn.addEventListener("click", closeFindDialog);
el.findSubmitBtn.addEventListener("click", submitFind);

el.findOverlay.addEventListener("click", event => {
    if (event.target === el.findOverlay) closeFindDialog();
});

el.findInput.addEventListener("keydown", event => {
    if (event.key === "Enter") submitFind();
});

document.addEventListener("keydown", event => {
    if (event.key === "Escape" && !el.findOverlay.classList.contains("hidden")) closeFindDialog();
});

loadEntries();
loadVersionInfo();
pollLogs();
setInterval(loadEntries, ENTRIES_INTERVAL);