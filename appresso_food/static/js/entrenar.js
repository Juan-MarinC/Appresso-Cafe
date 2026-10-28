// Entrenamiento de la red de gestos con ml5.neuralNetwork: grabar ejemplos (los 21 puntos de la mano, nunca la
// imagen), entrenar, evaluar con ejemplos que la red no vio y guardar el modelo en el proyecto para /gestos.
(function () {
    const MS_PREPARAR = 1500;    // cuenta regresiva para poner la mano antes de grabar
    const MS_GRABAR = 3000;
    const EPOCAS = 60;
    const { rasgos, muyLejos, CLASES } = window.GestosReglas;
    const $ = (id) => document.getElementById(id);
    const MINIMO = Number($("clases").dataset.minimo);  // ejemplos por gesto antes de poder entrenar (lo fija el servidor)
    const TOKEN = $("clases").dataset.token;            // solo viene si esta página se abrió en el equipo del servidor
    const video = $("video"), lienzo = $("lienzo");
    let muestras = [];           // {x: [42 números], y: "combo2"}
    let grabando = null;         // {clase, desde, hasta}
    let red = null, precision = null, probando = false, prediciendo = false;
    let conexiones = [];

    const nombre = (clase) => document.querySelector(`[data-clase="${clase}"] .clase__nombre`).textContent;

    function mostrar(titulo, detalle = "") {
        $("estado-titulo").textContent = titulo;
        $("estado-detalle").textContent = detalle;
    }

    function contar() {
        const cuentas = Object.fromEntries(CLASES.map((c) => [c, 0]));
        muestras.forEach((m) => { cuentas[m.y] += 1; });
        CLASES.forEach((c) => {
            const celda = document.querySelector(`[data-cuenta="${c}"]`);
            celda.textContent = cuentas[c];
            celda.closest(".clase").classList.toggle("clase--lista", cuentas[c] >= MINIMO);
        });
        $("entrenar").disabled = CLASES.some((c) => cuentas[c] < MINIMO);
        return cuentas;
    }

    function alDetectar(manos) {
        const mano = manos[0];
        const ahora = performance.now();
        CamaraMano.dibujar(lienzo, video, mano, conexiones);
        const lejos = mano && muyLejos(mano, video.videoHeight);

        if (grabando) {
            if (ahora < grabando.desde) {
                $("lectura").textContent = `Prepárate: ${nombre(grabando.clase)}…`;
            } else if (ahora <= grabando.hasta) {
                if (mano && !lejos) muestras.push({ x: rasgos(mano), y: grabando.clase });
                $("progreso-barra").style.width = `${Math.round(((ahora - grabando.desde) / MS_GRABAR) * 100)}%`;
                $("lectura").textContent = mano ? (lejos ? "Acércate un poco" : `Grabando ${nombre(grabando.clase)}…`) : "No veo tu mano";
                contar();
            } else {
                mostrar(`Listo: ${nombre(grabando.clase)}`, "Elige otro gesto o vuelve a grabar el mismo con la mano en otra posición");
                grabando = null;
                $("progreso-barra").style.width = "0%";
                document.querySelectorAll(".clase").forEach((b) => { b.disabled = false; });
            }
            return;
        }
        if (probando && red && mano && !lejos && !prediciendo) {
            prediciendo = true;
            red.classify(rasgos(mano))
                .then((r) => {
                    const m = CamaraMano.mejor(r);
                    $("lectura").textContent = `La red ve: ${nombre(m.label)} (${Math.round(m.confidence * 100)} %)`;
                })
                .finally(() => { prediciendo = false; });
        } else if (!probando) {
            $("lectura").textContent = mano ? (lejos ? "Acércate un poco a la cámara" : "Mano detectada") : "No veo tu mano";
        }
    }

    function grabar(clase) {
        const ahora = performance.now();
        grabando = { clase, desde: ahora + MS_PREPARAR, hasta: ahora + MS_PREPARAR + MS_GRABAR };
        document.querySelectorAll(".clase").forEach((b) => { b.disabled = true; });
        mostrar(`Grabando: ${nombre(clase)}`, "Mantén el gesto frente a la cámara y muévelo un poco");
    }

    function barajar(lista) {
        const a = lista.slice();
        for (let i = a.length - 1; i > 0; i--) {
            const j = Math.floor(Math.random() * (i + 1));
            [a[i], a[j]] = [a[j], a[i]];
        }
        return a;
    }

    function tablaResultados(aciertos, totales, total) {
        const filas = CLASES.map((c) => `<tr><td>${nombre(c)}</td><td>${aciertos[c]} de ${totales[c]}</td><td>${totales[c] ? Math.round((100 * aciertos[c]) / totales[c]) : 0} %</td></tr>`).join("");
        $("resultado").innerHTML = `<p class="entreno__precision">Precisión con ejemplos que la red no vio: <strong>${precision} %</strong> (${total} ejemplos)</p>`
            + `<div class="tabla-scroll"><table><tr><th>Gesto</th><th>Acertó</th><th>%</th></tr>${filas}</table></div>`;
    }

    async function entrenar() {
        $("entrenar").disabled = true;
        $("guardar").disabled = true;
        $("probar").disabled = true;
        $("resultado").innerHTML = "";
        await CamaraMano.cargarMl5();
        // Se separa el 20 % (de cada gesto) para evaluar con ejemplos que la red nunca vio.
        const entreno = [], prueba = [];
        for (const c of CLASES) {
            const deLaClase = barajar(muestras.filter((m) => m.y === c));
            const corte = Math.round(deLaClase.length * 0.8);
            entreno.push(...deLaClase.slice(0, corte));
            prueba.push(...deLaClase.slice(corte));
        }
        red = ml5.neuralNetwork({ task: "classification" });
        await red.ready;
        barajar(entreno).forEach((m) => red.addData(m.x, [m.y]));
        red.normalizeData();
        await red.train({ epochs: EPOCAS, batchSize: 32 }, (epoca, registro) => {
            const perdida = typeof registro === "number" ? registro : registro && registro.loss;  // según la versión llega de una u otra forma
            $("entreno-estado").textContent = `Época ${epoca + 1} de ${EPOCAS}` + (typeof perdida === "number" ? ` · error ${perdida.toFixed(3)}` : "");
            $("progreso-barra").style.width = `${Math.round(((epoca + 1) / EPOCAS) * 100)}%`;
        });
        const aciertos = Object.fromEntries(CLASES.map((c) => [c, 0]));
        const totales = Object.fromEntries(CLASES.map((c) => [c, 0]));
        for (const m of prueba) {
            totales[m.y] += 1;
            if (CamaraMano.mejor(await red.classify(m.x)).label === m.y) aciertos[m.y] += 1;
        }
        const acertadas = Object.values(aciertos).reduce((a, b) => a + b, 0);
        precision = Math.round((1000 * acertadas) / Math.max(prueba.length, 1)) / 10;
        $("entreno-estado").textContent = `Entrenada con ${entreno.length} ejemplos en ${EPOCAS} épocas.`;
        $("progreso-barra").style.width = "0%";
        tablaResultados(aciertos, totales, prueba.length);
        $("entrenar").disabled = false;
        $("probar").disabled = false;
        $("guardar").disabled = !TOKEN;
    }

    // ml5 solo sabe descargar el modelo; aquí se toma el modelo de TensorFlow.js de la red y se envía al servidor.
    async function guardar() {
        $("guardar").disabled = true;
        const datos = new FormData();
        const archivo = (nombreArchivo, contenido) => datos.append(nombreArchivo, new Blob([contenido]), nombreArchivo);
        await red.neuralNetwork.model.save({
            save: async (a) => {
                archivo("model.json", JSON.stringify({
                    modelTopology: a.modelTopology,
                    weightsManifest: [{ paths: ["./model.weights.bin"], weights: a.weightSpecs }],
                }));
                datos.append("model.weights.bin", new Blob([].concat(a.weightData)), "model.weights.bin");
                return { modelArtifactsInfo: { dateSaved: new Date(), modelTopologyType: "JSON" } };
            },
        });
        archivo("model_meta.json", JSON.stringify({ ...red.neuralNetworkData.meta, _muestras: muestras.length, _precision: precision }));
        archivo("muestras.json", JSON.stringify({ clases: CLASES, muestras }));
        const respuesta = await fetch("/api/gestos/modelo", { method: "POST", body: datos, headers: { "X-Entrenamiento-Token": TOKEN } });
        const r = await respuesta.json();
        mostrar(respuesta.ok ? "Modelo guardado en el proyecto" : "No se pudo guardar", respuesta.ok ? "Ya lo usa la página Pedir con gestos" : r.mensaje);
        $("guardar").disabled = !TOKEN;
        estadoModelo();
    }

    async function cargarMuestras() {
        const respuesta = await fetch("/static/modelos/gestos/muestras.json", { cache: "no-store" });
        if (!respuesta.ok) return mostrar("Todavía no hay muestras guardadas", "Graba ejemplos y guarda un modelo primero");
        const datos = await respuesta.json();
        muestras = datos.muestras.filter((m) => CLASES.includes(m.y) && Array.isArray(m.x) && m.x.length === 42);
        contar();
        mostrar(`Se cargaron ${muestras.length} ejemplos`, "Puedes grabar más o entrenar de nuevo");
    }

    async function estadoModelo() {
        const e = await (await fetch("/api/gestos/modelo", { cache: "no-store" })).json();
        $("modelo-actual").textContent = e.existe
            ? `Modelo en uso: guardado el ${e.guardado.replace("T", " a las ")}, ${e.muestras ?? "?"} ejemplos, precisión ${e.precision ?? "?"} %.`
            : "Todavía no hay un modelo guardado: /gestos usa las reglas de distancias.";
    }

    async function activar() {
        $("activar").disabled = true;
        const modelo = await CamaraMano.iniciar({
            video, alDetectar, avisar: mostrar,
            alEncender: () => { $("visor-inicio").hidden = true; },
        });
        if (!modelo) {
            $("activar").disabled = false;
            return;
        }
        conexiones = modelo.getConnections();
        CamaraMano.pausarConPestana(modelo, video, alDetectar);
        document.querySelectorAll(".clase").forEach((b) => { b.disabled = false; });
        mostrar("Listo para grabar", "Elige el primer gesto");
    }

    document.querySelectorAll(".clase").forEach((b) => b.addEventListener("click", () => grabar(b.dataset.clase)));
    $("activar").addEventListener("click", activar);
    $("entrenar").addEventListener("click", entrenar);
    $("guardar").addEventListener("click", guardar);
    $("probar").addEventListener("click", () => {
        probando = !probando;
        $("probar").textContent = probando ? "Dejar de probar" : "Probar en vivo";
    });
    $("cargar-muestras").addEventListener("click", cargarMuestras);
    $("borrar-muestras").addEventListener("click", () => {
        if (muestras.length && !confirm(`¿Borrar los ${muestras.length} ejemplos grabados?`)) return;
        muestras = [];
        contar();
    });
    estadoModelo();
})();
