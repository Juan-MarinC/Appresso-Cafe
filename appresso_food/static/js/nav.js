// Menú desplegable en pantallas pequeñas
(function () {
    const boton = document.getElementById("menu-movil");
    const nav = document.getElementById("nav");
    if (!boton || !nav) return;
    boton.addEventListener("click", function () {
        const abierto = nav.classList.toggle("abierto");
        boton.setAttribute("aria-expanded", String(abierto));
    });
    // El grupo "Equipo" se cierra al tocar fuera de él.
    const equipo = nav.querySelector(".nav__equipo");
    document.addEventListener("click", function (e) {
        if (equipo && !equipo.contains(e.target)) equipo.open = false;
    });
})();

// Aviso de privacidad (base.html): se muestra hasta que la persona pulsa "Entendido".
(function () {
    const aviso = document.getElementById("aviso-privacidad");
    if (!aviso) return;
    const CLAVE = "appresso-aviso-privacidad-v1";
    let visto = false;
    try { visto = localStorage.getItem(CLAVE) === "1"; } catch (e) { /* navegador sin almacenamiento: se muestra igual */ }
    if (visto) return;
    aviso.hidden = false;
    document.getElementById("aviso-privacidad-ok").addEventListener("click", function () {
        aviso.hidden = true;
        try { localStorage.setItem(CLAVE, "1"); } catch (e) { /* sin almacenamiento: volverá a salir, no pasa nada */ }
    });
})();
