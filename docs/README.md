# Documentación del proyecto

Índice y estado al **2026-11-08**. Hito en curso: presentación informal del MVP el **viernes 13/11/2026**.

## Mapa

| Documento | Para qué sirve |
| --- | --- |
| [MVP.md](MVP.md) | Qué se muestra el 13/11: alcance, arquitectura, requerimientos, calendario y decisiones D08–D12. **Fuente de verdad del hito** |
| [setup-linux.md](setup-linux.md) | Instalar y correr todo en Linux (CachyOS/Arch). Incluye registro de verificación |
| [setup-windows.md](setup-windows.md) | Lo mismo en Windows/PowerShell |
| [../protocol/mqtt/README.md](../protocol/mqtt/README.md) | Contrato MQTT (única fuente) |
| [reference.md](reference.md) | Referencia técnica larga: hardware, métricas, modo local, pendientes P01–P08, orden I0–I6, registro de decisiones |
| [agent_session_context.md](agent_session_context.md) | Traspaso para retomar el trabajo sin el historial del chat |

Los estudios (ESP-NOW, YOLO en ESP, etc.) y el guion narrativo de la presentación están en el vault de Obsidian (`CODAPLI/Semáforos IOT`), no en el repo.

## Estado resumido

- **Existe:** firmware `camera-server` (stream MJPEG), dos detectores Python con YOLO y seguimiento.
- **Sin verificar en esta máquina (Linux):** compilación y carga del firmware, stream, detector.
- **Falta para el MVP:** publicación MQTT del detector, controlador con política, semáforo simulado, modo seguro, segundo acceso.
- **Pausado:** `sensor-controller` (simulador con sensores y LEDs).

## Lectura por necesidad

| Necesidad | Documento |
| --- | --- |
| Qué construir esta semana | MVP.md |
| Poner a andar la máquina | setup-linux.md |
| Entender una decisión o un pendiente técnico | reference.md (§12 y §11) |
| Definir un topic o payload | protocol/mqtt/README.md |
| Retomar tras una pausa | agent_session_context.md |
