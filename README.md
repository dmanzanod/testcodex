# testcodex

Automatización RPA con Selenium para navegar `https://www.me.com.br/`, autenticarse y consultar transacciones/cotaciones en estado *Em Andamento*.

## Requisitos

- Python 3.10+
- Google Chrome/Chromium compatible con Selenium
- ChromeDriver compatible con la versión de Chrome/Chromium
- Dependencia Python fija:
  - `selenium==4.29.0`

## Instalación

```bash
python -m pip install -r requirements.txt
```

## Ejecución

```bash
python rpa.py --login "$ME_LOGIN" --password "$ME_PASSWORD"
```

Opciones útiles:

- `--headed`: abre el navegador en modo visible.
- `--timeout`: timeout global en segundos (default: 25).
- `--debug-traceback`: imprime traceback completo para diagnosticar errores.

## Nota de seguridad

Evita almacenar credenciales reales en el código fuente. Lo recomendado es usar variables de entorno o un gestor de secretos.


## Troubleshooting

### `SessionNotCreatedException: Chrome instance exited`

Este error suele ocurrir por incompatibilidad entre Chrome/Chromium y ChromeDriver o por dependencias del sistema faltantes en Linux.

Checklist rápido:

1. Verifica que el navegador y driver sean compatibles en versión principal.
2. Si usas contenedor/VM, instala librerías de Chrome requeridas por tu distro.
3. Prueba `--headed` para ver si el navegador abre correctamente.
4. Activa logs de ChromeDriver:

```bash
export CHROMEDRIVER_LOG=/tmp/chromedriver.log
export CHROMEDRIVER_VERBOSE=1
python rpa.py --login "$ME_LOGIN" --password "$ME_PASSWORD" --debug-traceback
```

5. Si Chrome no está en la ruta estándar, define:

```bash
export CHROME_BINARY=/usr/bin/google-chrome
```
