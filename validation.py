import math
import re
from datetime import date

from fields import DIAGRAMS, FIELDS, field_visible


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
    require(isinstance(raw, dict) and set(raw) <= {f["name"] for f in FIELDS}, "入力項目が不正です。")
    note = {}
    for f in FIELDS:
        if f["kind"] in ("repeat", "checks"):
            value = raw.get(f["name"], [])
            require(isinstance(value, list) and len(value) <= len(f["options"]), f'{f["label"]}の件数・形式が不正です。')
            require(all(isinstance(v, str) and (v in f["options"] or (f["kind"] == "repeat" and v == "")) for v in value), f'{f["label"]}の選択肢が不正です。')
            selected = [v for v in value if v]
            require(len(selected) == len(set(selected)), f'{f["label"]}が重複しています。')
            note[f["name"]] = value
            continue
        value = raw.get(f["name"], "")
        require(isinstance(value, str) and len(value) <= (4000 if f["kind"] == "textarea" else 200), f'{f["label"]}の型または長さが不正です。')
        value = value.strip()
        require(not f["options"] or not value or value in f["options"], f'{f["label"]}の選択肢が不正です。')
        note[f["name"]] = value
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
        for f in FIELDS:
            if not field_visible(f, note):
                note[f["name"]] = [] if f["kind"] == "checks" else ""
    validate_diagrams(payload["diagrams"], note["position"])
    return note, payload["diagrams"]


def validate_diagrams(diagrams, position):
    require(isinstance(diagrams, list) and len(diagrams) == 3, "手術図は3種類必要です。")
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
