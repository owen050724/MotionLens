import argparse
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import cv2

MPLCONFIG_DIR = Path(__file__).resolve().parent / ".mplconfig"
MPLCONFIG_DIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(MPLCONFIG_DIR))

try:
    import mediapipe as mp
except Exception:
    mp = None


DEFAULT_CODECS = ["mp4v", "XVID", "MJPG", "avc1"]
CONTROL_BAR_HEIGHT = 52
BUTTON_HEIGHT = 34
BUTTON_GAP = 8
TARGET_WIDTH = 1920
TARGET_HEIGHT = 1080


class PoseEngine:
    def __init__(self):
        self.available = False
        self.reason = ""
        self.pose = None
        self.pose_connections = None
        self.drawer = None
        self.last_landmarks = None

        if mp is None:
            self.reason = "mediapipe import failed"
            return

        if not hasattr(mp, "solutions") or not hasattr(mp.solutions, "pose"):
            self.reason = "installed mediapipe build has no mp.solutions.pose"
            return

        self.available = True
        self.mp_pose = mp.solutions.pose
        self.pose_connections = self.mp_pose.POSE_CONNECTIONS
        self.drawer = mp.solutions.drawing_utils
        self.pose = self.mp_pose.Pose(
            static_image_mode=False,
            model_complexity=1,
            smooth_landmarks=True,
            enable_segmentation=False,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )

    def infer(self, frame):
        if not self.available or self.pose is None:
            return False

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self.pose.process(rgb)
        self.last_landmarks = results.pose_landmarks
        return self.last_landmarks is not None

    def draw_last(self, frame):
        if self.last_landmarks is None:
            return False

        self.drawer.draw_landmarks(
            frame,
            self.last_landmarks,
            self.pose_connections,
            landmark_drawing_spec=self.drawer.DrawingSpec(color=(0, 255, 255), thickness=2, circle_radius=2),
            connection_drawing_spec=self.drawer.DrawingSpec(color=(0, 255, 0), thickness=2, circle_radius=1),
        )
        return True

    def close(self):
        if self.pose is not None:
            self.pose.close()


def parse_source(value: str):
    try:
        return int(value)
    except ValueError:
        return value


def ensure_fourcc(codec: str) -> str:
    codec = (codec or "mp4v").strip()
    if len(codec) < 4:
        codec = (codec + "mp4v")[:4]
    return codec[:4]


def codec_candidates(primary: str):
    primary = ensure_fourcc(primary)
    return [primary] + [c for c in DEFAULT_CODECS if c.lower() != primary.lower()]


def build_output_path(output_dir: Path, codec: str) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    ext = ".avi" if codec.upper() in {"XVID", "MJPG"} else ".mp4"
    return output_dir / f"recording_{timestamp}_{codec}{ext}"


def apply_filter(frame, mode: str):
    if mode == "gray":
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        return cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    if mode == "edge":
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        edge = cv2.Canny(gray, 100, 200)
        return cv2.cvtColor(edge, cv2.COLOR_GRAY2BGR)
    return frame


def detect_motion(frame, bg_subtractor, min_area: int):
    fg = bg_subtractor.apply(frame)
    _, thresh = cv2.threshold(fg, 200, 255, cv2.THRESH_BINARY)
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, None, iterations=1)
    thresh = cv2.dilate(thresh, None, iterations=2)

    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    boxes = []
    max_area = 0.0
    for contour in contours:
        area = cv2.contourArea(contour)
        if area < min_area:
            continue
        x, y, w, h = cv2.boundingRect(contour)
        boxes.append((x, y, w, h, area))
        if area > max_area:
            max_area = area

    return len(boxes) > 0, max_area, boxes


def create_buttons(frame_width: int):
    specs = [
        ("record", "REC", 70),
        ("filter", "FILTER", 86),
        ("codec", "CODEC", 86),
        ("fps_down", "FPS-", 72),
        ("fps_up", "FPS+", 72),
        ("flip", "FLIP", 72),
        ("motion", "MOTION", 92),
        ("pose", "POSE", 74),
        ("auto", "AUTO", 82),
        ("snapshot", "SHOT", 72),
    ]

    buttons = []
    x = 12
    y = 9
    for key, label, width in specs:
        if x + width > frame_width - 12:
            break
        buttons.append({"key": key, "label": label, "rect": (x, y, width, BUTTON_HEIGHT)})
        x += width + BUTTON_GAP
    return buttons


