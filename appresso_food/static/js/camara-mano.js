// Cámara, ml5.handPose y la red de gestos entrenada, compartidos por /gestos (pedir), /entrenar (grabar y entrenar)
// y /gestos/ml5 (laboratorio).
(function () {
    const ML5 = "https://unpkg.com/ml5@1.4.0/dist/ml5.min.js";
    // Huella del archivo: si el CDN entregara otro código (alterado o roto), el navegador se niega a ejecutarlo.
    const ML5_SRI = "sha384-WhQsp6wxLjcueRBZ1VznJM97KGBK+r4P+L3yOCLEUk/H/4uAm9leYfoLx+Fauci2";
    const MODELO = "/static/modelos/gestos/";
    let ml5Listo = null;

    // Lo que responde getUserMedia cuando no puede abrir la cámara: [título, qué hacer]. Lo usa también /gestos/ml5.
    const ERRORES_CAMARA = {
        NotAllowedError: ["No diste permiso para usar la cámara",
            "Para activarla toca el candado junto a la dirección, permite la cámara y recarga la página."],
        SecurityError: ["El navegador bloqueó la cámara en esta página",
            "Solo se permite en https o en localhost, y no dentro de un marco de otro sitio."],
        NotFoundError: ["No encontramos una cámara", "Conecta una cámara o revisa que el equipo tenga una."],
        NotReadableError: ["La cámara está ocupada",
            "Otra aplicación la está usando (Zoom, Teams, Meet o la app Cámara): ciérrala y vuelve a intentar."],
        AbortError: ["La cámara no respondió", "Desconéctala y vuelve a conectarla, o reinicia el navegador."],
        OverconstrainedError: ["La cámara no admite la configuración pedida", "Prueba con otra cámara."],
    };

    function explicarError(error) {
        return ERRORES_CAMARA[error && error.name] || ["No se pudo usar la cámara", "Error del navegador: " + ((error && error.name) || "desconocido") + "."];
    }

    const tieneWebGL = () => {
        const c = document.createElement("canvas");
        return !!(c.getContext("webgl2") || c.getContext("webgl"));
    };

    function cargarMl5() {
        ml5Listo = ml5Listo || new Promise((resolve, reject) => {
            const s = document.createElement("script");
            s.src = ML5;
            s.integrity = ML5_SRI;
            s.crossOrigin = "anonymous";
            s.onload = resolve;
            s.onerror = () => { ml5Listo = null; reject(new Error("ml5")); };  // permite reintentar
            document.head.appendChild(s);
        }).then(() => ml5.tf.ready());  // neuralNetwork no espera a que TensorFlow.js prepare la GPU: sin esto falla al entrenar
        return ml5Listo;
    }

    /** Por qué no cargó ml5 o el modelo de manos, en palabras del usuario: [título, qué hacer]. */
    function explicarFalloMl5() {
        if (!navigator.onLine) return ["Sin conexión a internet", "ml5.js y el modelo de manos se descargan la primera vez."];
        if (!tieneWebGL()) return ["Este navegador no tiene aceleración gráfica (WebGL)", "Actívala en la configuración o usa Chrome o Edge actualizados."];
        return ["No se pudo cargar el reconocimiento de manos", "Revisa la conexión: un firewall puede estar bloqueando unpkg.com o cdn.jsdelivr.net."];
    }

    async function abrirCamara() {
        try {
            return await navigator.mediaDevices.getUserMedia({ video: { facingMode: "user", width: 640, height: 480 }, audio: false });
        } catch (error) {
            if (error.name !== "OverconstrainedError") throw error;
            return navigator.mediaDevices.getUserMedia({ video: true, audio: false });  // la cámara no tiene 640×480: la que tenga
        }
    }

    /**
     * Enciende la cámara en `video`, carga ml5.handPose y llama a alDetectar(manos) con cada cuadro.
     * avisar(titulo, detalle) cuenta cada paso; sinCamara se agrega a los mensajes de error (qué hacer sin cámara).
     * alEncender() corre apenas hay imagen; alPerder() si la cámara se desconecta después.
     * Devuelve el modelo (para pausarlo) o null si algo falló.
     */
    async function iniciar({ video, alDetectar, avisar, sinCamara = "", alEncender = () => {}, alPerder = () => {}, maxManos = 2 }) {
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
            avisar("La cámara no está disponible aquí", "El navegador solo la permite en https o en localhost." + sinCamara);
            return null;
        }
        avisar("Encendiendo la cámara…", "Si el navegador pregunta, permite el acceso a la cámara");
        try {
            video.srcObject = await abrirCamara();
            await video.play();
            // El modelo lee los atributos width/height del video; sin ellos valen 0 y no detecta ninguna mano.
            video.width = video.videoWidth;
            video.height = video.videoHeight;
        } catch (error) {
            const [titulo, detalle] = explicarError(error);
            avisar(titulo, detalle + sinCamara);
            return null;
        }
        alEncender();
        avisar("Cargando el reconocimiento de manos…", "La primera vez tarda unos segundos");
        let modelo;
        try {
            await cargarMl5();
            modelo = await ml5.handPose({ maxHands: maxManos });  // en ml5 1.4 devuelve una promesa
            modelo.detectStart(video, alDetectar);
        } catch (error) {
            const [titulo, detalle] = explicarFalloMl5();
            avisar(titulo, detalle + sinCamara);
            return null;
        }
        // Cable suelto, cámara USB desconectada o el permiso revocado con la página abierta.
        video.srcObject.getVideoTracks()[0].addEventListener("ended", () => {
            modelo.detectStop();
            avisar("Se perdió la cámara", "Se desconectó o se quitó el permiso. Revísala y pulsa Activar cámara." + sinCamara);
            alPerder();
        });
        avisar("Preparando el reconocimiento…", "Unos segundos más, solo la primera vez");
        return modelo;
    }

    /** La red de gestos entrenada en /entrenar, o null si todavía no hay una (entonces se usan las reglas). */
    async function cargarRed() {
        try {
            const estado = await (await fetch("/api/gestos/modelo", { cache: "no-store" })).json();
            if (!estado.existe) return null;
            await cargarMl5();
            const v = "?v=" + encodeURIComponent(estado.guardado);  // un modelo nuevo no debe salir de la caché
            const red = ml5.neuralNetwork({ task: "classification" });
            await red.ready;
            await red.load({ model: MODELO + "model.json" + v, metadata: MODELO + "model_meta.json" + v, weights: MODELO + "model.weights.bin" + v });
            return red;
        } catch (error) {
            console.warn("No se pudo cargar la red de gestos; se usan las reglas.", error);
            return null;
        }
    }

    /** La clase más probable de una predicción de ml5: {label, confidence}. */
    const mejor = (resultados) => resultados.reduce((a, b) => (b.confidence > a.confidence ? b : a));

    /** Dibuja el esqueleto de varias manos: [{mano, color}]. */
    function dibujarVarias(lienzo, video, manos, conexiones) {
        const ctx = lienzo.getContext("2d");
        lienzo.width = video.videoWidth;
        lienzo.height = video.videoHeight;
        ctx.clearRect(0, 0, lienzo.width, lienzo.height);
        for (const { mano, color } of manos) {
            ctx.strokeStyle = "#FFFFFF";
            ctx.lineWidth = 3;
            for (const [a, b] of conexiones) {
                ctx.beginPath();
                ctx.moveTo(mano.keypoints[a].x, mano.keypoints[a].y);
                ctx.lineTo(mano.keypoints[b].x, mano.keypoints[b].y);
                ctx.stroke();
            }
            ctx.fillStyle = color;
            for (const p of mano.keypoints) {
                ctx.beginPath();
                ctx.arc(p.x, p.y, 6, 0, Math.PI * 2);
                ctx.fill();
            }
        }
    }

    const dibujar = (lienzo, video, mano, conexiones) => dibujarVarias(lienzo, video, mano ? [{ mano, color: "#F2B134" }] : [], conexiones);

    /** Con la pestaña oculta no tiene sentido gastar CPU leyendo la cámara. */
    function pausarConPestana(modelo, video, alDetectar) {
        document.addEventListener("visibilitychange", () => {
            if (document.hidden) modelo.detectStop();
            else if (video.srcObject && video.srcObject.active) modelo.detectStart(video, alDetectar);
        });
    }

    window.CamaraMano = { cargarMl5, iniciar, cargarRed, mejor, dibujar, dibujarVarias, pausarConPestana, explicarError, ERRORES_CAMARA };
})();
