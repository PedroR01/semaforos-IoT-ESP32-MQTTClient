# Contribuir

Los proyectos PlatformIO se compilan de forma independiente. Una modificación de firmware debe indicar el proyecto y entorno afectados; no se debe crear un `platformio.ini` raíz que fusione placas diferentes.

Antes de abrir un cambio:

1. Ejecutar `git diff --check`.
2. Compilar el entorno PlatformIO afectado.
3. No incluir `secrets.h`, `.pio`, entornos Python, modelos descargados ni resultados de ejecución.
4. Actualizar la documentación del protocolo si cambia una interfaz MQTT.

La integración futura entre visión y semáforo requiere una decisión explícita del propietario y pruebas de comportamiento seguro antes de publicar comandos que afecten hardware.

## Preparar un clon nuevo

Instalar VS Code con las extensiones PlatformIO IDE y C/C++ de Microsoft. Desde la raíz del repositorio, ejecutar el build del proyecto que se vaya a editar:

```text
pio run -d firmware/sensor-controller -e esp32dev
pio run -d firmware/camera-server -e esp32cam
```

El build instala el framework Arduino, las toolchains y las bibliotecas declaradas por PlatformIO. Los perfiles compartidos de IntelliSense están en cada carpeta `.vscode`; no dependen de `.pio` ni de `compile_commands.json`, que son artefactos locales ignorados.

Para obtener el contexto más preciso, abrir como carpeta de VS Code el proyecto correspondiente (`firmware/sensor-controller` o `firmware/camera-server`) y seleccionar el perfil `PlatformIO` adecuado. Si se cambia de placa, regenerar la base local con `pio run -d firmware/camera-server -e esp32s3 -t compiledb` y seleccionar el perfil ESP32-S3.

## Entorno de desarrollo

No hay Dev Container: Docker se retiró del proyecto. La puesta en marcha está en [docs/setup-linux.md](docs/setup-linux.md) y [docs/setup-windows.md](docs/setup-windows.md). La carga del firmware y el monitor serie se hacen desde el sistema anfitrión (puertos `/dev/ttyUSB*` en Linux, `COM*` en Windows).

Para compilar manualmente:

```text
pio run -d firmware/sensor-controller -e esp32dev
pio run -d firmware/camera-server -e esp32cam
pio run -d firmware/camera-server -e esp32s3
python vision/detector/detect_esp32cam.py --help
```
