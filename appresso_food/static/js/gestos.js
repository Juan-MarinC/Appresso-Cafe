// Pedido con gestos: ml5.handPose lee la mano desde la cámara y la red entrenada (o, si no hay, las reglas de
// GestosReglas) la traduce a acciones. Todo corre en el navegador. Como en un kiosko: primero comer aquí o para
// llevar, luego se agregan combos a un carrito y el pedido completo se envía con su formulario (POST /pedidos).
(function () {
    const CONFIANZA = 0.8;  // por debajo la red "duda" y deciden las reglas de distancias
    const MS_SOSTENER = (k) => (k === "ayuda" ? 3000 : 1500);  // la ayuda pide más tiempo para no activarse sin querer
    const MS_INACTIVO = 30000;  // kiosko: si nadie hace nada, la siguiente persona no hereda el pedido
    const { clasificar, clave, crearTemporizador, elegirMano, rasgos, desdeClave } = window.GestosReglas;
    const $ = (id) => document.getElementById(id);
    const combos = [...document.querySelectorAll(".combo")];
    const video = $("video"), lienzo = $("lienzo");
    const temporizador = crearTemporizador(MS_SOSTENER);
    const ultimoGesto = {};
    let elegido = null;   // formulario del combo elegido
    let paraLlevar = null;  // null mientras se muestra la bienvenida
    const carrito = [];     // {form, n}: combo y cuántas veces, o {extra, n: 1}: un producto suelto
    const EXTRAS = JSON.parse($("oferta").dataset.extras);  // [{id, nombre, precio}] que se pueden ofrecer
    let oferta = null;        // extra que se está ofreciendo (pulgar sí · puño no)
    let yaOfrecido = false;   // una sola sugerencia por pedido, para no insistir
    let voz = false;          // accesibilidad: leer cada aviso en voz alta
    let origen = "";          // quién leyó el último gesto: la red (con su confianza) o las reglas
    let enviando = false;
    let modelo = null;
    let conexiones = [];  // pares de puntos que forman el esqueleto de la mano
    let red = null;          // red neuronal entrenada en /entrenar
    let prediccion = null;   // última respuesta de la red (llega de forma asíncrona)
    let prediciendo = false;
    let primerCuadro = true;
    let ultimaActividad = 0;

    const DEPURAR = location.search.includes("debug");  // /gestos?debug muestra quién leyó el gesto (red o reglas)
    const pesos = (n) => "$" + n.toLocaleString("es-CO", { maximumFractionDigits: 0 });

    function decir(texto) {
        if (!voz || !window.speechSynthesis) return;
        speechSynthesis.cancel();  // lo nuevo reemplaza lo que se estaba leyendo
        // La voz lee el texto; los emojis son solo apoyo visual.
        const frase = new SpeechSynthesisUtterance(texto.replace(/·/g, ",").replace(/\p{Extended_Pictographic}|\uFE0F/gu, ""));
        frase.lang = "es-CO";
        speechSynthesis.speak(frase);
    }

    function mostrar(titulo, detalle = "") {
        $("estado-titulo").textContent = titulo;
        $("estado-detalle").textContent = detalle;
        decir(`${titulo}. ${detalle}`);
    }

    // Muestra en la tarjeta cuántos combos y su precio; los productos los suma el carrito desde data-base.
    function fijarCantidad(form, n) {
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
            mostrar(`Combo ${form.dataset.numero}: ${form.dataset.nombre}`, "¿Cuántos? Baja la mano y muestra de 1 a 4 dedos · 👍 Pulgar arriba agrega · ✊ Puño cancela");
            form.scrollIntoView({ block: "nearest", behavior: "smooth" });
        } else {
            mostrar("Combo cancelado", "Muestra de 1 a 4 dedos para elegir otro combo");
        }
    }

    function elegirCantidad(n) {
        ultimaActividad = performance.now();
        fijarCantidad(elegido, n);
        const total = Number(elegido.querySelector(".combo__precio").dataset.total) * n;
        mostrar(`${n} × ${elegido.dataset.nombre} = ${pesos(total)}`, "👍 Pulgar arriba para agregarlo · ✊ Puño para cancelar");
    }

    function elegirModalidad(llevar) {
        ultimaActividad = performance.now();
        paraLlevar = llevar;
        $("bienvenida").hidden = true;
        $("menu-kiosko").hidden = false;
        $("carrito").hidden = false;
        $("carrito-modalidad").textContent = llevar ? "Para llevar" : "Para comer aquí";
        mostrar(llevar ? "Para llevar" : "Para comer aquí", "Muestra de 1 a 4 dedos para elegir un combo, o tócalo");
    }

    function bienvenida() {
        paraLlevar = null;
        $("bienvenida").hidden = false;
        $("menu-kiosko").hidden = true;
        mostrar("¿Comer aquí o para llevar?", "Toca una opción o muestra 1 dedo (aquí) o 2 dedos (para llevar)");
    }

    const nombreDe = (item) => (item.extra ? item.extra.nombre : item.form.dataset.nombre);

    // El formulario del carrito lleva cada producto una sola vez, con la suma de todos los combos y extras.
    function pintarCarrito() {
        const form = $("carrito-form");
        form.querySelectorAll(".carrito-item").forEach((i) => i.remove());
        const cantidades = new Map();
        let total = 0;
        $("carrito-lineas").innerHTML = "";
        const sumar = (id, cantidad) => cantidades.set(String(id), (cantidades.get(String(id)) || 0) + cantidad);
        carrito.forEach((item, i) => {
            const { form: combo, extra, n } = item;
            if (extra) {
                sumar(extra.id, n);
            } else {
                const ids = combo.querySelectorAll('input[name="product_id"]');
                combo.querySelectorAll('input[name="quantity"]').forEach((q, j) => sumar(ids[j].value, Number(q.dataset.base) * n));
            }
            const subtotal = (extra ? extra.precio : Number(combo.querySelector(".combo__precio").dataset.total)) * n;
            total += subtotal;
            const li = document.createElement("li");
            li.innerHTML = `<span>${n} × <strong></strong><br><small>${pesos(subtotal)}</small></span><button type="button" class="enlace">Quitar</button>`;
            li.querySelector("strong").textContent = nombreDe(item);
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

    const SIGUE = "Elige otro combo · 👍 Pulgar arriba confirma el pedido · ✊ Puño quita el último";

    function agregar(form) {
        const n = Number(form.querySelector(".combo__cantidad").value);
        carrito.push({ form, n });
        elegir(null);
        pintarCarrito();
        if (!ofrecer()) mostrar(`Agregado: ${n} × ${form.dataset.nombre}`, SIGUE);
    }

    // Como en un kiosko: tras el primer combo se sugiere un producto que el pedido todavía no tiene.
    function ofrecer() {
        if (yaOfrecido) return false;
        const enPedido = new Set(carrito.flatMap((item) => (item.extra ? [String(item.extra.id)]
            : [...item.form.querySelectorAll('input[name="product_id"]')].map((i) => i.value))));
        oferta = EXTRAS.find((e) => !enPedido.has(String(e.id))) || null;
        if (!oferta) return false;
        yaOfrecido = true;
        $("oferta").hidden = false;
        $("oferta-texto").textContent = `¿Le agregas ${oferta.nombre} por ${pesos(oferta.precio)}?`;
        mostrar($("oferta-texto").textContent, "👍 Pulgar arriba: sí · ✊ Puño: no");
        return true;
    }

    function responderOferta(si) {
        ultimaActividad = performance.now();
        const extra = oferta;
        cerrarOferta();
        if (!extra) return;
        if (si) {
            carrito.push({ extra, n: 1 });
            pintarCarrito();
        }
        mostrar(si ? `Agregado: ${extra.nombre}` : "Sin extras", SIGUE);
    }

    function cerrarOferta() {
        oferta = null;
        $("oferta").hidden = true;
    }

    function quitar(i) {
        ultimaActividad = performance.now();
        const [item] = carrito.splice(i, 1);
        pintarCarrito();
        mostrar(`Quitado: ${nombreDe(item)}`, carrito.length ? "👍 Pulgar arriba confirma el pedido · ✊ Puño quita otro" : "Muestra de 1 a 4 dedos para elegir un combo");
    }

    // Con gestos o tocando el botón el pedido sale por el mismo camino: el evento submit del formulario.
    const enviarCarrito = () => $("carrito-form").requestSubmit();

    function vaciar() {
        carrito.length = 0;
        cerrarOferta();
        yaOfrecido = false;
        pintarCarrito();
    }

    function reiniciar() {
        elegir(null);
        vaciar();
        $("nombre").value = "";
        $("carrito-form").reset();  // notas para cocina
        // La siguiente persona no hereda el texto grande, el contraste ni la voz de la anterior.
        document.querySelectorAll('.accesibilidad [aria-pressed="true"]').forEach((b) => b.click());
        bienvenida();
        mostrar("Listo para un nuevo pedido", "Se reinició por inactividad. ¿Comer aquí (1 dedo) o para llevar (2 dedos)?");
    }

    async function pedirAyuda() {
        mostrar("Avisando a un empleado…");
        try {
            const respuesta = await fetch("/api/ayuda", { method: "POST" });
            if (!respuesta.ok) throw new Error(respuesta.status);
            mostrar("Ya avisamos a un empleado", "Viene a ayudarte en un momento");
        } catch (error) {
            mostrar("No pudimos avisar", "Levanta la mano o acércate al mostrador");
        }
    }

    function actuar(gesto) {
        if (gesto.tipo === "ayuda") {
            pedirAyuda();
        } else if (oferta) {
            if (gesto.tipo === "confirmar" || gesto.tipo === "cancelar") responderOferta(gesto.tipo === "confirmar");
            else mostrar($("oferta-texto").textContent, "👍 Pulgar arriba: sí · ✊ Puño: no");
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

    // Con red: se le pide una predicción por vez y se usa la última que llegó. Si la red duda (menos de CONFIANZA),
    // todavía no responde o no hay red, deciden las reglas de distancias: así una mano distinta a la del
    // entrenamiento también puede pedir.
    function leerGesto(mano) {
        if (red && !prediciendo) {
            prediciendo = true;
            red.classify(rasgos(mano))
                .then((r) => { prediccion = CamaraMano.mejor(r); })
                .finally(() => { prediciendo = false; });
        }
        const segura = red && prediccion && prediccion.confidence >= CONFIANZA;
        origen = segura ? `red ${Math.round(prediccion.confidence * 100)} %` : red ? "reglas" : "";
        return segura ? desdeClave(prediccion.label) : clasificar(mano);
    }

    function alDetectar(manos) {
        if (enviando) return;
        const ahora = performance.now();
        if (primerCuadro) {  // el primer cuadro tarda unos segundos (el modelo "calienta"): recién ahora está listo
            primerCuadro = false;
            ultimaActividad = ahora;
            mostrar("Listo: muestra de 1 a 4 dedos", red ? "Reconoce los gestos la red neuronal entrenada" : "Sostén el gesto hasta que la barra se llene");
        }
        // Con dos manos (o una en una foto o pantalla del fondo) se usa la más cercana; ver GestosReglas.elegirMano.
        const { mano, lejos, revisadas } = elegirMano(manos, video.videoHeight);
        CamaraMano.dibujar(lienzo, video, mano, conexiones);
        if (!mano) prediccion = null;
        const gesto = mano ? leerGesto(mano) : null;
        const k = clave(gesto);
        if (gesto) {
            ultimoGesto[k] = gesto;
            ultimaActividad = ahora;
        }
        const r = temporizador(k, ahora);
        $("progreso-barra").style.width = `${Math.round(r.progreso * 100)}%`;
        const seguridad = gesto && origen && DEPURAR ? ` · ${origen}` : "";
        const otra = revisadas.length > 1 ? " · uso la mano más cercana" : "";
        $("lectura").textContent = lejos ? "Acércate un poco a la cámara"
            : gesto ? texto(gesto) + seguridad + otra : mano ? "No reconozco ese gesto" : "No veo tu mano";
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
            alPerder: () => {
                $("visor-inicio").hidden = false;
                $("activar").disabled = false;
                CamaraMano.dibujar(lienzo, video, null, conexiones);
                $("lectura").textContent = "";
            },
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
        e.target.elements.client.value = $("nombre").value.trim() || "Cliente con gestos";
        e.target.elements.para_llevar.value = paraLlevar ? "1" : "0";
        enviando = true;  // deja de leer gestos mientras carga la confirmación
        mostrar("Enviando tu pedido…", $("carrito-total").textContent);
    });
    $("carrito-vaciar").addEventListener("click", () => {
        vaciar();
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
    $("oferta-si").addEventListener("click", () => responderOferta(true));
    $("oferta-no").addEventListener("click", () => responderOferta(false));
    // Accesibilidad: cada botón es un interruptor (aria-pressed); texto grande y contraste son clases en <html>.
    $("acc-voz").hidden = !window.speechSynthesis;
    for (const [id, clase] of [["acc-grande", "texto-grande"], ["acc-contraste", "alto-contraste"], ["acc-voz", null]]) {
        $(id).addEventListener("click", (e) => {
            const activo = e.currentTarget.getAttribute("aria-pressed") !== "true";
            e.currentTarget.setAttribute("aria-pressed", String(activo));
            if (clase) return document.documentElement.classList.toggle(clase, activo);
            voz = activo;
            if (activo) decir(`${$("estado-titulo").textContent}. ${$("estado-detalle").textContent}`);
            else speechSynthesis.cancel();
        });
    }
    combos.forEach((c) => { c.querySelector(".primary-btn").textContent = "Agregar"; });  // con carrito, el botón agrega
    pintarCarrito();
    bienvenida();
})();
