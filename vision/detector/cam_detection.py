import argparse
import json
import time
from collections import Counter, deque
from dataclasses import dataclass

import cv2
from ultralytics import YOLO

# Clases COCO relevantes -> nombre lógico propio
CLASES = {1: "bicicleta", 2: "auto", 3: "moto", 5: "colectivo", 7: "camion"}


@dataclass
class Track:
    clase: str
    last_seen: float


class TrafficState:
    """
    Estado lógico y liviano del tráfico a partir de detecciones con ID de tracking.

    Expone tres vistas:
      - current:       vehículos presentes en el frame actual, por clase.
      - unique_total:  vehículos únicos (IDs distintos) vistos desde el inicio.
      - unique_window: vehículos únicos que aparecieron en los últimos `window` s.

    Memoria acotada: los IDs que no se ven hace más de `ttl` s se descartan
    (el tracker no reutiliza IDs, así que el total acumulado sigue siendo válido).
    """

    def __init__(self, ttl: float = 10.0, window: float = 60.0):
        self.ttl = ttl
        self.window = window
        self.active: dict[int, Track] = {}
        self.total = Counter()
        self.events: deque[tuple[float, str]] = deque()  # (t_primera_vez, clase)
        self.current = Counter()

    def update(self, dets: list[tuple[int, str]], now: float | None = None):
        """dets: lista de (track_id, nombre_clase) del frame actual."""
        now = now if now is not None else time.time()
        self.current = Counter()

        for tid, clase in dets:
            self.current[clase] += 1
            tr = self.active.get(tid)
            if tr is None:
                # Primera vez que aparece este ID -> vehículo único nuevo.
                # Se cuenta con la clase del primer avistamiento.
                self.active[tid] = Track(clase, now)
                self.total[clase] += 1
                self.events.append((now, clase))
            else:
                tr.last_seen = now

        # Limpieza para mantener memoria acotada
        for tid in [t for t, tr in self.active.items() if now - tr.last_seen > self.ttl]:
            del self.active[tid]
        while self.events and now - self.events[0][0] > self.window:
            self.events.popleft()

    def snapshot(self, now: float | None = None) -> dict:
        now = now if now is not None else time.time()
        win = Counter(c for _, c in self.events)
        return {
            "ts": round(now, 2),
            "current": {**{c: self.current.get(c, 0) for c in CLASES.values()},
                        "total": sum(self.current.values())},
            "unique_total": {**{c: self.total.get(c, 0) for c in CLASES.values()},
                             "total": sum(self.total.values())},
            "unique_window": {**{c: win.get(c, 0) for c in CLASES.values()},
                              "total": sum(win.values()), "window_s": self.window},
        }


def parse_args():
    p = argparse.ArgumentParser(description="YOLOv8 + tracking sobre stream MJPEG de ESP32-CAM")
    p.add_argument("--url", required=True, help="URL del stream (p.ej. http://<IP>:81/stream)")
    p.add_argument("--model", default="yolov8n.pt")
    p.add_argument("--conf", type=float, default=0.35)
    p.add_argument("--tracker", default="bytetrack.yaml", help="bytetrack.yaml (liviano) o botsort.yaml")
    p.add_argument("--save", action="store_true")
    p.add_argument("--show", action="store_true")
    p.add_argument("--max-w", type=int, default=640)
    p.add_argument("--reconnect", type=int, default=3)
    p.add_argument("--ttl", type=float, default=10.0, help="Segundos sin ver un ID antes de descartarlo")
    p.add_argument("--window", type=float, default=60.0, help="Ventana (s) para únicos recientes")
    p.add_argument("--emit-every", type=float, default=1.0, help="Cada cuántos s emitir el snapshot JSON (0 = no)")
    p.add_argument("--jsonl", default=None, help="Archivo .jsonl donde guardar los snapshots")
    return p.parse_args()


def open_capture(url: str):
    cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    return cap


def main():
    args = parse_args()
    model = YOLO(args.model)
    state = TrafficState(ttl=args.ttl, window=args.window)

    stream = open_capture(args.url)
    if not stream.isOpened():
        print(f"[ERROR] No se puede abrir el stream: {args.url}")
        return

    writer, writer_failed = None, False
    jsonl = open(args.jsonl, "a", encoding="utf-8") if args.jsonl else None
    prev_time, fps = time.time(), 0.0
    last_emit = 0.0
    reconnects_left = args.reconnect

    while True:
        ok, frame = stream.read()
        if not ok or frame is None:
            print("[WARN] Frame nulo. Intentando reconectar...")
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

        if args.max_w > 0 and frame.shape[1] > args.max_w:
            h = int(frame.shape[0] * (args.max_w / frame.shape[1]))
            frame = cv2.resize(frame, (args.max_w, h), interpolation=cv2.INTER_AREA)

        # track() en vez de predict(): agrega box.id (persist=True mantiene IDs entre frames)
        results = model.track(
            source=frame, persist=True, tracker=args.tracker,
            conf=args.conf, verbose=False, classes=list(CLASES.keys()),
            max_det=30, iou=0.6, imgsz=320,
        )
        res = results[0]
        annotated = frame.copy()
        dets: list[tuple[int, str]] = []

        if res.boxes is not None and res.boxes.id is not None:
            ids = res.boxes.id.int().tolist()
            clss = res.boxes.cls.int().tolist()
            confs = res.boxes.conf.tolist()
            boxes = res.boxes.xyxy.int().tolist()

            for tid, cid, cf, (x1, y1, x2, y2) in zip(ids, clss, confs, boxes):
                nombre = CLASES.get(cid, str(cid))
                dets.append((tid, nombre))

                label = f"#{tid} {nombre} {cf:.2f}"
                cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 255, 0), 2)
                (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
                cv2.rectangle(annotated, (x1, y1 - th - 6), (x1 + tw + 4, y1), (0, 255, 0), -1)
                cv2.putText(annotated, label, (x1 + 2, y1 - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)

        now = time.time()
        state.update(dets, now)

        # Emisión periódica del snapshot (lo que consumirá la lógica del semáforo)
        if args.emit_every > 0 and now - last_emit >= args.emit_every:
            snap = state.snapshot(now)
            line = json.dumps(snap, ensure_ascii=False)
            print(line)
            if jsonl:
                jsonl.write(line + "\n")
                jsonl.flush()
            last_emit = now

        fps = fps * 0.9 + (1.0 / max(1e-6, now - prev_time)) * 0.1
        prev_time = now
        cv2.putText(annotated, f"FPS: {fps:.1f}  En cuadro: {sum(state.current.values())}  "
                               f"Unicos: {sum(state.total.values())}",
                    (8, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 0, 0), 2)

        if args.save and writer is None and not writer_failed:
            h, w = annotated.shape[:2]
            writer = cv2.VideoWriter("output.mp4", cv2.VideoWriter.fourcc(*"mp4v"), 20.0, (w, h))
            if not writer.isOpened():
                print("[WARN] No se pudo abrir output.mp4 para escritura")
                writer.release()
                writer, writer_failed = None, True

        if writer is not None:
            writer.write(annotated)

        if args.show:
            cv2.imshow("ESP32-CAM + YOLOv8n", annotated)
            if cv2.waitKey(1) & 0xFF in (27, ord("q")):
                break

    if writer is not None:
        writer.release()
    if jsonl:
        jsonl.close()
    stream.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()