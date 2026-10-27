"""Recursos web compartidos: carpetas de plantillas y archivos estáticos."""

from pathlib import Path

from fastapi.templating import Jinja2Templates

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
templates.env.filters["pesos"] = lambda valor: "${:,.0f}".format(valor).replace(",", ".")  # $16.000, formato colombiano
