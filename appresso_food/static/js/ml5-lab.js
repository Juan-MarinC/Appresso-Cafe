// Laboratorio de /gestos/ml5: muestra lo que entrega ml5.handPose (hasta 2 manos, x, y, z) y qué mano usaría el kiosko,
// con la misma regla que /gestos (GestosReglas.elegirMano). También pinta la tabla de errores de cámara desde
// CamaraMano.ERRORES_CAMARA, para que la explicación y los mensajes reales no se separen.
(function () {
    const { elegirMano, rasgos } = window.GestosReglas;
    const $ = (id) => document.getElementById(id);
    const video = $("video"), lienzo = $("lienzo");
    const COLOR_USADA = "#D62B1F", COLOR_DESCARTADA = "#9A8F86";
    let conexiones = [];
    let cuadros = [];  // momentos de las últimas lecturas, para las lecturas por segundo

    const CUANDO = {
        NotAllowedError: "La persona pulsa «Bloquear», o ya la había bloqueado antes en este sitio",
        SecurityError: "La página no es segura (http) o está dentro de un marco de otro sitio",
        NotFoundError: "El equipo no tiene cámara o está deshabilitada",
        NotReadableError: "Otra aplicación ya está usando la cámara",
        AbortError: "La cámara falló al encender",
        OverconstrainedError: "La cámara no tiene la resolución pedida (se reintenta con la que tenga)",
    };

    function tablaErrores() {
        const filas = Object.entries(CamaraMano.ERRORES_CAMARA).map(([nombre, [titulo, detalle]]) => {
            const tr = document.createElement("tr");
            for (const texto of [nombre, CUANDO[nombre] || "", `${titulo} · ${detalle}`]) {
                const td = document.createElement("td");
                td.textContent = texto;
                tr.append(td);
            }
            tr.firstChild.innerHTML = `<code>${nombre}</code>`;
            return tr;
        });
        $("tabla-errores").replaceChildren(...filas);
    }

    function mostrar(titulo, detalle = "") {
        $("estado-titulo").textContent = titulo;
        $("estado-detalle").textContent = detalle;
    }

    const lado = (m) => ({ Left: "Izquierda", Right: "Derecha" }[m.handedness] || "?");
    const n = (v, d = 0) => (typeof v === "number" ? v.toFixed(d) : "–");

    function filas(revisadas, alto) {
        if (!revisadas.length) return '<tr><td colspan="5" class="vacio">No veo ninguna mano.</td></tr>';
        return revisadas.map(({ mano, confianza, tamano, motivo }) => {
            const p = mano.index_finger_tip;
            const estado = motivo ? `Descartada: ${motivo}` : "<strong>Usada</strong>";
            return `<tr class="${motivo ? "descartada" : "usada"}"><td>${lado(mano)}</td><td>${Math.round(confianza * 100)} %</td>`
                + `<td>${Math.round((100 * tamano) / alto)} % del alto</td>`
                + `<td>${n(p.x)}, ${n(p.y)} · z ${n(p.z3D, 3)} m</td><td>${estado}</td></tr>`;
        }).join("");
    }

    function alDetectar(manos) {
        const ahora = performance.now();
        cuadros = cuadros.filter((t) => ahora - t < 1000);
        cuadros.push(ahora);
        const { mano, revisadas } = elegirMano(manos, video.videoHeight);
        CamaraMano.dibujarVarias(lienzo, video, revisadas.map((r) => ({ mano: r.mano, color: r.motivo ? COLOR_DESCARTADA : COLOR_USADA })), conexiones);
        $("lab-manos").textContent = manos.length;
        $("lab-fps").textContent = cuadros.length;
        $("lab-filas").innerHTML = filas(revisadas, video.videoHeight);
        $("lab-numeros").textContent = mano ? "[" + rasgos(mano).map((v) => v.toFixed(2)).join(", ") + "]" : "–";
        $("estado-titulo").textContent = manos.length > 1 ? "Veo 2 manos: el kiosko usa la más cercana"
            : mano ? "Veo una mano" : manos.length ? "Veo una mano, pero el kiosko la descarta" : "No veo ninguna mano";
        $("estado-detalle").textContent = "";
    }

    async function activar() {
        $("activar").disabled = true;
        const modelo = await CamaraMano.iniciar({
            video, alDetectar, avisar: mostrar,
            alEncender: () => { $("visor-inicio").hidden = true; },
            alPerder: () => { $("visor-inicio").hidden = false; $("activar").disabled = false; },
        });
        if (!modelo) {
            $("activar").disabled = false;
            return;
        }
        conexiones = modelo.getConnections();
        CamaraMano.pausarConPestana(modelo, video, alDetectar);
    }

    async function estadoModelo() {
        try {
            const e = await (await fetch("/api/gestos/modelo", { cache: "no-store" })).json();
            $("estado-modelo").textContent = e.existe
                ? `Modelo en uso en este servidor: guardado el ${e.guardado.replace("T", " a las ")}, entrenado con ${e.muestras ?? "?"} ejemplos, precisión ${e.precision ?? "?"} % con ejemplos que no vio.`
                : "En este servidor todavía no hay una red guardada: /gestos está usando las reglas de distancias.";
        } catch (error) {
            $("estado-modelo").textContent = "No se pudo consultar el modelo guardado.";
        }
    }

    tablaErrores();
    estadoModelo();
    $("activar").addEventListener("click", activar);
})();
