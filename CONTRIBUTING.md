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

## Dev Container

El repositorio incluye un entorno reproducible en `.devcontainer/`. Requiere Docker Desktop y la extensión `Dev Containers` de VS Code. Después de clonar:

1. Abrir la raíz del repositorio en VS Code.
2. Ejecutar `Dev Containers: Reopen in Container`.
3. Esperar a que finalice la inicialización.

El contenedor instala PlatformIO Core, las dependencias Python del detector, C/C++ y Pylance. El script de creación copia `secrets.h.example` como `secrets.h` si todavía no existe y compila `esp32dev` y `esp32cam`. Los archivos locales de credenciales siguen ignorados por Git; reemplazar sus valores antes de usar hardware real.

La carga del firmware y el monitor serie no forman parte del contenedor. En Windows, usar PlatformIO desde el sistema anfitrión para acceder a `COM5` o `COM6`, o configurar un puente USB explícito si se necesita exponer el dispositivo al contenedor. La compilación y el detector Python sí están pensados para ejecutarse dentro del contenedor.

Para compilar manualmente desde el terminal del contenedor:

```text
pio run -d firmware/sensor-controller -e esp32dev
pio run -d firmware/camera-server -e esp32cam
pio run -d firmware/camera-server -e esp32s3
python vision/detector/detect_esp32cam.py --help
```
