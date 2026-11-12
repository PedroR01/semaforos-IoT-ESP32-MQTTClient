import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from traffic_mqtt import build_payload, detections_topic, new_session_id  # noqa: E402
from cam_detection import TrafficState  # noqa: E402

KW = dict(camera_id="cam-01", approach_id="acceso-01", session_id="s1", seq=7, now=1_700_000_000.0)


class PayloadTests(unittest.TestCase):
    def test_frame_sin_vehiculos_publica_ceros(self):
        p = build_payload(current={}, **KW)
        self.assertEqual(p["status"], "ok")
        self.assertEqual(p["metrics"]["visible_count"], 0)
        self.assertEqual(set(p["metrics"]["by_class"].values()), {0})

    def test_unavailable_no_lleva_metricas(self):
        p = build_payload(current=None, **KW)
        self.assertEqual(p["status"], "unavailable")
        self.assertNotIn("metrics", p)

    def test_conteos_y_campos_del_contrato(self):
        p = build_payload(current={"auto": 3, "moto": 1}, **KW)
        self.assertEqual(p["metrics"]["visible_count"], 4)
        self.assertEqual(p["metrics"]["by_class"]["colectivo"], 0)
        for k in ("v", "camera_id", "approach_id", "processing_mode", "session_id", "seq", "processed_at"):
            self.assertIn(k, p)
        self.assertEqual(p["processing_mode"], "external")
        self.assertEqual(p["processed_at"], "2023-11-14T22:13:20Z")

    def test_topic_y_session(self):
        self.assertEqual(detections_topic("cam-01"), "trafico/v1/cam-01/detections")
        self.assertTrue(new_session_id("cam-01", 0).startswith("cam-01-1970"))


class TrafficStateTests(unittest.TestCase):
    def test_visible_cuenta_detecciones_sin_id(self):
        st = TrafficState()
        st.update([(None, "auto"), (None, "auto"), (5, "moto")], now=1.0)
        self.assertEqual(sum(st.current.values()), 3)
        self.assertEqual(sum(st.total.values()), 1)  # solo el que tiene ID es único

    def test_id_repetido_no_duplica_unicos(self):
        st = TrafficState()
        st.update([(1, "auto")], now=1.0)
        st.update([(1, "auto")], now=2.0)
        self.assertEqual(st.total["auto"], 1)
        self.assertEqual(st.current["auto"], 1)


if __name__ == "__main__":
    unittest.main()