def point_in_rect(px: int, py: int, rect):
    x, y, w, h = rect
    return x <= px <= x + w and y <= py <= y + h


def map_window_to_frame_coords(window_name: str, x: int, y: int, frame_w: int, frame_h: int):
    """Map click coords from resized HighGUI window space to frame pixel space."""
    try:
        wx, wy, ww, wh = cv2.getWindowImageRect(window_name)
    except Exception:
        return x, y

    if ww <= 0 or wh <= 0:
        return x, y

    # Some backends report callback coords as local image coords, others as window/screen based.
    if 0 <= x < ww and 0 <= y < wh:
        local_x, local_y = x, y
    else:
        local_x, local_y = x - wx, y - wy

    # Clamp inside current displayed image area and scale back to frame coordinates.
    local_x = max(0, min(ww - 1, local_x))
    local_y = max(0, min(wh - 1, local_y))
    fx = int(local_x * frame_w / ww)
    fy = int(local_y * frame_h / wh)
    return fx, fy


def draw_controls(frame, buttons, state):
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 0), (frame.shape[1], CONTROL_BAR_HEIGHT), (20, 22, 28), -1)
    cv2.addWeighted(overlay, 0.55, frame, 0.45, 0, frame)

    active = {
        "record": state["recording"],
        "motion": state["motion_enabled"],
        "pose": state["pose_enabled"],
        "auto": state["auto_motion"],
        "flip": state["flip_horizontal"],
    }

    for btn in buttons:
        x, y, w, h = btn["rect"]
        is_active = active.get(btn["key"], False)
        fill = (50, 60, 75)
        text_color = (235, 235, 235)

        if btn["key"] == "record" and is_active:
            fill = (40, 40, 180)
            text_color = (255, 255, 255)
        elif is_active:
            fill = (80, 140, 60)

        cv2.rectangle(frame, (x, y), (x + w, y + h), fill, -1, cv2.LINE_AA)
        cv2.rectangle(frame, (x, y), (x + w, y + h), (140, 145, 155), 1, cv2.LINE_AA)
        cv2.putText(frame, btn["label"], (x + 10, y + 23), cv2.FONT_HERSHEY_SIMPLEX, 0.55, text_color, 1, cv2.LINE_AA)


def draw_status(frame, recording, record_reason, filter_mode, writer_codec, writer_fps, motion_detected, pose_enabled):
    color = (0, 0, 255) if recording else (0, 255, 255)
    mode = f"RECORD ({record_reason})" if recording else "PREVIEW"
    h, w = frame.shape[:2]
    status = f"{mode} | {w}x{h} | Filter:{filter_mode} | Codec:{writer_codec} | FPS:{writer_fps:.1f}"
    cv2.putText(frame, status, (12, frame.shape[0] - 18), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2, cv2.LINE_AA)

    if motion_detected:
        cv2.putText(frame, "MOTION", (12, CONTROL_BAR_HEIGHT + 28), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 200, 255), 2, cv2.LINE_AA)
    if pose_enabled:
        cv2.putText(frame, "POSE", (120, CONTROL_BAR_HEIGHT + 28), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 255, 120), 2, cv2.LINE_AA)

    if recording:
        cv2.circle(frame, (frame.shape[1] - 24, CONTROL_BAR_HEIGHT + 16), 9, (0, 0, 255), -1)


