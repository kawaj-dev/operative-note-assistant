"""Approved guide catalog; legacy diagrams remain in fields.py for compatibility."""

COMMON = ["finding", "text", "freehand"]
TEMPLATES = {
    "approach": dict(label="ポート・創部", guides=["left_lateral", "supine", "right_lateral"], types=["port", "incision", *COMMON]),
    "lung": dict(label="肺・病変／切除範囲", guides=["right_lung", "left_lung"], types=["lesion", "resection_area", "staple_line", *COMMON]),
    "hilum": dict(label="肺門部・手術操作", guides=["right_hilum", "left_hilum"], types=["staple_line", "energy_device", *COMMON]),
    "blank": dict(label="白紙", guides=["none"], types=["port", "incision", "lesion", "resection_area", "staple_line", "energy_device", *COMMON]),
}
GUIDES = {
    "left_lateral": dict(label="左側臥位", file="position_guide_left_lateral.png"),
    "supine": dict(label="仰臥位", file="position_guide_supine.png"),
    "right_lateral": dict(label="右側臥位", file="position_guide_right_lateral.png"),
    "right_lung": dict(label="右肺", file="lung_guide_right.png"),
    "left_lung": dict(label="左肺", file="lung_guide_left.png"),
    "right_hilum": dict(label="右肺門", file="hilum_guide_right.png"),
    "left_hilum": dict(label="左肺門", file="hilum_guide_left.png"),
    "none": dict(label="ガイドなし", file=None),
}
