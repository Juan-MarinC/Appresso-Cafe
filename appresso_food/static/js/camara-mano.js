// Cámara, ml5.handPose y la red de gestos entrenada, compartidos por /gestos (pedir) y /entrenar (grabar y entrenar).
(function () {
    const ML5 = "https://unpkg.com/ml5@1.4.0/dist/ml5.min.js";
    const MODELO = "/static/modelos/gestos/";
    let ml5Listo = null;

    function cargarMl5() {
        ml5Listo = ml5Listo || new Promise((resolve, reject) => {
            const s = document.createElement("script");
            s.src = ML5;
            s.onload = resolve;
            s.onerror = reject;
            document.head.appendChild(s);
        }).then(() => ml5.tf.ready());  // neuralNetwork no espera a que TensorFlow.js prepare la GPU: sin esto falla al entrenar
        return ml5Listo;
    }

    /**
     * Enciende la cámara en `video`, carga ml5.handPose y llama a alDetectar(manos) con cada cuadro.
     * avisar(titulo, detalle) cuenta cada paso; sinCamara se agrega a los mensajes de error (qué hacer sin cámara).
     * alEncender() corre apenas hay imagen. Devuelve el modelo (para pausarlo) o null si algo falló.
     */
    async function iniciar({ video, alDetectar, avisar, sinCamara = "", alEncender = () => {} }) {
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
            avisar("La cámara no está disponible aquí", "El navegador solo la permite en https o en localhost." + sinCamara);
            return null;
        }
        avisar("Encendiendo la cámara…", "Si el navegador pregunta, permite el acceso a la cámara");
        try {
            video.srcObject = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "user", width: 640, height: 480 }, audio: false });
            await video.play();
            // El modelo lee los atributos width/height del video; sin ellos valen 0 y no detecta ninguna mano.
            video.width = video.videoWidth;
            video.height = video.videoHeight;
        } catch (error) {
            avisar("No se pudo usar la cámara", (error.name === "NotAllowedError" ? "No diste permiso." : "No encontramos una cámara.") + sinCamara);
            return null;
        }
        alEncender();
        avisar("Cargando el reconocimiento de manos…", "La primera vez tarda unos segundos");
        try {
            await cargarMl5();
            const modelo = await ml5.handPose({ maxHands: 1 });  // en ml5 1.4 devuelve una promesa
            modelo.detectStart(video, alDetectar);
            avisar("Preparando el reconocimiento…", "Unos segundos más, solo la primera vez");
            return modelo;
        } catch (error) {
            avisar("No se pudo cargar el reconocimiento de manos", "Revisa la conexión a internet." + sinCamara);
            return null;
        }
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

    function dibujar(lienzo, video, mano, conexiones) {
        const ctx = lienzo.getContext("2d");
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

    /** Con la pestaña oculta no tiene sentido gastar CPU leyendo la cámara. */
    function pausarConPestana(modelo, video, alDetectar) {
        document.addEventListener("visibilitychange", () => {
            if (document.hidden) modelo.detectStop();
            else modelo.detectStart(video, alDetectar);
        });
    }

    window.CamaraMano = { cargarMl5, iniciar, cargarRed, mejor, dibujar, pausarConPestana };
})();
