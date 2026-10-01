/* Utilidades compartidas por /transacciones y /antifraude. Sin dependencias externas. */
(function () {
    const $ = (id) => document.getElementById(id);

    function esc(value) {
        return String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
    }

    function money(n) {
        const value = Number(n || 0);
        return (value < 0 ? "-$" : "$") + Math.abs(value).toLocaleString("es-CO", { maximumFractionDigits: 0 });
    }

    function time(iso) {
        if (!iso) return "—";
        const d = new Date(iso);
        if (isNaN(d)) return esc(iso);
        const p = (n, l = 2) => String(n).padStart(l, "0");
        return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}.${p(d.getMilliseconds(), 3)}`;
    }

    function datetime(iso) {
        if (!iso) return "—";
        const d = new Date(iso);
        if (isNaN(d)) return esc(iso);
        return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")} ${time(iso)}`;
    }

    async function api(path, options) {
        const response = await fetch(path, options);
        let data = null;
        try { data = await response.json(); } catch (_) { /* respuesta sin JSON */ }
        return { status: response.status, ok: response.ok, data };
    }

    /**
     * Dibuja una ventana deslizante como línea de tiempo SVG.
     * El borde derecho es la transacción más reciente; el izquierdo, N segundos antes.
     * entries: [{idTxn, fecha(ISO), valor}]  - windowSeconds - limit
     */
    function windowSvg(entries, windowSeconds, limit, anchorIso) {
        const W = 640, H = 112, padL = 14, padR = 14, trackY = 64, trackH = 18;
        const inner = W - padL - padR;
        const list = (entries || []).map((e) => ({ ...e, t: new Date(e.fecha).getTime() })).sort((a, b) => a.t - b.t);
        const anchor = anchorIso ? new Date(anchorIso).getTime() : (list.length ? list[list.length - 1].t : Date.now());
        const x = (t) => padL + Math.max(0, Math.min(1, 1 - (anchor - t) / (windowSeconds * 1000))) * inner;
        const hot = list.length >= limit;
        let svg = `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Ventana deslizante de ${windowSeconds} segundos">`;
        svg += `<rect class="w-track" x="${padL}" y="${trackY}" width="${inner}" height="${trackH}" rx="9"/>`;
        for (let s = 0; s <= windowSeconds; s++) {
            const tx = padL + (s / windowSeconds) * inner;
            svg += `<line class="w-tick" x1="${tx}" x2="${tx}" y1="${trackY}" y2="${trackY + trackH}"/>`;
            if (windowSeconds <= 30 || s % 5 === 0) {
                svg += `<text x="${tx}" y="${trackY + trackH + 14}" text-anchor="middle">-${windowSeconds - s}s</text>`;
            }
        }
        svg += `<text x="${padL}" y="14" text-anchor="start">salen ◄</text><text x="${W - padR}" y="14" text-anchor="end">► entran (más reciente)</text>`;
        list.forEach((e, i) => {
            const cx = x(e.t);
            const lift = (i % 3) * 13; // 3 niveles para que las etiquetas cercanas no se monten
            svg += `<circle class="w-dot ${hot ? "hot" : (list.length === limit - 1 ? "warn" : "")}" cx="${cx}" cy="${trackY + trackH / 2}" r="8"><title>${esc(e.idTxn)} · ${time(e.fecha)} · ${money(e.valor)}</title></circle>`;
            const id = String(e.idTxn);
            const short = id.length > 12 ? "…" + id.slice(-9) : id;
            const side = cx > W - 70 ? "end" : cx < 70 ? "start" : "middle";
            const lx = side === "end" ? cx + 8 : side === "start" ? cx - 8 : cx;
            svg += `<text class="w-label" x="${lx}" y="${trackY - 8 - lift}" text-anchor="${side}">#${esc(short)}</text>`;
        });
        svg += `</svg>`;
        return svg;
    }

    function chip(kind, value) {
        return `<span class="chip ${kind}-${esc(value)}">${esc(value)}</span>`;
    }

    window.Fraud = { $, esc, money, time, datetime, api, windowSvg, chip };
})();
