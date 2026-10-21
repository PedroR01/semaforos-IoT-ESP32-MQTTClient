## Retomar el proyecto sin el historial del chat

Punto de entrada para `project-mentor`. Corte de contexto: 21/10/2026, zona `America/Buenos_Aires`. Este apartado resume lo necesario para continuar; ampliar solo las secciones relacionadas con la decisión o incremento en trabajo.

### Contexto mínimo y decisiones vigentes

- **Producto:** detección y estado del tráfico con cámaras ESP, con pruebas de maqueta y tráfico real. Se necesitan presencia, cantidad esperando y conteo de pasos/flujo sin duplicados; no solo cajas dibujadas.
- **Arquitectura acordada:** lugar de procesamiento seleccionable al compilar/cargar: externo en una PC/centro o local en un ESP compatible. Mantener definiciones de métricas y contrato común, aunque cambien modelo, runtime y capacidades del hardware.
- **Prioridad:** funcionalidades y arquitectura escalable. Optimizar la PC, instalar CUDA o comprar placas no es condición previa. La inferencia local forma parte del objetivo; no descartarla ni prometer que cualquier ESP pueda ejecutar todo.
- **Desarrollo pausado:** `sensor-controller` como simulador. Sus configuraciones físicas y experiencia MQTT son referencia. No reactivar sensores, LEDs, display o máquina de estados por iniciativa propia.
- **Hardware ya informado:** ESP-32S/OV2640/ESP32-CAM-MB; ESP32-S3-N16R8/OV5640; NodeMCU; PC i5-9600K/16 GB/RTX 2060 6 GB y notebook Ryzen 7 5700U/8 GB/Radeon integrada. No volver a pedir este inventario completo; los datos físicos todavía pendientes están en la sección 12.
- **Organización:** un único documento en `docs/`, este archivo. Mentor analiza y revisa; Coding Agent implementa una tarea definida. Esta planificación no autoriza por sí sola cambios funcionales ni carga sobre dispositivos.

### Qué existe y qué todavía no

El firmware `camera-server` tiene perfiles `esp32cam` y `esp32s3`, WiFi y servidor HTTP/MJPEG. Python tiene un detector simple y otro con seguimiento/JSON. **No están implementados el selector externo/local, la inferencia local, la integración MQTT de cámara/visión ni las métricas de espera/cruce.** El JSON y los nombres de perfiles/tópicos de este documento son propuestas, no interfaces ya disponibles.

Problemas registrados: empaquetado Python con dos módulos, semántica de conteos/TTL, reconexión con captura abierta sin frames, perfil/pinout S3 sin validar y documentación histórica contradictoria. No se verificó el circuito físico completo. Los builds intentados tuvieron una restricción de permisos del entorno, no un fallo de compilación demostrado. Ver secciones 3, 7 y 9 para evidencia y límites.

### Por dónde continuar en la próxima sesión

1. Contrastar este resumen con `git status --short` y los archivos relevantes; no repetir la auditoría completa sin cambios que lo justifiquen. La referencia HEAD al redactar este apartado es `ff4c06a`; el árbol de trabajo contiene cambios posteriores sin commit.
2. Empezar por **I0 de la sección 11**: delimitar configuración por modo/capacidades y contrato mínimo. Usar la tabla de decisiones P01–P08 de la sección 12 para identificar únicamente lo que bloquea ese incremento. No convertir todas las dudas de largo plazo en preguntas previas obligatorias.
3. Revisar `firmware/camera-server/platformio.ini`, `include/board_config.h`, `include/camera_pins.h` y `src/main.cpp`; para el contrato y empaquetado, `vision/detector/pyproject.toml` y ambos scripts. Los workflows y ejemplos se revisan cuando el incremento los afecte.
4. Presentar la decisión, alternativas y alcance mínimo. Si el usuario pide continuar con planificación, actualizar aquí la decisión y preparar un brief solo cuando el incremento esté definido. Si pide implementación, ejecutar únicamente el alcance autorizado. No asumir que todos los incrementos del plan están aprobados para ejecución.
5. Registrar resultado, verificaciones, pendientes y siguiente paso, distinguiendo lo decidido de lo recomendado y lo implementado de lo no probado.

**Primer resultado esperado:** una decisión documentada sobre cómo separar perfil físico, selección de procesamiento y capacidades, junto con el contrato mínimo de observación/estado y la delimitación del primer incremento. El trabajo concreto siguiente es corregir empaquetado y agregar configuración/selección explícita, conservando la ruta externa existente y rechazando combinaciones locales aún no soportadas; esto no demuestra ni sustituye el backend local completo.

### Lectura por necesidad y conservación del contexto

| Necesidad                                       | Secciones a ampliar                  |
| ----------------------------------------------- | ------------------------------------ |
| Entender objetivo, dispositivos y código actual | 1–3                                  |
| Decidir modos, capacidades y backend local      | 4 y P01–P03 de la sección 12         |
| Definir espera, unicidad, cruces y fase         | 5 y P05–P07                          |
| Cerrar contrato, identidades y broker           | 6 y P04                              |
| Implementar y verificar un incremento           | 7–9 y su fila en la sección 11       |
| Retomar plan, decisiones y traspaso             | 11–13                                |
| Consultar rendimiento cuando sea necesario      | 10; no es el punto de partida actual |

Los documentos y agentes se guardaron en disco; al corte de esta revisión `docs/README.md`, `.agents/` y `cam_detection.py` siguen sin versionar y hay cambios locales en otros archivos. Una nueva conversación en este mismo árbol debe inspeccionarlos; un clon nuevo no los tendrá hasta incorporarlos al control de versiones. No hacer commit, revertir ni limpiar cambios del usuario sin que forme parte de la tarea.

Los README antiguos pueden describir comportamiento desactualizado. Las instrucciones explícitas vigentes del usuario definen el alcance; este documento conserva las decisiones, mientras el código y las pruebas determinan qué está implementado. Si difieren, registrar la discrepancia, no completar supuestos a partir del chat ausente.

Instrucción sugerida para retomar:

> Usa project-mentor. Lee primero la sección 0 de docs/README.md, contrasta el estado actual del repositorio y continúa la planificación desde el siguiente incremento documentado. Distingue acuerdos de propuestas y plantea solo las decisiones que bloqueen ese incremento. Todavía no implementes código.
