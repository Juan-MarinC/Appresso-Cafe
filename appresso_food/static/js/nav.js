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
