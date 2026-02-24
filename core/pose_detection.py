import cv2
import mediapipe as mp
from typing import Optional, List, Tuple


class PoseDetector:
    def __init__(self):
        self.mp_pose = mp.solutions.pose
        self.engine  = self.mp_pose.Pose(
            static_image_mode=True,
            model_complexity=2,
            enable_segmentation=False,
        )

    def detect_landmarks(self, image_path: str) -> Optional[Tuple[List, int, int]]:
        img = cv2.imread(image_path)
        if img is None:
            return None

        h, w    = img.shape[:2]
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        results = self.engine.process(img_rgb)

        if not results.pose_landmarks:
            return None

        landmarks = [
            (int(lm.x * w), int(lm.y * h))
            for lm in results.pose_landmarks.landmark
        ]
        return landmarks, w, h

    def compute_sequential_boxes(self, image_path: str) -> Optional[dict]:
        pose_data = self.detect_landmarks(image_path)
        if not pose_data:
            return None

        landmarks, w, h = pose_data

        nose       = landmarks[0]
        l_shoulder = landmarks[11]
        r_shoulder = landmarks[12]
        l_hip      = landmarks[23]
        r_hip      = landmarks[24]
        l_knee     = landmarks[25]
        r_knee     = landmarks[26]

        xs    = [pt[0] for pt in landmarks]
        min_x = max(0, min(xs))
        max_x = min(w, max(xs))
        pad_x = int((max_x - min_x) * 0.1)
        min_x = max(0, min_x - pad_x)
        max_x = min(w, max_x + pad_x)

        raw_top     = min(pt[1] for pt in landmarks)
        bottom_full = max(pt[1] for pt in landmarks)

        shoulder_width = abs(l_shoulder[0] - r_shoulder[0])
        head_padding   = int(shoulder_width * 0.75)
        top_full       = max(0, raw_top - head_padding)
        body_height    = bottom_full - top_full

        knee_y       = max(l_knee[1], r_knee[1])
        thigh_adjust = int(body_height * 0.10)
        bottom_thigh = max(top_full, knee_y - thigh_adjust)

        hip_y        = max(l_hip[1], r_hip[1])
        torso_adjust = int(body_height * 0.08)
        bottom_torso = max(top_full, hip_y - torso_adjust)

        face_size   = int(shoulder_width * 1.2)
        half        = face_size // 2
        face_left   = max(0, nose[0] - half)
        face_right  = min(w, nose[0] + half)
        face_top    = max(0, nose[1] - half)
        face_bottom = min(h, nose[1] + half)

        return {
            "full":  (min_x, top_full, max_x, bottom_full),
            "thigh": (min_x, top_full, max_x, bottom_thigh),
            "torso": (min_x, top_full, max_x, bottom_torso),
            "face":  (face_left, face_top, face_right, face_bottom),
        }
