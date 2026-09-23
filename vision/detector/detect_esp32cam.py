import argparse
import time
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO

def parse_args():
    args = argparse.ArgumentParser(description="YOLOv8 sobre stream MJPEG de ESP32-CAM")
    args.add_argument("--url", required=True, help="URL del stream (p.ej. http://<IP>:81/stream)")

    # Modelo a descargar y aplicar de yolo. Por ahora v8 nano, pero hay otras muchos más nuevas, y variaciones más y menos pesadas.
    args.add_argument("--model", default="yolov8n.pt", help="Ruta o nombre del modelo YOLO")
    args.add_argument("--conf", type=float, default=0.35, help="Umbral de confianza")
    args.add_argument("--save", action="store_true", help="Guardar video con anotaciones (output.mp4)")
    args.add_argument("--show", action="store_true", help="Mostrar ventana con vídeo")
    args.add_argument("--max-w", type=int, default=640, help="Redimensionar ancho máximo (0 = no escalar)")
    args.add_argument("--reconnect", type=int, default=3, help="Intentos de reconexión si el stream cae")
    return args.parse_args()

def open_capture(url:str):
    # En streams MJPEG inestables:
    # - cv2.CAP_FFMpeg suele ir mejor que el backend por defecto en algunos sistemas.
    cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1) # minimizar latencia - TODO: revisar más sobre esta propiedad para la captura con CV2...
    return cap

def main():
    args = parse_args()
    model = YOLO(args.model) # Carga el modelo por defecto establecido dentro de la funcion referenciada por la variable args.

    stream = open_capture(args.url)
    if not stream.isOpened():
        print(f"[ERROR] No se puede abrir el stream: {args.url}")
        return

    # Configuracion de guardado opcional
    writer = None
    writer_failed = False

    prev_time = time.time()
    fps = 0.0
    reconnects_left = args.reconnect

    while True:
        ok, frame = stream.read()
        if not ok or frame is None:
            print("[WARN] Frame nulo. Intentando reconectar...")

            # Reiniciando captura...
            stream.release()
            time.sleep(0.7)
            stream = open_capture(args.url)

            if not stream.isOpened():
                reconnects_left -= 1

                if reconnects_left < 0:
                    print("[ERROR] Sin stream y sin reconexiones. Saliendo...")
                    break
                continue

            reconnects_left = args.reconnect
            continue

        # Redimensionar opcional para ganar FPS
        if args.max_w > 0 and frame.shape[1] > args.max_w:
            height = int(frame.shape[0] * (args.max_w / frame.shape[1]))
            frame = cv2.resize(frame, (args.max_w, height), interpolation=cv2.INTER_AREA)

        # Inferencia YOLO
        results = model.predict(source=frame, conf=args.conf, verbose=False, stream=True) # Si se activa stream=True devuelve de a 1 resultado (en lugar de una lista) --> óptimo para videos largos o transmisiones en vivo. Por defecto está en False, lo que devuelve una lista de resultados (aunque sea de un solo frame). Ocupa mucha más RAM.
        annotated = frame.copy()

        # Dibujar detecciones
        for res in results:
            if res.boxes is None:  # type: ignore
                continue
            for box in res.boxes: # type: ignore
                cls_id = int(box.cls[0])
                conf = float(box.conf[0])
                xyxy = box.xyxy[0].cpu().numpy().astype(int)
                posX1, posY1, posX2, posY2 = xyxy.tolist()

                label = f"{model.names.get(cls_id, cls_id)} {conf:.2f}"
                cv2.rectangle(annotated, (posX1, posY1), (posX2, posY2), (0,255,0), 2)
                (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
                cv2.rectangle(annotated, (posX1, posY1 - th-6), (posX1 + tw+4, posY1), (0,255,0), -1)
                cv2.putText(annotated, label, (posX1 +2, posY1 -4), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,0,0), 1)

        # FPS simple (suavizado ligero)
        now = time.time()
        fps = fps * 0.9 + (1.0 / max(1e-6, now - prev_time)) * 0.1
        prev_time = now
        cv2.putText(annotated, f"FPS: {fps:.1f}", (8,20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,255), 2)

        # Inicializar writer con tamaño real del frame
        if args.save and writer is None and not writer_failed:
            height, width = annotated.shape[:2]
            fourcc = cv2.VideoWriter.fourcc(*"mp4v")
            writer = cv2.VideoWriter("output.mp4", fourcc, 20.0, (width, height))
            if not writer.isOpened():
                print("[WARN] No se pudo abrir output.mp4 para escritura")
                writer.release()
                writer = None
                writer_failed = True

        if writer is not None:
            writer.write(annotated)

        if args.show:
            cv2.imshow("ESP32-CAM + YOLOv8n", annotated)
            # Salir con "q" o ESC
            key = cv2.waitKey(1) & 0xFF
            if key in (27, ord("q")):
                break

    if writer is not None:
        writer.release()
    stream.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
