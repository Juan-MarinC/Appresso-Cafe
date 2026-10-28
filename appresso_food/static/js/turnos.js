// Pantalla de turnos: consulta /api/turnos cada pocos segundos. Con ?pedido=N resalta ese turno y avisa
// (con vibración en el celular) cuando pasa a "¡Listo!".
(function () {
    const CADA_MS = 3000;
    const $ = (id) => document.getElementById(id);
    const mio = Number(new URLSearchParams(location.search).get("pedido")) || null;
    let listosAntes = null;   // null hasta la primera carga, para no marcar como "nuevo" lo que ya estaba
    let mioListo = false;

    function pintar(lista, turnos, nuevos) {
        lista.replaceChildren(...turnos.map((t) => {
            const li = document.createElement("li");
            li.className = "turno" + (nuevos.has(t.numero) ? " turno--nuevo" : "") + (t.numero === mio ? " turno--mio" : "");
            const numero = document.createElement("strong");
            const nombre = document.createElement("span");
            numero.textContent = "#" + t.numero;
            nombre.textContent = t.cliente;  // textContent: el nombre lo escribe el cliente
            li.append(numero, nombre);
            return li;
        }));
        if (!turnos.length) {
            const vacio = document.createElement("li");
            vacio.className = "turnos__vacio";
            vacio.textContent = "Ninguno por ahora";
            lista.append(vacio);
        }
    }

    function avisarMio(datos) {
        if (!mio) return;
        const listo = datos.listos.some((t) => t.numero === mio);
        const preparando = datos.preparando.some((t) => t.numero === mio);
        const caja = $("mio");
        caja.hidden = !listo && !preparando;
        caja.classList.toggle("turnos-mio--listo", listo);
        caja.textContent = listo ? `¡Tu pedido #${mio} está listo! Acércate al mostrador.` : `Tu pedido #${mio} se está preparando.`;
        if (listo && !mioListo && navigator.vibrate) navigator.vibrate([300, 120, 300, 120, 600]);
        mioListo = listo;
    }

    async function actualizar() {
        let datos;
        try {
            datos = await (await fetch("/api/turnos")).json();
        } catch (error) {
            $("turnos-estado").textContent = "Sin conexión: reintentando…";
            return;
        }
        const ahora = new Set(datos.listos.map((t) => t.numero));
        const nuevos = listosAntes ? new Set([...ahora].filter((n) => !listosAntes.has(n))) : new Set();
        listosAntes = ahora;
        pintar($("listos"), datos.listos, nuevos);
        pintar($("preparando"), datos.preparando, new Set());
        avisarMio(datos);
        $("turnos-estado").textContent = `Actualizado a las ${new Date().toLocaleTimeString("es-CO")}`;
    }

    actualizar();
    setInterval(actualizar, CADA_MS);
})();
