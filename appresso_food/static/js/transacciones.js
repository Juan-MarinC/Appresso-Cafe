(function () {
    const { $, esc, money, time, api, windowSvg, chip } = window.Fraud;
    const CFG = JSON.parse($("cfg").textContent);
    const FIELDS = { idTxn: "f-id", user: "f-user", nombre: "f-nombre", cedula: "f-cedula", date: "f-date", value: "f-value", paymentMethod: "f-method", hash: "f-hash" };
    let counter = 0;
    let lastAcceptedId = null;

    // ---------- utilidades ----------
    const pad = (n, l = 2) => String(n).padStart(l, "0");

    /** Hora local con desfase, p. ej. 2026-09-23T10:30:01.120-05:00 (el backend la normaliza). */
    function nowIso() {
        const d = new Date();
        const off = -d.getTimezoneOffset();
        const sign = off >= 0 ? "+" : "-";
        const o = Math.abs(off);
        return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}.${pad(d.getMilliseconds(), 3)}${sign}${pad(Math.floor(o / 60))}:${pad(o % 60)}`;
    }

    function newId() {
        counter += 1;
        return String(Date.now() % 1000000000 * 10 + (counter % 10));
    }

    const val = (id) => $(id).value;

    // ---------- validación en el navegador (espejo de la del backend; el backend manda) ----------
    const EMAIL = /^[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}$/;

    function validate() {
        const e = {};
        const id = val("f-id").trim();
        if (!id) e.idTxn = "El ID es obligatorio.";
        else if (!/^[A-Za-z0-9_\-]{1,64}$/.test(id)) e.idTxn = "Solo letras, números, guion y guion bajo (máx. 64).";

        const nombre = val("f-nombre").trim();
        if (!nombre) e.nombre = "El nombre es obligatorio.";
        else if (nombre.length < 2 || nombre.length > 80 || !/[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]/.test(nombre)) e.nombre = "Entre 2 y 80 caracteres, con letras.";

        const cedula = val("f-cedula").trim();
        if (!cedula) e.cedula = "La cédula es obligatoria.";
        else if (!/^\d{6,10}$/.test(cedula)) e.cedula = "Entre 6 y 10 dígitos, sin puntos ni letras.";

        const user = val("f-user").trim();
        if (!user) e.user = "El correo es obligatorio.";
        else if (user.length > 254 || !EMAIL.test(user)) e.user = "Correo electrónico inválido.";

        const date = val("f-date").trim();
        if (!date) e.date = "La fecha y hora son obligatorias.";
        else if (!/^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}/.test(date) || isNaN(new Date(date.replace(" ", "T")))) e.date = "Use formato ISO: 2026-09-23T10:30:01.120";

        const value = val("f-value").trim();
        if (!value) e.value = "El valor es obligatorio.";
        else if (!/^\d+(\.\d+)?$/.test(value)) e.value = "Solo dígitos (sin separadores de miles).";
        else if (Number(value) <= 0) e.value = "Debe ser mayor a cero.";

        const method = val("f-method");
        if (!CFG.payment_methods.some((m) => m.toLowerCase() === method.toLowerCase())) e.paymentMethod = "Método de pago no válido.";

        const hash = val("f-hash").trim();
        if (hash && !/^[0-9a-fA-F]{64}$/.test(hash)) e.hash = "Debe ser SHA-256 en hexadecimal (64 caracteres).";
        return e;
    }

    function showErrors(errors) {
        document.querySelectorAll("[data-err]").forEach((el) => {
            const msg = errors[el.dataset.err];
            el.textContent = msg || "";
        });
        Object.entries(FIELDS).forEach(([key, id]) => $(id).classList.toggle("invalid", Boolean(errors[key])));
    }

    // ---------- payload ----------
    function payloadFromForm() {
        const id = val("f-id").trim();
        const value = val("f-value").trim();
        const payload = {
            idTxn: /^\d{1,15}$/.test(id) ? Number(id) : val("f-id"),
            nombre: val("f-nombre"),
            cedula: val("f-cedula"),
            user: val("f-user"),
            date: val("f-date"),
            value: /^\d+(\.\d+)?$/.test(value) ? Number(value) : val("f-value"),
            paymentMethod: val("f-method"),
        };
        const hash = val("f-hash").trim();
        if (hash) payload.hash = hash;
        return payload;
    }

    async function post(bodyText) {
        return api("/api/transactions", { method: "POST", headers: { "Content-Type": "application/json" }, body: bodyText });
    }

    // ---------- resultado ----------
    function renderResult(res) {
        const d = res.data;
        if (!d) {
            $("result").innerHTML = `<div class="banner bad">Sin respuesta JSON (HTTP ${res.status}).</div>`;
            return;
        }
        if (d.detail) {
            $("result").innerHTML = `<div class="banner bad">${esc(typeof d.detail === "string" ? d.detail : JSON.stringify(d.detail))}</div>`;
            return;
        }
        let html = `<div class="result ${esc(d.estado)}"><h3>${chip("st", d.estado)}${d.motivo ? `<span class="chip lv-INFO">${esc(d.motivo)}</span>` : ""}<span class="muted" style="font-size:12px;font-weight:600;">HTTP ${res.status}</span></h3>`;
        html += `<p class="msg">${esc(d.mensaje)}</p>`;
        if (d.errores && d.errores.length) {
            html += "<ul>" + d.errores.map((e) => `<li><strong>${esc(e.campo)}</strong> · <code>${esc(e.codigo)}</code> — ${esc(e.mensaje)}</li>`).join("") + "</ul>";
        }
        if (d.hash) html += `<div><strong style="font-size:12px;">Hash (${esc(d.hash_origen || "recibido")}):</strong><div class="mono">${esc(d.hash)}</div></div>`;
        if (d.ventana) {
            const w = d.ventana;
            const anchor = w.entradas.length ? w.entradas[w.entradas.length - 1].fecha : null;
            html += `<h4 style="margin:14px 0 4px; color:var(--primary-dark);">Ventana deslizante de ${esc(w.usuario)}</h4>`;
            html += `<div class="muted" style="font-size:13px;">${w.cantidad} de ${w.limite} permitidas en ${w.ventana_segundos} s${w.tardia ? " · llegó con fecha anterior a la ventana vigente" : ""}</div>`;
            html += windowSvg(w.entradas, w.ventana_segundos, w.limite, anchor);
            if (w.salieron.length) {
                html += `<div class="muted" style="font-size:13px;">Salieron de la ventana activa (siguen en el historial): ${w.salieron.map((e) => "#" + esc(e.idTxn)).join(", ")}</div>`;
            }
        }
        if (d.anomalias && d.anomalias.length) {
            html += d.anomalias.map((a) => `<div class="banner warn" style="margin:10px 0 0;">Anomalía <strong>${esc(a.tipo)}</strong> · nivel ${esc(a.nivel)} · ${a.cantidad_transacciones} transacciones (límite ${a.limite})${a.franja ? " · franja " + esc(a.franja) : ""}</div>`).join("");
        }
        if (d.franja_horaria) {
            html += `<div class="muted" style="font-size:12px; margin-top:8px;">Franja ${esc(d.franja_horaria.franja)}: ${d.franja_horaria.cantidad} de ${d.franja_horaria.limite} permitidas.</div>`;
        }
        if (d.ok) {
            html += `<div class="btn-row"><button class="btn small" id="btn-verify" data-id="${esc(d.idTxn)}">Verificar integridad del hash guardado</button><a class="btn small" style="text-decoration:none;" href="/antifraude">Ver en el dashboard</a></div><div id="verify-out"></div>`;
        }
        html += `<details class="raw"><summary>Respuesta JSON</summary><pre class="json">${esc(JSON.stringify(d, null, 2))}</pre></details></div>`;
        $("result").innerHTML = html;
        const verify = $("btn-verify");
        if (verify) verify.onclick = verifyStored;
    }

    async function verifyStored(event) {
        const id = event.target.dataset.id;
        const res = await api(`/api/transactions/${encodeURIComponent(id)}/verify`);
        const d = res.data || {};
        $("verify-out").innerHTML = `<div class="banner ${d.coincide ? "warn" : "bad"}" style="margin-top:10px;${d.coincide ? "background:var(--ok-soft);border-color:#a5d6a7;color:var(--ok);" : ""}">${esc(d.mensaje || d.detail || "Sin respuesta")}</div>`;
    }

    // ---------- envío ----------
    async function submitForm(event) {
        event.preventDefault();
        // Con un hash ya calculado la fecha forma parte de lo firmado: no se debe reemplazar.
        if ($("f-autodate").checked && !val("f-hash").trim()) $("f-date").value = nowIso();
        const errors = validate();
        showErrors(errors);
        if (Object.keys(errors).length && !$("f-novalidate").checked) {
            $("result").innerHTML = `<div class="banner bad">Corrija los campos marcados. (Active el “Modo prueba” para enviarlos igual y ver la respuesta del backend.)</div>`;
            return;
        }
        $("btn-send").disabled = true;
        try {
            const res = await post(JSON.stringify(payloadFromForm()));
            renderResult(res);
            if (res.data && res.data.ok) {
                lastAcceptedId = res.data.idTxn;
                $("f-id").value = newId();
                $("f-hash").value = ""; // el hash era de la transacción anterior
                $("hash-note").textContent = "";
                $("f-autodate").checked = true;
            }
            loadRecent();
        } catch (err) {
            $("result").innerHTML = `<div class="banner bad">No se pudo contactar al servidor: ${esc(err.message)}</div>`;
        } finally {
            $("btn-send").disabled = false;
        }
    }

    async function burst() {
        const count = Math.max(1, Math.min(30, Number($("b-count").value) || 1));
        const delay = Math.max(0, Number($("b-delay").value) || 0);
        const errors = validate();
        delete errors.idTxn; delete errors.date;
        showErrors(errors);
        if (Object.keys(errors).length) { $("burst-log").innerHTML = `<div class="banner bad" style="margin-top:12px;">Complete correctamente los datos del formulario antes de lanzar la ráfaga.</div>`; return; }
        $("btn-burst").disabled = true;
        const lines = [];
        let last = null;
        for (let i = 0; i < count; i++) {
            const payload = payloadFromForm();
            payload.idTxn = newId();
            payload.date = nowIso();
            delete payload.hash;
            const res = await post(JSON.stringify(payload));
            last = res;
            const d = res.data || {};
            lines.push(`<tr><td>${i + 1}</td><td class="mono">${esc(payload.idTxn)}</td><td>${chip("st", d.estado || "ERROR")}</td><td class="num">${d.ventana ? d.ventana.cantidad + "/" + d.ventana.limite : "—"}</td><td>${esc(d.motivo || "")}</td></tr>`);
            $("burst-log").innerHTML = `<div class="tscroll"><table class="tight"><tr><th>#</th><th>idTxn</th><th>Estado</th><th class="num">En ventana</th><th>Motivo</th></tr>${lines.join("")}</table></div>`;
            if (i < count - 1 && delay) await new Promise((r) => setTimeout(r, delay));
        }
        if (last) renderResult(last);
        $("f-id").value = newId();
        $("btn-burst").disabled = false;
        loadRecent();
    }

    // ---------- JSON crudo y casos de prueba ----------
    /** Cada caso usa un correo nuevo para que el resultado dependa solo del caso y no de pruebas anteriores. */
    function base(over) {
        const user = `demo${Math.random().toString(36).slice(2, 7)}@correo.com`;
        return Object.assign({ idTxn: Number(newId()), nombre: "Ana Pérez", cedula: "1012345678", user, date: nowIso(), value: 50000, paymentMethod: CFG.payment_methods[0] }, over);
    }
    const pretty = (o) => JSON.stringify(o, null, 2);

    const PRESETS = [
        ["1. Transacción correcta → VALID", () => pretty(base())],
        ["2. Campo null → NULL_FIELD", () => pretty(base({ user: null }))],
        ["3. Campo vacío → EMPTY_FIELD", () => pretty(base({ nombre: "" }))],
        ["4. Correo inválido → INVALID_EMAIL", () => pretty(base({ user: "correo-sin-arroba" }))],
        ["5. Tipo incorrecto → INVALID_TYPE", () => pretty(base({ value: [50000], idTxn: true }))],
        ["6. Número como texto \"50000\" → se normaliza", () => pretty(base({ value: "50000" }))],
        ["6b. Valor \"abc\" → INVALID_VALUE (nunca 0)", () => pretty(base({ value: "abc" }))],
        ["7. ID duplicado → DUPLICATE_TRANSACTION", () => pretty(base({ idTxn: lastAcceptedId ?? 1 }))],
        ["11. Hash alterado → HASH_MISMATCH", async () => {
            const original = base({ user: "hash@correo.com" });
            const res = await api("/api/transactions/hash", { method: "POST", body: JSON.stringify(original) });
            const hash = res.data && res.data.hash ? res.data.hash : "0".repeat(64);
            return pretty(Object.assign({}, original, { value: 99999, hash }));
        }],
        ["JSON mal formado → MALFORMED_JSON", () => '{"idTxn": 1, "user": "a@a.com", "value": '],
    ];

    function fillPresets() {
        $("preset").innerHTML = PRESETS.map((p, i) => `<option value="${i}">${esc(p[0])}</option>`).join("");
    }

    async function loadPreset() {
        $("raw").value = await PRESETS[Number($("preset").value)][1]();
    }

    async function sendRaw() {
        const res = await post($("raw").value);
        renderResult(res);
        if (res.data && res.data.ok) lastAcceptedId = res.data.idTxn;
        loadRecent();
    }

    async function calcHash() {
        if ($("f-autodate").checked) $("f-date").value = nowIso();
        $("f-autodate").checked = false; // el hash firma esta fecha exacta
        const errors = validate();
        delete errors.hash;
        showErrors(errors);
        if (Object.keys(errors).length) { $("result").innerHTML = `<div class="banner bad">Complete los datos correctamente para calcular el hash.</div>`; return; }
        const payload = payloadFromForm();
        delete payload.hash;
        const res = await api("/api/transactions/hash", { method: "POST", body: JSON.stringify(payload) });
        if (res.data && res.data.hash) {
            $("f-hash").value = res.data.hash;
            $("hash-note").textContent = `Hash calculado para la fecha ${payload.date}. La hora automática se desactivó para que coincida; si cambia cualquier dato, el servidor rechazará el hash.`;
        } else $("result").innerHTML = `<div class="banner bad">${esc((res.data && res.data.detail) || "No se pudo calcular el hash")}</div>`;
    }

    // ---------- últimas transacciones ----------
    async function loadRecent() {
        const res = await api("/api/transactions?limit=8");
        if (!res.ok || !Array.isArray(res.data)) {
            $("recent").innerHTML = `<tr><td class="empty">${esc((res.data && res.data.detail) || "No disponible")}</td></tr>`;
            return;
        }
        if (!res.data.length) { $("recent").innerHTML = `<tr><td class="empty">Aún no hay transacciones.</td></tr>`; return; }
        $("recent").innerHTML = `<tr><th>ID</th><th>Usuario</th><th class="num">Valor</th><th>Hora</th><th>Estado</th></tr>` +
            res.data.map((t) => `<tr><td class="mono">${esc(t.id_txn ?? "—")}</td><td>${esc(t.usuario_email ?? "—")}</td><td class="num">${t.valor != null ? money(t.valor) : "—"}</td><td>${time(t.fecha_txn || t.fecha_creacion)}</td><td>${chip("st", t.estado)}${t.motivo ? `<div class="muted" style="font-size:11px;">${esc(t.motivo)}</div>` : ""}</td></tr>`).join("");
    }

    // ---------- init ----------
    function init() {
        $("f-id").value = newId();
        $("f-user").value = "belen@correo.com";
        $("f-nombre").value = "Belén Castilla";
        $("f-cedula").value = "1012345678";
        $("f-date").value = nowIso();
        $("f-value").value = "25000";
        fillPresets();
        $("txn-form").addEventListener("submit", submitForm);
        $("btn-newid").onclick = () => { $("f-id").value = newId(); };
        $("btn-now").onclick = () => { $("f-date").value = nowIso(); };
        $("f-autodate").onchange = () => { if ($("f-autodate").checked) $("f-date").value = nowIso(); };
        $("f-date").addEventListener("input", () => { $("f-autodate").checked = false; });
        $("btn-burst").onclick = burst;
        $("btn-preset").onclick = loadPreset;
        $("btn-raw").onclick = sendRaw;
        $("btn-form2json").onclick = () => { $("raw").value = pretty(payloadFromForm()); };
        const hashBtn = $("btn-hash");
        if (hashBtn) hashBtn.onclick = calcHash;
        loadRecent();
        loadPreset();
    }
    init();
})();
