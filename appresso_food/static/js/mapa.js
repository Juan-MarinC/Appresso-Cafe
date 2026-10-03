// Dibuja el grafo de barrios (nodos y vías) y resalta la ruta más corta (Dijkstra) hacia un barrio.
(function () {
    const NS = "http://www.w3.org/2000/svg";
    const lienzo = document.getElementById("mapa-domicilios");
    if (!lienzo) return;
    const selector = document.getElementById("barrio-consulta");
    const resultado = document.getElementById("ruta-resultado");

    function nodo(nombre, atributos, texto) {
        const e = document.createElementNS(NS, nombre);
        for (const k in atributos) e.setAttribute(k, atributos[k]);
        if (texto !== undefined) e.textContent = texto;
        return e;
    }
    const km = (n) => n.toLocaleString("es-CO", { minimumFractionDigits: 1, maximumFractionDigits: 1 });

    fetch("/api/domicilios/mapa").then((r) => r.json()).then(function (datos) {
        const pos = new Map(datos.nodos.map((n) => [n.nombre, n]));
        const aristas = datos.aristas.map(function (a) {
            const o = pos.get(a.origen), d = pos.get(a.destino);
            const linea = nodo("line", { class: "arista", x1: o.x, y1: o.y, x2: d.x, y2: d.y });
            const etiqueta = nodo("text", { class: "km", x: (o.x + d.x) / 2 + 6, y: (o.y + d.y) / 2 - 6 }, km(a.km) + " km");
            return { a: a, linea: linea, etiqueta: etiqueta };
        });
        const nodos = datos.nodos.map(function (n) {
            const tienda = n.nombre === datos.restaurante;
            const g = nodo("g", { class: "nodo" + (tienda ? " tienda" : ""), tabindex: "0", role: "button",
                "aria-label": n.nombre + (n.distancia_km !== null ? ": " + km(n.distancia_km) + " km" : "") });
            g.appendChild(nodo("circle", { cx: n.x, cy: n.y, r: tienda ? 18 : 11 }));
            g.appendChild(nodo("text", { x: n.x, y: n.y - (tienda ? 28 : 20), "text-anchor": "middle" }, tienda ? "Restaurante" : n.nombre));
            if (!tienda) {
                g.addEventListener("click", function () { elegir(n.nombre); });
                g.addEventListener("keydown", function (e) {
                    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); elegir(n.nombre); }
                });
            }
            return { n: n, g: g };
        });
        const capaA = nodo("g", {}), capaK = nodo("g", {}), capaN = nodo("g", {});
        aristas.forEach((x) => { capaA.appendChild(x.linea); capaK.appendChild(x.etiqueta); });
        nodos.forEach((x) => capaN.appendChild(x.g));
        lienzo.replaceChildren(capaA, capaK, capaN);

        datos.nodos.filter((n) => n.nombre !== datos.restaurante).forEach(function (n) {
            const o = document.createElement("option");
            o.value = n.nombre;
            o.textContent = n.nombre + " · " + km(n.distancia_km) + " km";
            selector.appendChild(o);
        });
        selector.addEventListener("change", function () { elegir(selector.value); });

        function resaltar(ruta) {
            const enRuta = new Set(ruta);
            const pares = new Set();
            ruta.forEach((b, i) => { if (i) pares.add([ruta[i - 1], b].sort().join("|")); });
            aristas.forEach((x) => x.linea.classList.toggle("en-ruta", pares.has([x.a.origen, x.a.destino].sort().join("|"))));
            nodos.forEach(function (x) {
                const esTienda = x.n.nombre === datos.restaurante;
                x.g.classList.toggle("en-ruta", enRuta.has(x.n.nombre) && !esTienda);
                x.g.classList.toggle("destino", ruta[ruta.length - 1] === x.n.nombre && !esTienda);
            });
        }

        function elegir(barrio) {
            selector.value = barrio;
            fetch("/api/domicilios/ruta?barrio=" + encodeURIComponent(barrio)).then((r) => r.json()).then(function (r) {
                if (!r.ruta) { resultado.textContent = r.mensaje || "Sin ruta."; return; }
                resaltar(r.ruta);
                resultado.replaceChildren();
                const pasos = document.createElement("div");
                pasos.className = "ruta-pasos";
                r.ruta.forEach(function (b, i) {
                    if (i) pasos.appendChild(document.createTextNode(" → "));
                    const s = document.createElement("span");
                    s.textContent = b;
                    pasos.appendChild(s);
                });
                const dato = document.createElement("div");
                dato.className = "dato-grande";
                [[km(r.distancia_km) + " km", "ruta más corta"], [r.minutos + " min", "tiempo estimado"]].forEach(function (p) {
                    const d = document.createElement("div");
                    const s = document.createElement("strong");
                    s.textContent = p[0];
                    const l = document.createElement("span");
                    l.textContent = p[1];
                    d.append(s, l);
                    dato.appendChild(d);
                });
                resultado.append(pasos, dato);
            });
        }
        const primero = datos.nodos.find((n) => n.nombre !== datos.restaurante);
        if (primero) elegir(primero.nombre);
    });
})();
