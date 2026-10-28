// Pedido con gestos: ml5.handPose lee la mano desde la cámara y la red entrenada (o, si no hay, las reglas de
// GestosReglas) la traduce a acciones. Todo corre en el navegador. Como en un kiosko: primero comer aquí o para
// llevar, luego se agregan combos a un carrito y el pedido completo se envía con su formulario (POST /pedidos).
(function () {
    const CONFIANZA = 0.8;  // por debajo, la red "duda" y no se toma ninguna acción
    const MS_SOSTENER = (k) => (k === "ayuda" ? 3000 : 1500);  // la ayuda pide más tiempo para no activarse sin querer
    const MS_INACTIVO = 30000;  // kiosko: si nadie hace nada, la siguiente persona no hereda el pedido
    const { clasificar, clave, crearTemporizador, muyLejos, rasgos, desdeClave } = window.GestosReglas;
    const $ = (id) => document.getElementById(id);
    const combos = [...document.querySelectorAll(".combo")];
    const video = $("video"), lienzo = $("lienzo");
    const temporizador = crearTemporizador(MS_SOSTENER);
    const ultimoGesto = {};
    let elegido = null;   // formulario del combo elegido
    let paraLlevar = null;  // null mientras se muestra la bienvenida
    const carrito = [];     // {form, n}: combo y cuántas veces
    let enviando = false;
    let modelo = null;
    let conexiones = [];  // pares de puntos que forman el esqueleto de la mano
    let red = null;          // red neuronal entrenada en /entrenar
    let prediccion = null;   // última respuesta de la red (llega de forma asíncrona)
    let prediciendo = false;
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
            mostrar(`Combo ${form.dataset.numero}: ${form.dataset.nombre}`, "¿Cuántos? Baja la mano y muestra de 1 a 4 dedos · 👍 agregar · ✊ cancelar");
            form.scrollIntoView({ block: "nearest", behavior: "smooth" });
        } else {
            mostrar("Combo cancelado", "Muestra de 1 a 4 dedos para elegir otro combo");
        }
    }

    function elegirCantidad(n) {
        ultimaActividad = performance.now();
        fijarCantidad(elegido, n);
        const total = Number(elegido.querySelector(".combo__precio").dataset.total) * n;
        mostrar(`${n} × ${elegido.dataset.nombre} = ${pesos(total)}`, "👍 Pulgar arriba para agregarlo · ✊ puño para cancelar");
    }

    function elegirModalidad(llevar) {
        ultimaActividad = performance.now();
        paraLlevar = llevar;
        $("bienvenida").hidden = true;
        $("menu-kiosko").hidden = false;
        $("carrito").hidden = false;
        $("carrito-modalidad").textContent = llevar ? "🛍️ Para llevar" : "🍽️ Para comer aquí";
        mostrar(llevar ? "Para llevar" : "Para comer aquí", "Muestra de 1 a 4 dedos para elegir un combo, o tócalo");
    }

    function bienvenida() {
        paraLlevar = null;
        $("bienvenida").hidden = false;
        $("menu-kiosko").hidden = true;
        mostrar("¿Comer aquí o para llevar?", "Toca una opción o muestra 1 dedo (aquí) o 2 dedos (para llevar)");
    }

    // El formulario del carrito lleva cada producto una sola vez, con la suma de todos los combos.
    function pintarCarrito() {
        const form = $("carrito-form");
        form.querySelectorAll(".carrito-item").forEach((i) => i.remove());
        const cantidades = new Map();
        let total = 0;
        $("carrito-lineas").innerHTML = "";
        carrito.forEach(({ form: combo, n }, i) => {
            const ids = combo.querySelectorAll('input[name="product_id"]');
            combo.querySelectorAll('input[name="quantity"]').forEach((q, j) => {
                cantidades.set(ids[j].value, (cantidades.get(ids[j].value) || 0) + Number(q.dataset.base) * n);
            });
            const subtotal = Number(combo.querySelector(".combo__precio").dataset.total) * n;
            total += subtotal;
            const li = document.createElement("li");
            li.innerHTML = `<span>${n} × <strong></strong><br><small>${pesos(subtotal)}</small></span><button type="button" class="enlace">Quitar</button>`;
            li.querySelector("strong").textContent = combo.dataset.nombre;
            li.querySelector("button").addEventListener("click", () => quitar(i));
            $("carrito-lineas").append(li);
        });
        if (!carrito.length) $("carrito-lineas").innerHTML = '<li class="vacio">Todavía no has agregado combos.</li>';
        cantidades.forEach((cantidad, id) => {
            for (const [name, value] of [["product_id", id], ["quantity", cantidad]]) {
                const input = Object.assign(document.createElement("input"), { type: "hidden", name, value, className: "carrito-item" });
                form.append(input);
            }
        });
        $("carrito-total").textContent = pesos(total);
        $("carrito-enviar").disabled = $("carrito-vaciar").disabled = !carrito.length;
    }

    function agregar(form) {
        const n = Number(form.querySelector(".combo__cantidad").value);
        carrito.push({ form, n });
        elegir(null);
        pintarCarrito();
        mostrar(`Agregado: ${n} × ${form.dataset.nombre}`, "Elige otro combo con los dedos · 👍 confirmar el pedido · ✊ quitar el último");
    }

    function quitar(i) {
        ultimaActividad = performance.now();
        const [{ form }] = carrito.splice(i, 1);
        pintarCarrito();
        mostrar(`Quitado: ${form.dataset.nombre}`, carrito.length ? "👍 confirmar el pedido · ✊ quitar otro" : "Muestra de 1 a 4 dedos para elegir un combo");
    }

    function enviarCarrito() {
        const form = $("carrito-form");
        form.elements.client.value = $("nombre").value.trim() || "Cliente con gestos";
        form.elements.para_llevar.value = paraLlevar ? "1" : "0";
        enviando = true;
        mostrar("Enviando tu pedido…", $("carrito-total").textContent);
        form.requestSubmit();
    }

    function reiniciar() {
        elegir(null);
        carrito.length = 0;
        pintarCarrito();
        $("nombre").value = "";
        bienvenida();
        mostrar("Listo para un nuevo pedido", "Se reinició por inactividad. ¿Comer aquí (1 dedo) o para llevar (2 dedos)?");
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
        } else if (paraLlevar === null) {
            if (gesto.tipo === "combo" && gesto.numero <= 2) elegirModalidad(gesto.numero === 2);
            else mostrar("¿Comer aquí o para llevar?", "1 dedo: comer aquí · 2 dedos: para llevar");
        } else if (gesto.tipo === "combo" && elegido) {
            elegirCantidad(gesto.numero);
        } else if (gesto.tipo === "combo") {
            const form = combos.find((c) => c.dataset.numero === String(gesto.numero));
            if (form) elegir(form);
            else mostrar(`No hay combo ${gesto.numero}`, `Elige un número del 1 al ${combos.length}`);
        } else if (gesto.tipo === "confirmar" && elegido) {
            agregar(elegido);
        } else if (gesto.tipo === "confirmar" && carrito.length) {
            enviarCarrito();
        } else if (gesto.tipo === "cancelar" && elegido) {
            elegir(null);
        } else if (gesto.tipo === "cancelar" && carrito.length) {
            quitar(carrito.length - 1);
        } else {
            mostrar("Primero elige un combo", "Muestra de 1 a 4 dedos y sostenlos hasta que la barra se llene");
        }
    }

    const texto = (g) => g.tipo === "combo" ? `Veo ${g.numero} ${g.numero === 1 ? "dedo" : "dedos"}`
        : { confirmar: "Veo pulgar arriba", cancelar: "Veo puño cerrado", ayuda: "Veo la palma abierta" }[g.tipo];

    // Con red: se le pide una predicción por vez y se usa la última que llegó. Sin red: las reglas de distancias.
    function leerGesto(mano) {
        if (!red) return clasificar(mano);
        if (!prediciendo) {
            prediciendo = true;
            red.classify(rasgos(mano))
                .then((r) => { prediccion = CamaraMano.mejor(r); })
                .finally(() => { prediciendo = false; });
        }
        return prediccion && prediccion.confidence >= CONFIANZA ? desdeClave(prediccion.label) : null;
    }

    function alDetectar(manos) {
        if (enviando) return;
        const ahora = performance.now();
        if (primerCuadro) {  // el primer cuadro tarda unos segundos (el modelo "calienta"): recién ahora está listo
            primerCuadro = false;
            ultimaActividad = ahora;
            mostrar("Listo: muestra de 1 a 4 dedos", red ? "Reconoce los gestos la red neuronal entrenada" : "Sostén el gesto hasta que la barra se llene");
        }
        const mano = manos[0];
        CamaraMano.dibujar(lienzo, video, mano, conexiones);
        const lejos = mano && muyLejos(mano, video.videoHeight);
        if (!mano || lejos) prediccion = null;
        const gesto = mano && !lejos ? leerGesto(mano) : null;
        const k = clave(gesto);
        if (gesto) {
            ultimoGesto[k] = gesto;
            ultimaActividad = ahora;
        }
        const r = temporizador(k, ahora);
        $("progreso-barra").style.width = `${Math.round(r.progreso * 100)}%`;
        const seguridad = red && gesto ? ` · red ${Math.round(prediccion.confidence * 100)} %` : "";
        $("lectura").textContent = lejos ? "Acércate un poco a la cámara"
            : gesto ? texto(gesto) + seguridad : mano ? "No reconozco ese gesto" : "No veo tu mano";
        if (r.disparar) actuar(ultimoGesto[r.clave]);
        if ((elegido || carrito.length || paraLlevar !== null) && ahora - ultimaActividad > MS_INACTIVO) reiniciar();
    }

    async function activar() {
        $("activar").disabled = true;
        red = await CamaraMano.cargarRed();  // antes de la cámara, para que el primer cuadro ya la use
        modelo = await CamaraMano.iniciar({
            video, alDetectar, avisar: mostrar,
            sinCamara: " Puedes tocar un combo para pedir.",
            alEncender: () => { $("visor-inicio").hidden = true; },
        });
        if (!modelo) {
            $("activar").disabled = false;
            return;
        }
        conexiones = modelo.getConnections();
        CamaraMano.pausarConPestana(modelo, video, alDetectar);
    }

    // Con JavaScript el botón de cada combo lo agrega al carrito en vez de enviarlo solo.
    combos.forEach((form) => {
        form.querySelector('button[type="submit"]').textContent = `Agregar combo ${form.dataset.numero}`;
        form.addEventListener("submit", (e) => {
            e.preventDefault();
            agregar(form);
        });
    });
    $("carrito-form").addEventListener("submit", (e) => {
        if (enviando) return;  // ya lo preparó enviarCarrito()
        e.preventDefault();
        enviarCarrito();
    });
    $("carrito-vaciar").addEventListener("click", () => {
        carrito.length = 0;
        pintarCarrito();
        mostrar("Pedido vacío", "Muestra de 1 a 4 dedos para elegir un combo");
    });
    document.querySelectorAll(".bienvenida__opcion").forEach((b) => b.addEventListener("click", () => elegirModalidad(b.dataset.llevar === "1")));
    $("cambiar-modalidad").addEventListener("click", bienvenida);
    // Quien pide tocando también cuenta como actividad: no se le reinicia el pedido mientras lee el menú.
    document.addEventListener("pointerdown", () => { ultimaActividad = performance.now(); });
    // Quien pide tocando elige la cantidad con el selector de la tarjeta.
    combos.forEach((form) => form.querySelector(".combo__cantidad").addEventListener("change", (e) => {
        if (elegido !== form) elegir(form);
        elegirCantidad(Number(e.target.value));
    }));
    $("activar").addEventListener("click", activar);
    $("ayuda").addEventListener("click", pedirAyuda);
    pintarCarrito();
    bienvenida();
})();
