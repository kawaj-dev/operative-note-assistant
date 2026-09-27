import math
import re
from datetime import date

from fields import DIAGRAMS, FIELDS, LEGACY_NARRATIVE_FIELDS, field_visible, merge_narrative
from diagram_specs import TEMPLATES


class ValidationError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise ValidationError(message)


def number(value, low, high):
    return type(value) in (int, float) and low <= value <= high and math.isfinite(value)


def duration_minutes(start, end):
    if not start and not end:
        return None
    require(bool(start and end), "開始時刻と終了時刻は両方入力してください。")
    require(all(re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", t) for t in (start, end)), "時刻はHH:MM形式で入力してください。")
    values = [int(t[:2]) * 60 + int(t[3:]) for t in (start, end)]
    return (values[1] - values[0]) % 1440


def validate_payload(payload, status="completed"):
    require(isinstance(payload, dict) and {"note", "diagrams"} <= set(payload) <= {"note", "diagrams", "status", "revision", "step", "creation_key"}, "保存データの形式が不正です。")
    require(status in ("draft", "completed"), "保存状態が不正です。")
    creation_key = payload.get("creation_key")
    require(creation_key is None or (isinstance(creation_key, str) and bool(re.fullmatch(r"[a-f0-9]{32}", creation_key))), "新規保存キーが不正です。")
    step = payload.get("step", 0)
    require(type(step) is int and 0 <= step <= 9, "入力ステップが不正です。")
    raw = payload["note"]
    require(isinstance(raw, dict) and set(raw) <= {f["name"] for f in FIELDS + LEGACY_NARRATIVE_FIELDS}, "入力項目が不正です。")
    note = {}
    for f in FIELDS + LEGACY_NARRATIVE_FIELDS:
        if f["kind"] in ("repeat", "checks"):
            value = raw.get(f["name"], [])
            require(isinstance(value, list) and len(value) <= len(f["options"]), f'{f["label"]}の件数・形式が不正です。')
            require(all(isinstance(v, str) and (v in f["options"] or (f["kind"] == "repeat" and v == "")) for v in value), f'{f["label"]}の選択肢が不正です。')
            selected = [v for v in value if v]
            require(len(selected) == len(set(selected)), f'{f["label"]}が重複しています。')
            note[f["name"]] = value
            continue
        value = raw.get(f["name"], "")
        require(isinstance(value, str) and len(value) <= (10000 if f["name"] == "narrative" else 4000 if f["kind"] == "textarea" else 200), f'{f["label"]}の型または長さが不正です。')
        value = value if f["name"] in ("narrative", "findings", "course") else value.strip()
        require(not f["options"] or not value or value in f["options"], f'{f["label"]}の選択肢が不正です。')
        note[f["name"]] = value
    if not raw.get("narrative") and (raw.get("findings") or raw.get("course")):
        note["narrative"] = merge_narrative(note)
    if status == "completed":
        missing = [f["label"] for f in FIELDS if f["required"] and field_visible(f, note) and not note[f["name"]]]
        require(not missing, "完成に必要な項目が未入力です：" + "、".join(missing))
    require(not note["case_id"] or bool(re.fullmatch(r"DEMO-\d{3}", note["case_id"], re.ASCII)), "症例IDはDEMO-001のようにDEMO-と半角数字3桁で入力してください。")
    try:
        if note["operation_date"]:
            require(bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", note["operation_date"])), "手術日が不正です。")
            date.fromisoformat(note["operation_date"])
    except ValueError:
        raise ValidationError("手術日が不正です。") from None
    require(not note["blood_loss"] or bool(re.fullmatch(r"\d{1,6}(?:\.\d)?", note["blood_loss"], re.ASCII)), "出血量は0以上の数値（整数6桁、小数1桁以内）で入力してください。")
    for key in ("start_time", "end_time"):
        require(not note[key] or bool(re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", note[key])), "時刻はHH:MM形式で入力してください。")
    note["duration_minutes"] = None if status == "draft" and not (note["start_time"] and note["end_time"]) else duration_minutes(note["start_time"], note["end_time"])
    if status == "completed":
        # Preserve conditional work while drafting; omit inactive values on completion.
        for f in FIELDS + LEGACY_NARRATIVE_FIELDS:
            if not field_visible(f, note):
                note[f["name"]] = [] if f["kind"] == "checks" else ""
    validate_diagrams(payload["diagrams"], note["position"])
    return note, payload["diagrams"]


def validate_legacy_diagrams(diagrams, position):

    seen = set()
    for diagram in diagrams:
        require(isinstance(diagram, dict) and set(diagram) == {"diagram_type", "base_template", "position", "layers", "base_transform", "next_port", "next_sequence", "objects"}, "図の構造が不正です。")
        kind = diagram["diagram_type"]
        require(isinstance(kind, str) and kind in DIAGRAMS and kind not in seen, "図種が不正または重複しています。")
        seen.add(kind)
        spec = DIAGRAMS[kind]
        require(diagram["base_template"] == f"{kind}-placeholder-v1", "ベーステンプレートが不正です。")
        require(diagram["position"] == (position if kind == "approach" else ""), "図と基本情報の体位が一致しません。")
        layers = diagram["layers"]
        require(isinstance(layers, dict) and set(layers) == set(spec["layers"]), "レイヤーが不正です。")
        for state in layers.values():
            require(isinstance(state, dict) and set(state) == {"visible", "locked"} and all(type(v) is bool for v in state.values()), "レイヤー状態が不正です。")
        transform = diagram["base_transform"]
        require(isinstance(transform, dict) and set(transform) == {"x", "y", "rotation"}, "ベース位置が不正です。")
        require(number(transform["x"], -800, 800) and number(transform["y"], -500, 500) and number(transform["rotation"], -360, 360), "ベース座標が不正です。")
        for counter in ("next_port", "next_sequence"):
            require(type(diagram[counter]) is int and 1 <= diagram[counter] <= 1000000, "採番状態が不正です。")
        objects = diagram["objects"]
        require(isinstance(objects, list) and len(objects) <= 200, "各図のオブジェクト数は200個以内です。")
        ids, ports, sequences = set(), set(), set()
        for obj in objects:
            require(isinstance(obj, dict), "オブジェクトが不正です。")
            typ = obj.get("type")
            require(isinstance(typ, str) and typ in spec["types"], "許可されていないdiagram object typeです。")
            extras = {"PORT": {"number"}, "TUMOR": {"size", "note"}, "STAPLER": {"sequence"}, "ENERGY_DEVICE": {"sequence"}, "TEXT": {"text"}, "FREEHAND": {"points"}, "INCISION": {"points"}, "DIVISION_LINE": {"points"}, "ENCLOSURE": {"points"}}[typ]
            require(set(obj) == {"id", "type", "x", "y", "rotation"} | extras, "オブジェクトの項目が不正です。")
            oid = obj["id"]
            require(isinstance(oid, str) and bool(re.fullmatch(r"[A-Za-z0-9-]{1,64}", oid)) and oid not in ids, "オブジェクトIDが不正です。")
            ids.add(oid)
            require(number(obj["x"], 0, 800) and number(obj["y"], 0, 500) and number(obj["rotation"], -360, 360), "オブジェクト座標が不正です。")
            if typ == "TUMOR":
                require(number(obj["size"], 4, 120) and isinstance(obj["note"], str) and len(obj["note"]) <= 500, "腫瘍のサイズ・注記が不正です。")
            if typ == "TEXT":
                require(isinstance(obj["text"], str) and 1 <= len(obj["text"]) <= 500, "テキストは1〜500文字です。")
            if "points" in extras:
                points = obj["points"]
                require(isinstance(points, list) and 2 <= len(points) <= 2000, "描画点数が不正です。")
                require(all(isinstance(p, list) and len(p) == 2 and number(p[0], -800, 800) and number(p[1], -500, 500) for p in points), "描画座標が不正です。")
            for key, used, counter in (("number", ports, "next_port"), ("sequence", sequences, "next_sequence")):
                if key in extras:
                    value = obj[key]
                    require(type(value) is int and 0 < value < diagram[counter] and value not in used, "採番が不正または重複しています。")
                    used.add(value)


def validate_diagrams(diagrams, position):
    require(isinstance(diagrams, list) and len(diagrams) <= 30, "手術図は30枚以内です。")
    legacy = []
    for index, diagram in enumerate(diagrams):
        require(isinstance(diagram, dict), "図の構造が不正です。")
        if "version" in diagram:
            validate_new_diagram(diagram, index)
        else:
            legacy.append(diagram)
    validate_legacy_diagrams(legacy, position)


def validate_new_diagram(diagram, index):
    require(set(diagram) == {"version", "diagram_type", "base_template", "guide_type", "guide_visible", "order", "next_port", "objects"}, "図の項目が不正です。")
    kind = diagram["diagram_type"]
    require(type(diagram["version"]) is int and diagram["version"] == 2 and isinstance(kind, str) and kind in TEMPLATES, "図種が不正です。")
    require(diagram["base_template"] == "guide-v2" and diagram["guide_type"] in TEMPLATES[kind]["guides"], "ガイドが不正です。")
    require(type(diagram["guide_visible"]) is bool and (kind != "blank" or not diagram["guide_visible"]), "ガイド表示状態が不正です。")
    require(type(diagram["order"]) is int and diagram["order"] == index, "図の順序が不正です。")
    require(type(diagram["next_port"]) is int and 1 <= diagram["next_port"] <= 1000000, "採番状態が不正です。")
    require(isinstance(diagram["objects"], list) and len(diagram["objects"]) <= 200, "各図のオブジェクト数は200個以内です。")
    ids, ports = set(), set()
    extras = {"port": {"x", "y", "number"}, "incision": {"x1", "y1", "x2", "y2"}, "lesion": {"x", "y", "size", "note"}, "resection_area": {"points"}, "staple_line": {"x1", "y1", "x2", "y2"}, "energy_device": {"x", "y", "device_type", "note"}, "finding": {"target_x", "target_y", "label_x", "label_y", "text"}, "text": {"x", "y", "text"}, "freehand": {"points"}}
    for obj in diagram["objects"]:
        require(isinstance(obj, dict), "オブジェクトが不正です。")
        typ = obj.get("type")
        require(isinstance(typ, str) and typ in TEMPLATES[kind]["types"], "許可されていないdiagram object typeです。")
        optional = {"rotation", "scale"} if typ in ("port", "lesion", "energy_device", "text", "resection_area", "freehand") else set()
        if typ == "freehand":
            optional |= {"stroke_color", "stroke_width"}
        required = {"id", "type"} | extras[typ]
        require(required <= set(obj) <= required | optional, "オブジェクトの項目が不正です。")
        if "rotation" in obj:
            require(number(obj["rotation"], -360, 360), "回転角が不正です。")
        if "scale" in obj:
            require(number(obj["scale"], 0.25, 4), "拡大率が不正です。")
        if "stroke_color" in obj:
            require(isinstance(obj["stroke_color"], str) and obj["stroke_color"] in ("#222222", "#b42318", "#175cd3", "#167044"), "ペンの色が不正です。")
        if "stroke_width" in obj:
            require(type(obj["stroke_width"]) is int and obj["stroke_width"] in (2, 4, 8), "ペンの太さが不正です。")
        oid = obj["id"]
        require(isinstance(oid, str) and bool(re.fullmatch(r"[A-Za-z0-9-]{1,64}", oid)) and oid not in ids, "オブジェクトIDが不正です。")
        ids.add(oid)
        for key in extras[typ]:
            if key in {"x", "x1", "x2", "target_x", "label_x", "y", "y1", "y2", "target_y", "label_y"}:
                require(number(obj[key], 0, 500 if "y" in key else 800), "オブジェクト座標が不正です。")
        for key in ("text", "note"):
            if key in obj:
                require(isinstance(obj[key], str) and len(obj[key]) <= 500 and (key != "text" or bool(obj[key].strip())), "文章は1〜500文字（メモは空欄可）です。")
        if typ == "port":
            require(type(obj["number"]) is int and 0 < obj["number"] < diagram["next_port"] and obj["number"] not in ports, "ポート番号が不正です。")
            ports.add(obj["number"])
        if typ == "lesion":
            require(number(obj["size"], 4, 120), "病変サイズが不正です。")
        if typ == "energy_device":
            require(obj["device_type"] in ("unspecified", "ultrasonic", "bipolar", "other"), "デバイス種類が不正です。")
        if "points" in obj:
            points = obj["points"]
            require(isinstance(points, list) and (3 if typ == "resection_area" else 2) <= len(points) <= 2000, "描画点数が不正です。")
            require(all(isinstance(p, list) and len(p) == 2 and number(p[0], 0, 800) and number(p[1], 0, 500) for p in points), "描画座標が不正です。")
