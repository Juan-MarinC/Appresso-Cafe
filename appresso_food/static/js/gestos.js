// Pedido con gestos: ml5.handPose lee la mano desde la cámara y GestosReglas la traduce a acciones.
// Todo corre en el navegador; el pedido se envía con el formulario del combo (POST /pedidos), igual que al tocarlo.
(function () {
    const ML5 = "https://unpkg.com/ml5@1.4.0/dist/ml5.min.js";
    const MS_SOSTENER = (k) => (k === "ayuda" ? 3000 : 1500);  // la ayuda pide más tiempo para no activarse sin querer
    const MS_INACTIVO = 20000;  // kiosko: si nadie hace nada, la siguiente persona no hereda la elección
    const { clasificar, clave, crearTemporizador, muyLejos } = window.GestosReglas;
    const $ = (id) => document.getElementById(id);
    const combos = [...document.querySelectorAll(".combo")];
    const video = $("video"), lienzo = $("lienzo"), ctx = lienzo.getContext("2d");
    const temporizador = crearTemporizador(MS_SOSTENER);
    const ultimoGesto = {};
    let elegido = null;   // formulario del combo elegido
    let enviando = false;
    let modelo = null;
    let conexiones = [];  // pares de puntos que forman el esqueleto de la mano
    let primerCuadro = true;
    let ultimaActividad = 0;

    const pesos = (n) => "$" + n.toLocaleString("es-CO", { maximumFractionDigits: 0 });

    function mostrar(titulo, detalle = "") {
        $("estado-titulo").textContent = titulo;
        $("estado-detalle").textContent = detalle;
    }

    // Las cantidades ocultas del formulario son las de un combo (data-base) multiplicadas por n.
    function fijarCantidad(form, n) {
        form.querySelectorAll('input[name="quantity"]').forEach((i) => { i.value = Number(i.dataset.base) * n; });
        form.querySelector(".combo__cantidad").value = String(n);
        const precio = form.querySelector(".combo__precio");
        precio.textContent = pesos(Number(precio.dataset.total) * n);
    }

    function elegir(form) {
        ultimaActividad = performance.now();
        if (elegido && elegido !== form) fijarCantidad(elegido, 1);
        elegido = form;
        combos.forEach((c) => c.classList.toggle("elegido", c === form));
        if (form) {
            fijarCantidad(form, 1);
            mostrar(`Combo ${form.dataset.numero}: ${form.dataset.nombre}`, "¿Cuántos? Baja la mano y muestra de 1 a 4 dedos · 👍 confirmar · ✊ cancelar");
            form.scrollIntoView({ block: "nearest", behavior: "smooth" });
        } else {
            mostrar("Pedido cancelado", "Muestra de 1 a 4 dedos para elegir otro combo");
        }
    }

    function elegirCantidad(n) {
        ultimaActividad = performance.now();
        fijarCantidad(elegido, n);
        const total = Number(elegido.querySelector(".combo__precio").dataset.total) * n;
        mostrar(`${n} × ${elegido.dataset.nombre} = ${pesos(total)}`, "👍 Pulgar arriba para confirmar · ✊ puño para cancelar");
    }

    async function pedirAyuda() {
        mostrar("Avisando a un empleado…");
        try {
            const respuesta = await fetch("/api/ayuda", { method: "POST" });
            if (!respuesta.ok) throw new Error(respuesta.status);
            mostrar("🖐️ Ya avisamos a un empleado", "Viene a ayudarte en un momento");
        } catch (error) {
            mostrar("No pudimos avisar", "Levanta la mano o acércate al mostrador");
        }
    }

    function actuar(gesto) {
        if (gesto.tipo === "ayuda") {
            pedirAyuda();
        } else if (gesto.tipo === "combo" && elegido) {
            elegirCantidad(gesto.numero);
        } else if (gesto.tipo === "combo") {
            const form = combos.find((c) => c.dataset.numero === String(gesto.numero));
            if (form) elegir(form);
            else mostrar(`No hay combo ${gesto.numero}`, `Elige un número del 1 al ${combos.length}`);
        } else if (gesto.tipo === "confirmar" && elegido) {
            enviando = true;
            mostrar("Enviando tu pedido…", `${elegido.querySelector(".combo__cantidad").value} × ${elegido.dataset.nombre}`);
            elegido.requestSubmit();
        } else if (gesto.tipo === "cancelar" && elegido) {
            elegir(null);
        } else {
            mostrar("Primero elige un combo", "Muestra de 1 a 4 dedos y sostenlos hasta que la barra se llene");
        }
    }

    const texto = (g) => g.tipo === "combo" ? `Veo ${g.numero} ${g.numero === 1 ? "dedo" : "dedos"}`
        : { confirmar: "Veo pulgar arriba", cancelar: "Veo puño cerrado", ayuda: "Veo la palma abierta" }[g.tipo];

    function dibujar(mano) {
        lienzo.width = video.videoWidth;
        lienzo.height = video.videoHeight;
        ctx.clearRect(0, 0, lienzo.width, lienzo.height);
        if (!mano) return;
        ctx.strokeStyle = "#FFFFFF";
        ctx.lineWidth = 3;
        for (const [a, b] of conexiones) {
            ctx.beginPath();
            ctx.moveTo(mano.keypoints[a].x, mano.keypoints[a].y);
            ctx.lineTo(mano.keypoints[b].x, mano.keypoints[b].y);
            ctx.stroke();
        }
        ctx.fillStyle = "#F2B134";
        for (const p of mano.keypoints) {
            ctx.beginPath();
            ctx.arc(p.x, p.y, 6, 0, Math.PI * 2);
            ctx.fill();
        }
    }

    function alDetectar(manos) {
        if (enviando) return;
        const ahora = performance.now();
        if (primerCuadro) {  // el primer cuadro tarda unos segundos (el modelo "calienta"): recién ahora está listo
            primerCuadro = false;
            ultimaActividad = ahora;
            mostrar("Listo: muestra de 1 a 4 dedos", "Sostén el gesto hasta que la barra se llene");
        }
        const mano = manos[0];
        dibujar(mano);
        const lejos = mano && muyLejos(mano, video.videoHeight);
        const gesto = mano && !lejos ? clasificar(mano) : null;
        const k = clave(gesto);
        if (gesto) {
            ultimoGesto[k] = gesto;
            ultimaActividad = ahora;
        }
        const r = temporizador(k, ahora);
        $("progreso-barra").style.width = `${Math.round(r.progreso * 100)}%`;
        $("lectura").textContent = lejos ? "Acércate un poco a la cámara"
            : gesto ? texto(gesto) : mano ? "No reconozco ese gesto" : "No veo tu mano";
        if (r.disparar) actuar(ultimoGesto[r.clave]);
        if (elegido && ahora - ultimaActividad > MS_INACTIVO) {
            elegir(null);
            $("nombre").value = "";
            mostrar("Listo para un nuevo pedido", "Se reinició por inactividad. Muestra de 1 a 4 dedos");
        }
    }

    function cargarScript(src) {
        return new Promise((resolve, reject) => {
            const s = document.createElement("script");
            s.src = src;
            s.onload = resolve;
            s.onerror = reject;
            document.head.appendChild(s);
        });
    }

    async function activar() {
        const boton = $("activar");
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
            return mostrar("La cámara no está disponible aquí", "El navegador solo la permite en https o en localhost. Toca un combo para pedir.");
        }
        boton.disabled = true;
        mostrar("Encendiendo la cámara…", "Si el navegador pregunta, permite el acceso a la cámara");
        try {
            video.srcObject = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "user", width: 640, height: 480 }, audio: false });
            await video.play();
            // El modelo lee los atributos width/height del video; sin ellos valen 0 y no detecta ninguna mano.
            video.width = video.videoWidth;
            video.height = video.videoHeight;
        } catch (error) {
            boton.disabled = false;
            return mostrar("No se pudo usar la cámara",
                error.name === "NotAllowedError" ? "No diste permiso. Puedes tocar un combo para pedir." : "No encontramos una cámara. Puedes tocar un combo para pedir.");
        }
        $("visor-inicio").hidden = true;
        mostrar("Cargando el reconocimiento de manos…", "La primera vez tarda unos segundos");
        try {
            await cargarScript(ML5);
            // En ml5 1.4 devuelve una promesa. El espejo se hace con CSS en el video y en el lienzo (gestos.css).
            modelo = await ml5.handPose({ maxHands: 1 });
            conexiones = modelo.getConnections();
            modelo.detectStart(video, alDetectar);
            mostrar("Preparando el reconocimiento…", "Unos segundos más, solo la primera vez");
        } catch (error) {
            mostrar("No se pudo cargar el reconocimiento de manos", "Revisa la conexión a internet o toca un combo para pedir.");
        }
    }

    // El nombre escrito viaja con cualquier combo, se envíe con gestos o tocando el botón.
    combos.forEach((form) => form.addEventListener("submit", () => {
        const nombre = $("nombre").value.trim();
        if (nombre) form.elements.client.value = nombre;
    }));
    // Quien pide tocando elige la cantidad con el selector de la tarjeta.
    combos.forEach((form) => form.querySelector(".combo__cantidad").addEventListener("change", (e) => {
        if (elegido !== form) elegir(form);
        elegirCantidad(Number(e.target.value));
    }));
    // Con la pestaña oculta no tiene sentido gastar CPU leyendo la cámara.
    document.addEventListener("visibilitychange", () => {
        if (!modelo || enviando) return;
        if (document.hidden) modelo.detectStop();
        else modelo.detectStart(video, alDetectar);
    });
    $("activar").addEventListener("click", activar);
    $("ayuda").addEventListener("click", pedirAyuda);
})();