def main():
    parser = argparse.ArgumentParser(description="Camera-like OpenCV recorder with clickable controls")
    parser.add_argument("--source", default="0", help="Camera index (e.g. 0) or stream URL")
    parser.add_argument("--fps", type=float, default=30.0, help="Initial recording FPS")
    parser.add_argument("--codec", default="mp4v", help="Initial FourCC codec (e.g. mp4v, XVID)")
    parser.add_argument("--output-dir", default="recordings", help="Directory for recorded videos")
    parser.add_argument("--motion-min-area", type=int, default=1200, help="Minimum contour area for motion detection")
    parser.add_argument("--motion-hold-seconds", type=float, default=2.0, help="Auto-record stop delay after motion ends")
    args = parser.parse_args()

    source = parse_source(args.source)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open camera/stream: {source}")

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, TARGET_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, TARGET_HEIGHT)

    ok, first_frame = cap.read()
    if not ok:
        cap.release()
        raise RuntimeError("Failed to read first frame from camera/stream")

    frame_height, frame_width = first_frame.shape[:2]
    print(f"[INFO] Camera resolution: {frame_width}x{frame_height}")

    codecs = codec_candidates(args.codec)
    codec_idx = 0
    writer_codec = codecs[codec_idx]
    writer_fps = max(5.0, min(120.0, args.fps))

    recording = False
    record_reason = "manual"
    writer = None
    writer_path = None

    flip_horizontal = False
    filter_mode = "normal"

    motion_enabled = False
    auto_motion = False
    bg_subtractor = cv2.createBackgroundSubtractorMOG2(history=300, varThreshold=25, detectShadows=True)
    last_motion_time = 0.0

    pose_engine = PoseEngine()
    pose_enabled = False
    pose_warned = False
    print(f"[INFO] Python executable: {sys.executable}")
    if mp is not None:
        print(f"[INFO] mediapipe version: {getattr(mp, '__version__', 'unknown')}")
    if not pose_engine.available:
        print(f"[WARN] Pose engine unavailable: {pose_engine.reason}")

    window_name = "OpenCV Video Recorder"
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)

    buttons = create_buttons(frame_width)
    pending_action = {"value": None}

    def on_mouse(event, x, y, flags, param):
        del flags, param
        if event != cv2.EVENT_LBUTTONDOWN:
            return
        fx, fy = map_window_to_frame_coords(window_name, x, y, frame_width, frame_height)
        for btn in buttons:
            if point_in_rect(fx, fy, btn["rect"]):
                pending_action["value"] = btn["key"]
                break

    cv2.setMouseCallback(window_name, on_mouse)

    def start_recording(reason: str):
        nonlocal writer, writer_path, recording, record_reason
        if writer is not None:
            return
        writer_path = build_output_path(output_dir, writer_codec)
        fourcc = cv2.VideoWriter_fourcc(*ensure_fourcc(writer_codec))
        writer = cv2.VideoWriter(str(writer_path), fourcc, writer_fps, (frame_width, frame_height))
        if not writer.isOpened():
            writer = None
            recording = False
            print(f"[WARN] Failed to start recording with codec={writer_codec}, fps={writer_fps:.1f}")
            return
        recording = True
        record_reason = reason
        print(f"[INFO] Recording started ({reason}): {writer_path}")

    def stop_recording():
        nonlocal writer, recording
        if writer is not None:
            writer.release()
            writer = None
            print(f"[INFO] Recording saved: {writer_path}")
        recording = False

    def cycle_filter():
        nonlocal filter_mode
        order = ["normal", "gray", "edge"]
        idx = (order.index(filter_mode) + 1) % len(order)
        filter_mode = order[idx]

    def cycle_codec():
        nonlocal codec_idx, writer_codec
        if recording:
            print("[INFO] Stop recording first to change codec.")
            return
        codec_idx = (codec_idx + 1) % len(codecs)
        writer_codec = codecs[codec_idx]
        print(f"[INFO] Codec changed: {writer_codec}")

    def adjust_fps(delta: float):
        nonlocal writer_fps
        if recording:
            print("[INFO] Stop recording first to change FPS.")
            return
        writer_fps = max(5.0, min(120.0, writer_fps + delta))
        print(f"[INFO] FPS changed: {writer_fps:.1f}")

    def handle_action(action_key: str, current_display_frame):
        nonlocal flip_horizontal, motion_enabled, auto_motion, bg_subtractor, pose_enabled, pose_warned

        if action_key == "record":
            if recording:
                stop_recording()
            else:
                start_recording("manual")
        elif action_key == "filter":
            cycle_filter()
        elif action_key == "codec":
            cycle_codec()
        elif action_key == "fps_up":
            adjust_fps(5.0)
        elif action_key == "fps_down":
            adjust_fps(-5.0)
        elif action_key == "flip":
            flip_horizontal = not flip_horizontal
        elif action_key == "motion":
            motion_enabled = not motion_enabled
            print(f"[INFO] Motion detection: {'ON' if motion_enabled else 'OFF'}")
            if motion_enabled:
                bg_subtractor = cv2.createBackgroundSubtractorMOG2(history=300, varThreshold=25, detectShadows=True)
        elif action_key == "auto":
            auto_motion = not auto_motion
            if auto_motion:
                motion_enabled = True
                bg_subtractor = cv2.createBackgroundSubtractorMOG2(history=300, varThreshold=25, detectShadows=True)
            print(f"[INFO] Auto motion recording: {'ON' if auto_motion else 'OFF'}")
        elif action_key == "pose":
            if not pose_engine.available:
                if not pose_warned:
                    print(f"[WARN] Pose unavailable: {pose_engine.reason}")
                    pose_warned = True
                pose_enabled = False
            else:
                pose_enabled = not pose_enabled
                print(f"[INFO] Pose detection: {'ON' if pose_enabled else 'OFF'}")
        elif action_key == "snapshot":
            shot_path = output_dir / f"snapshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            cv2.imwrite(str(shot_path), current_display_frame)
            print(f"[INFO] Snapshot saved: {shot_path}")

    running = True
    display_frame = first_frame
    while running:
        ok, frame = cap.read()
        if not ok:
            break

        if flip_horizontal:
            frame = cv2.flip(frame, 1)

        motion_detected = False
        motion_boxes = []
        if motion_enabled:
            motion_detected, _, motion_boxes = detect_motion(frame, bg_subtractor, args.motion_min_area)
            if motion_detected:
                last_motion_time = time.time()

        pose_found = False
        if pose_enabled:
            pose_found = pose_engine.infer(frame)

        display_frame = apply_filter(frame, filter_mode)

        if motion_enabled:
            for x, y, w, h, _ in motion_boxes:
                cv2.rectangle(display_frame, (x, y), (x + w, y + h), (0, 180, 255), 2)

        if auto_motion:
            if motion_detected and not recording:
                start_recording("motion")
            if recording and record_reason == "motion" and (time.time() - last_motion_time) > args.motion_hold_seconds:
                stop_recording()

        if pose_enabled:
            pose_engine.draw_last(display_frame)
            if not pose_found:
                cv2.putText(
                    display_frame,
                    "POSE: no person detected",
                    (240, CONTROL_BAR_HEIGHT + 28),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.62,
                    (80, 230, 255),
                    2,
                    cv2.LINE_AA,
                )

        if recording and writer is not None:
            writer.write(display_frame)

        draw_controls(
            display_frame,
            buttons,
            {
                "recording": recording,
                "motion_enabled": motion_enabled,
                "pose_enabled": pose_enabled,
                "auto_motion": auto_motion,
                "flip_horizontal": flip_horizontal,
            },
        )

        draw_status(display_frame, recording, record_reason, filter_mode, writer_codec, writer_fps, motion_detected, pose_enabled)
        cv2.imshow(window_name, display_frame)

        if pending_action["value"] is not None:
            action = pending_action["value"]
            pending_action["value"] = None
            handle_action(action, display_frame)

        key = cv2.waitKey(1) & 0xFF
        if key == 27:
            running = False
        elif key == 32:
            handle_action("record", display_frame)
        elif key == ord("c") or key == ord("C"):
            handle_action("codec", display_frame)
        elif key == ord("+") or key == ord("="):
            handle_action("fps_up", display_frame)
        elif key == ord("-") or key == ord("_"):
            handle_action("fps_down", display_frame)
        elif key == ord("1"):
            filter_mode = "normal"
        elif key == ord("2"):
            filter_mode = "gray"
        elif key == ord("3"):
            filter_mode = "edge"
        elif key == ord("f") or key == ord("F"):
            handle_action("flip", display_frame)
        elif key == ord("m") or key == ord("M"):
            handle_action("motion", display_frame)
        elif key == ord("p") or key == ord("P"):
            handle_action("pose", display_frame)
        elif key == ord("a") or key == ord("A"):
            handle_action("auto", display_frame)
        elif key == ord("s") or key == ord("S"):
            handle_action("snapshot", display_frame)

    if writer is not None:
        writer.release()
        print(f"[INFO] Recording saved: {writer_path}")

    pose_engine.close()
    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()

