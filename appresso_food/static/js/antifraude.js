(function () {
    const { $, esc, money, time, datetime, api, windowSvg, chip } = window.Fraud;
    const CFG = JSON.parse($("cfg").textContent);
    let period = "hoy";
    let stats = null;

    const PERIOD_LABEL = { hoy: "Hoy", semana: "Esta semana", mes: "Este mes" };

    const empty = (text) => `<div class="empty">${esc(text)}</div>`;
    const failed = (res) => `<div class="empty">${esc((res.data && res.data.detail) || "No disponible")}</div>`;

    // ---------- resumen ----------
    function trendBadge(t) {
        if (!t || t.cambio_pct === null) return `<span class="muted">sin base de comparación</span>`;
        const up = t.cambio_pct > 0;
        return `<span class="${up ? "up" : "down"}">${up ? "▲" : "▼"} ${Math.abs(t.cambio_pct)}%</span> <span class="muted">vs. anterior (${t.anterior})</span>`;
    }

    function renderBig3() {
        const p = stats.periodos;
        $("big3").innerHTML = ["hoy", "semana", "mes"].map((k) => `
            <div class="kpi"><div class="k">${PERIOD_LABEL[k]}</div><div class="v">${p[k].total_transacciones}</div>
            <div class="s">aceptadas · <strong>${p[k].total_anomalias}</strong> anomalías · ${p[k].rechazadas} rechazadas aparte</div></div>`).join("");
    }

    function renderClasif() {
        const p = stats.periodos[period];
        const buenas = Math.max(p.total_transacciones - p.transacciones_sospechosas, 0);
        const sospechosas = p.transacciones_sospechosas;
        const erroneas = p.rechazadas;
        const total = buenas + sospechosas + erroneas;
        const pct = (n) => (total ? Math.round((1000 * n) / total) / 10 : 0);
        const card = (cls, titulo, n, nota) => `<div class="kpi ${cls}"><div class="k">${titulo}</div><div class="v">${n}</div><div class="s">${pct(n)}% · ${nota}</div></div>`;
        $("clasif").innerHTML = `
            <div class="kpis" style="grid-template-columns:repeat(3,minmax(0,1fr));">
                ${card("ok", "Buenas", buenas, "pasaron todas las reglas")}
                ${card("warn", "Sospechosas / posible fraude", sospechosas, "aceptadas pero con anomalía")}
                ${card("bad", "Erróneas", erroneas, "formato, hash o datos inválidos")}
            </div>
            <div class="stackbar" role="img" aria-label="Proporción de buenas, sospechosas y erróneas">
                <span class="ok" style="width:${pct(buenas)}%"></span><span class="warn" style="width:${pct(sospechosas)}%"></span><span class="bad" style="width:${pct(erroneas)}%"></span>
            </div>
            <div class="muted" style="font-size:12px;margin-top:6px;">${total} peticiones en ${PERIOD_LABEL[period].toLowerCase()}</div>`;
    }

    function renderKpis() {
        const p = stats.periodos[period];
        const s = p.anomalias_por_estado;
        const cards = [
            ["Transacciones aceptadas", p.total_transacciones, `además, ${p.rechazadas} rechazadas por validación (no se cuentan aquí)`, ""],
            ["Total de anomalías", p.total_anomalias, `incluye descartadas · ${p.transacciones_sospechosas} transacciones sospechosas`, p.total_anomalias ? "bad" : "ok"],
            ["% con anomalías", p.porcentaje_anomalias + "%", "sospechosas / aceptadas", p.porcentaje_anomalias ? "warn" : "ok"],
            ["Usuarios afectados", p.usuarios_afectados, `de ${p.usuarios_distintos} usuarios activos`, ""],
            ["Valor sospechoso", money(p.valor_sospechoso), "suma de transacciones sospechosas", p.valor_sospechoso ? "warn" : ""],
            ["Promedio por usuario", p.promedio_por_usuario, "transacciones por usuario", ""],
            ["Anomalías nuevas", s.NUEVA, "sin revisar", s.NUEVA ? "bad" : ""],
            ["Anomalías abiertas", s.ABIERTA, "en revisión", s.ABIERTA ? "warn" : ""],
            ["Anomalías revisadas", s.REVISADA, "confirmadas / resueltas", ""],
            ["Anomalías descartadas", s.DESCARTADA, "falsos positivos", ""],
        ];
        $("kpis").innerHTML = cards.map(([k, v, sub, cls]) => `<div class="kpi ${cls}"><div class="k">${esc(k)}</div><div class="v">${esc(v)}</div><div class="s">${esc(sub)}</div></div>`).join("");
    }

    // ---------- gráficos ----------
    function renderEvolution() {
        const data = stats.evolucion;
        const W = 640, H = 240, L = 34, R = 10, T = 16, B = 40;
        const max = Math.max(1, ...data.map((d) => Math.max(d.transacciones, d.anomalias)));
        const bw = (W - L - R) / data.length;
        const y = (v) => T + (1 - v / max) * (H - T - B);
        let svg = `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Evolución de transacciones y anomalías por día">`;
        for (let i = 0; i <= 4; i++) {
            const v = Math.round((max * i) / 4);
            svg += `<line class="axis" x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}"/><text x="${L - 6}" y="${y(v) + 4}" text-anchor="end">${v}</text>`;
        }
        data.forEach((d, i) => {
            const x = L + i * bw;
            svg += `<rect class="bar" x="${x + 4}" y="${y(d.transacciones)}" width="${bw - 8}" height="${H - B - y(d.transacciones)}" rx="3"><title>${d.fecha}: ${d.transacciones} transacciones, ${d.anomalias} anomalías, ${d.rechazadas} rechazadas</title></rect>`;
            if (i % 2 === 0 || data.length < 8) svg += `<text x="${x + bw / 2}" y="${H - B + 16}" text-anchor="middle">${d.fecha.slice(5)}</text>`;
        });
        const pts = data.map((d, i) => `${L + i * bw + bw / 2},${y(d.anomalias)}`).join(" ");
        svg += `<polyline class="line" points="${pts}"/>` + data.map((d, i) => `<circle class="dot" cx="${L + i * bw + bw / 2}" cy="${y(d.anomalias)}" r="3.5"><title>${d.fecha}: ${d.anomalias} anomalías</title></circle>`).join("");
        svg += `<text x="${L}" y="${H - 6}" text-anchor="start">▮ transacciones</text><text x="${L + 110}" y="${H - 6}" text-anchor="start" style="fill:var(--primary)">━ anomalías</text></svg>`;
        $("evo").innerHTML = svg;
    }

    function renderHeat() {
        const hours = stats.por_hora;
        const max = Math.max(1, ...hours.map((h) => h.anomalias));
        $("heat").innerHTML = hours.map((h) => {
            const a = h.anomalias / max;
            const bg = h.anomalias ? `rgba(198,40,40,${0.18 + 0.72 * a})` : "#fff8f0";
            const color = a > 0.55 ? "#fff" : "var(--primary-dark)";
            return `<div style="background:${bg}; color:${color};" title="${String(h.hora).padStart(2, "0")}:00 · ${h.anomalias} anomalías · ${h.transacciones} transacciones">${String(h.hora).padStart(2, "0")}<small>${h.anomalias}/${h.transacciones}</small></div>`;
        }).join("");
        const peaks = stats.horas_pico;
        $("peaks").textContent = peaks.length ? "Horas pico: " + peaks.map((h) => String(h).padStart(2, "0") + ":00").join(", ") + "  (formato celda: anomalías/transacciones)" : "Sin actividad este mes.";
    }

    function hbars(rows, labelKey, valueKey, fmt) {
        if (!rows.length) return empty("Sin datos.");
        const max = Math.max(1, ...rows.map((r) => r[valueKey]));
        return rows.map((r) => `<div class="hbar"><div>${esc(r[labelKey])}</div><div class="track"><div class="fill" style="width:${(100 * r[valueKey]) / max}%"></div></div><div class="n">${fmt ? fmt(r[valueKey]) : r[valueKey]}</div></div>`).join("");
    }

    function renderBreakdowns() {
        $("levels").innerHTML = ["ALTO", "MEDIO", "BAJO"].map((lv) => `<div class="hbar"><div>${chip("lv", lv)}</div><div class="track"><div class="fill" style="width:${stats.anomalias_por_nivel[lv] ? 100 * stats.anomalias_por_nivel[lv] / Math.max(1, ...Object.values(stats.anomalias_por_nivel)) : 0}%"></div></div><div class="n">${stats.anomalias_por_nivel[lv]}</div></div>`).join("");
        const types = Object.entries(stats.anomalias_por_tipo).map(([tipo, n]) => ({ tipo, n }));
        $("types").innerHTML = hbars(types, "tipo", "n");
        $("payments").innerHTML = hbars(stats.metodos_pago, "metodo", "cantidad");
        const t = stats.tendencias;
        $("trends").innerHTML = `
            <div class="ev"><b>Hoy vs. ayer</b></div>
            <div class="ev"><span>Transacciones</span><span>${t.hoy_vs_ayer.transacciones.actual} · ${trendBadge(t.hoy_vs_ayer.transacciones)}</span></div>
            <div class="ev"><span>Anomalías</span><span>${t.hoy_vs_ayer.anomalias.actual} · ${trendBadge(t.hoy_vs_ayer.anomalias)}</span></div>
            <div class="ev" style="margin-top:8px;"><b>Semana vs. anterior</b></div>
            <div class="ev"><span>Transacciones</span><span>${t.semana_vs_anterior.transacciones.actual} · ${trendBadge(t.semana_vs_anterior.transacciones)}</span></div>
            <div class="ev"><span>Anomalías</span><span>${t.semana_vs_anterior.anomalias.actual} · ${trendBadge(t.semana_vs_anterior.anomalias)}</span></div>`;
        $("cases").innerHTML = hbars(stats.casos_recurrentes, "caso", "cantidad");
        $("users").innerHTML = stats.usuarios_recurrentes.length
            ? `<table class="tight"><tr><th>Usuario</th><th class="num">Txns</th><th class="num">Anom.</th></tr>${stats.usuarios_recurrentes.map((u) => `<tr><td>${esc(u.usuario)}</td><td class="num">${u.transacciones}</td><td class="num">${u.anomalias}</td></tr>`).join("")}</table>`
            : empty("Sin usuarios recurrentes.");
        $("multi").innerHTML = stats.multiples_transacciones.length
            ? `<table class="tight"><tr><th>Usuario</th><th class="num">En ventana</th><th>Hora</th></tr>${stats.multiples_transacciones.map((m) => `<tr><td>${esc(m.usuario)}</td><td class="num">${m.cantidad}</td><td>${time(m.fecha)}</td></tr>`).join("")}</table>`
            : empty("Sin ráfagas detectadas.");
    }

    async function loadStats() {
        const res = await api("/api/stats");
        if (!res.ok) { $("big3").innerHTML = ""; $("kpis").innerHTML = failed(res); return; }
        stats = res.data;
        renderBig3(); renderClasif(); renderKpis(); renderEvolution(); renderHeat(); renderBreakdowns();
    }

    // ---------- ventana deslizante en vivo ----------
    async function loadWindow() {
        const res = await api("/api/window");
        if (!res.ok) { $("window").innerHTML = failed(res); return; }
        const users = res.data.usuarios;
        if (!users.length) { $("window").innerHTML = empty("No hay transacciones activas en ninguna ventana. Envíe transacciones desde /transacciones."); return; }
        $("window").innerHTML = users.map((u) => {
            const hot = u.cantidad >= res.data.limite;
            return `<div class="wuser"><div class="head"><strong>${esc(u.usuario)}</strong>
                <span>${hot ? chip("st", "SUSPICIOUS") : chip("st", "VALID")} ${u.cantidad} de ${res.data.limite} permitidas · ventana ${res.data.ventana_segundos} s hasta ${time(u.ancla)}</span></div>
                ${windowSvg(u.entradas, res.data.ventana_segundos, res.data.limite, u.ancla)}</div>`;
        }).join("");
    }

    async function loadWindowEvents() {
        const res = await api("/api/logs?limit=12&evento=VENTANA_SALE");
        const enter = await api("/api/logs?limit=12&evento=VENTANA_ENTRA");
        if (!res.ok || !enter.ok) { $("winevents").innerHTML = ""; return; }
        const rows = [...res.data.map((l) => ({ ...l, dir: "SALE" })), ...enter.data.map((l) => ({ ...l, dir: "ENTRA" }))]
            .sort((a, b) => (a.ts < b.ts ? 1 : -1)).slice(0, 10);
        $("winevents").innerHTML = rows.length
            ? rows.map((l) => `<div class="ev"><span><b>${l.dir === "ENTRA" ? "▶ entra" : "◀ sale"}</b> #${esc(l.id_txn)} · ${esc(l.usuario)}</span><span class="muted">${time(l.ts)}</span></div>`).join("")
            : empty("Aún no hay movimientos.");
    }

    // ---------- anomalías ----------
    const PAGE = 50;
    let anomLimit = 15, txnLimit = 15;

    function moreButton(id, shown, limit, onMore) {
        const btn = $(id);
        btn.hidden = shown < limit || limit >= 500; // si trajo menos de lo pedido, ya no hay más
        btn.onclick = () => { onMore(); };
    }

    async function loadAnomalies() {
        const estado = $("anom-filter").value;
        const res = await api(`/api/anomalies?limit=${anomLimit}` + (estado ? "&estado=" + estado : ""));
        if (!res.ok) { $("anoms").innerHTML = `<tr><td>${failed(res)}</td></tr>`; $("anom-more").hidden = true; return; }
        moreButton("anom-more", res.data.length, anomLimit, () => { anomLimit += PAGE; loadAnomalies(); });
        if (!res.data.length) { $("anoms").innerHTML = `<tr><td class="empty">No hay anomalías${estado ? " en estado " + esc(estado) : ""}.</td></tr>`; return; }
        $("anoms").innerHTML = `<tr><th>Hora</th><th>Usuario</th><th>Tipo</th><th>Nivel</th><th class="num">Cantidad</th><th>Ventana</th><th>Estado</th><th></th></tr>` +
            res.data.map((a) => `<tr><td>${time(a.fecha_txn)}</td><td>${esc(a.usuario_email)}</td><td><code>${esc(a.tipo)}</code>${a.franja ? ` <span class="muted">${esc(a.franja)}</span>` : ""}</td><td>${chip("lv", a.nivel)}</td>
                <td class="num">${a.cantidad_transacciones}/${a.limite}</td><td>${a.tipo === "POSSIBLE_FRAUD" ? a.ventana_segundos + " s" : "franja"}</td>
                <td><select data-state="${esc(a.id)}" style="padding:5px 8px;border-radius:8px;border:1px solid var(--border);">${["NUEVA", "ABIERTA", "REVISADA", "DESCARTADA"].map((s) => `<option ${s === a.estado ? "selected" : ""}>${s}</option>`).join("")}</select></td>
                <td><button class="btn small" data-timeline="${esc(a.id)}">Línea de tiempo</button></td></tr>`).join("");
        document.querySelectorAll("[data-state]").forEach((el) => el.onchange = async () => {
            await api(`/api/anomalies/${el.dataset.state}`, { method: "PATCH", body: JSON.stringify({ estado: el.value }) });
            loadStats(); loadAnomalies();
        });
        document.querySelectorAll("[data-timeline]").forEach((el) => el.onclick = () => showTimeline(el.dataset.timeline));
    }

    async function showTimeline(id) {
        const res = await api(`/api/anomalies/${id}/timeline`);
        if (!res.ok) { $("timeline").innerHTML = failed(res); return; }
        const a = res.data;
        const events = a.linea_de_tiempo || [];
        let html = `<div class="wuser"><div class="head"><strong>Línea de tiempo · ${esc(a.usuario_email)}</strong><span>${chip("lv", a.nivel)} <code>${esc(a.tipo)}</code> · ${a.cantidad_transacciones} transacciones</span></div>`;
        if (events.length) {
            html += windowSvg(events.map((e) => ({ idTxn: e.id_txn, fecha: e.fecha_txn, valor: e.valor })), a.ventana_segundos, a.limite, events[events.length - 1].fecha_txn);
            html += `<div class="muted" style="font-size:13px;">${events.length} transacciones en ${a.duracion_segundos} s (ventana de ${a.ventana_segundos} s).</div>`;
            html += `<table class="tight"><tr><th>#</th><th>idTxn</th><th>Hora</th><th class="num">+ segundos</th><th class="num">Valor</th></tr>${events.map((e, i) => `<tr><td>${i + 1}</td><td class="mono">${esc(e.id_txn)}</td><td>${time(e.fecha_txn)}</td><td class="num">+${e.offset_segundos}</td><td class="num">${money(e.valor)}</td></tr>`).join("")}</table>`;
        } else {
            html += `<div class="empty">Esta anomalía viene de la regla por franja horaria (límite de ventas por franja), no de una ventana de segundos.</div>`;
        }
        $("timeline").innerHTML = html + "</div>";
        $("timeline").scrollIntoView({ behavior: "smooth", block: "nearest" });
    }

    // ---------- transacciones y logs ----------
    async function loadTxns() {
        const estado = $("txn-filter").value;
        const res = await api(`/api/transactions?limit=${txnLimit}` + (estado ? "&estado=" + estado : ""));
        if (!res.ok) { $("txns").innerHTML = `<tr><td>${failed(res)}</td></tr>`; $("txn-more").hidden = true; return; }
        moreButton("txn-more", res.data.length, txnLimit, () => { txnLimit += PAGE; loadTxns(); });
        if (!res.data.length) { $("txns").innerHTML = `<tr><td class="empty">No hay transacciones.</td></tr>`; return; }
        $("txns").innerHTML = `<tr><th>ID</th><th>Usuario</th><th class="num">Valor</th><th>Pago</th><th>Fecha</th><th>Estado</th><th>Hash</th><th></th></tr>` +
            res.data.map((t) => `<tr><td class="mono">${esc(t.id_txn ?? "—")}</td><td>${esc(t.usuario_email ?? "—")}</td><td class="num">${t.valor != null ? money(t.valor) : "—"}</td><td>${esc(t.metodo_pago ?? "—")}</td><td>${datetime(t.fecha_txn || t.fecha_creacion)}</td>
                <td>${chip("st", t.estado)}${t.motivo ? `<div class="muted" style="font-size:11px;">${esc(t.motivo)}</div>` : ""}</td><td class="mono">${t.hash ? esc(t.hash.slice(0, 12)) + "…" : "—"}</td>
                <td>${t.aceptada ? `<button class="btn small" data-verify="${esc(t.id_txn)}">Verificar</button>` : ""}</td></tr>`).join("");
        document.querySelectorAll("[data-verify]").forEach((el) => el.onclick = async () => {
            const r = await api(`/api/transactions/${encodeURIComponent(el.dataset.verify)}/verify`);
            const d = r.data || {};
            $("verify-out").innerHTML = `<div class="banner ${d.coincide ? "warn" : "bad"}" style="margin:12px 0 0;${d.coincide ? "background:var(--ok-soft);border-color:#a5d6a7;color:var(--ok);" : ""}">#${esc(el.dataset.verify)}: ${esc(d.mensaje || d.detail || "Sin respuesta")}</div>`;
            loadLogs();
        });
    }

    async function loadInvalids() {
        const estado = $("inv-filter").value;
        const res = await api("/api/transactions/invalid?limit=50" + (estado ? "&estado=" + estado : ""));
        if (!res.ok) { $("invalids").innerHTML = `<tr><td>${failed(res)}</td></tr>`; return; }
        if (!res.data.length) { $("invalids").innerHTML = `<tr><td class="empty">No hay peticiones erróneas.</td></tr>`; return; }
        const cls = { PENDIENTE: "st-REJECTED", REPROCESADA: "st-VALID", DESCARTADA: "es-DESCARTADA" };
        $("invalids").innerHTML = `<tr><th>Recibida</th><th>Tipo</th><th>Motivo</th><th>Faltan</th><th>Sobran</th><th>Origen</th><th>Estado</th><th></th></tr>` +
            res.data.map((d) => `<tr><td>${datetime(d.recibido_en)}</td><td>${esc(d.tipo_fallo)}</td><td><code>${esc(d.motivo ?? "—")}</code></td>
                <td class="muted" style="font-size:12px;">${esc((d.campos_faltantes || []).join(", ") || "—")}</td><td class="muted" style="font-size:12px;">${esc((d.campos_desconocidos || []).join(", ") || "—")}</td>
                <td class="muted" style="font-size:12px;">${esc((d.origen && d.origen.ip) || "—")}</td><td><span class="chip ${cls[d.estado] || ""}">${esc(d.estado)}</span></td>
                <td><button class="btn small" data-inv-view="${esc(d.id)}">Ver</button>
                ${d.estado === "PENDIENTE" ? `<button class="btn small" data-inv-re="${esc(d.id)}">Reprocesar</button> <button class="btn small" data-inv-del="${esc(d.id)}">Descartar</button>` : ""}</td></tr>`).join("");
        const byId = new Map(res.data.map((d) => [d.id, d]));
        document.querySelectorAll("[data-inv-view]").forEach((el) => el.onclick = () => {
            const d = byId.get(el.dataset.invView);
            $("inv-out").innerHTML = `<div class="banner warn" style="margin:0 0 12px;"><strong>Petición original</strong> (${esc(d.origen && d.origen.content_type || "sin Content-Type")}):
                <pre class="json">${esc(d.payload_texto)}</pre><strong>Errores:</strong> ${esc((d.errores || []).map((e) => e.campo + ": " + e.mensaje).join(" · ") || "—")}</div>`;
        });
        document.querySelectorAll("[data-inv-re]").forEach((el) => el.onclick = async () => {
            const r = await api(`/api/transactions/invalid/${encodeURIComponent(el.dataset.invRe)}/reprocess`, { method: "POST" });
            $("inv-out").innerHTML = `<div class="banner ${r.data && r.data.ok ? "warn" : "bad"}" style="margin:0 0 12px;">${esc((r.data && (r.data.mensaje || r.data.detail)) || "Sin respuesta")}</div>`;
            slow();
        });
        document.querySelectorAll("[data-inv-del]").forEach((el) => el.onclick = async () => {
            await api(`/api/transactions/invalid/${encodeURIComponent(el.dataset.invDel)}/discard`, { method: "POST" });
            slow();
        });
    }

    async function loadLogs() {
        const res = await api("/api/logs?limit=25");
        if (!res.ok) { $("logs").innerHTML = `<tr><td>${failed(res)}</td></tr>`; return; }
        $("logs").innerHTML = `<tr><th>Hora</th><th>Nivel</th><th>Evento</th><th>Usuario</th><th>idTxn</th><th>Estado</th><th>Motivo</th><th>Detalle</th></tr>` +
            res.data.map((l) => `<tr><td>${time(l.ts)}</td><td>${chip("lv", l.nivel === "WARN" ? "MEDIO" : l.nivel === "ERROR" ? "ALTO" : "INFO")}</td><td><code>${esc(l.evento)}</code></td><td>${esc(l.usuario ?? "—")}</td><td class="mono">${esc(l.id_txn ?? "—")}</td><td>${l.estado ? chip("st", l.estado) : "—"}</td><td>${esc(l.motivo ?? "")}</td><td class="muted" style="font-size:12px;">${esc(l.detalle ?? "")}</td></tr>`).join("");
    }

    // ---------- init ----------
    document.querySelectorAll("#tabs button").forEach((b) => b.onclick = () => {
        period = b.dataset.p;
        document.querySelectorAll("#tabs button").forEach((x) => x.classList.toggle("on", x === b));
        if (stats) { renderClasif(); renderKpis(); }
    });
    $("anom-filter").onchange = loadAnomalies;
    $("txn-filter").onchange = loadTxns;
    $("inv-filter").onchange = loadInvalids;

    const slow = () => { loadStats(); loadAnomalies(); loadTxns(); loadInvalids(); loadLogs(); loadWindowEvents(); };
    slow(); loadWindow();
    setInterval(loadWindow, 1500);
    setInterval(slow, 5000);
})();
