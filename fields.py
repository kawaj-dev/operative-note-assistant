"""The guide and validation share one small field catalog."""


def field(name, label, kind="text", options=None, required=False, when=None):
    return dict(name=name, label=label, kind=kind, options=options, required=required, when=when or {})


POSITIONS = ["左側臥位", "右側臥位", "仰臥位"]
OTHER = "その他（自由入力）"
LOBECTOMY = "肺葉切除術（Lobectomy）"
SEGMENTECTOMY = "区域切除術（Segmentectomy）"
PROCEDURES = [LOBECTOMY, SEGMENTECTOMY, "部分切除術 / 楔状切除術（Wedge Resection）", "肺全摘術（Pneumonectomy）", OTHER]
STATIONS = ["#2R　上気管傍リンパ節", "#4R　下気管傍リンパ節", "#7　気管分岐下リンパ節", "#10　肺門リンパ節", "#11　葉間リンパ節", "#12　区域間リンパ節", "#13　亜区域間リンパ節"]
STEPS = [
    ("基本情報", "この記録は完全架空のデモ症例です。必須項目は * で示しています。", [
        field("case_id", "症例ID", required=True),
        field("operation_date", "手術日", "date", required=True),
        field("pre_diagnosis", "術前診断", required=True),
        field("post_diagnosis", "術後診断"),
        field("start_time", "手術開始時刻", "time"),
        field("end_time", "手術終了時刻", "time"),
    ]),
    ("手術担当", "すべて架空の役割名です。実在人物の名前は入力しません。", [
        field("surgeon", "術者", "repeat", ["架空術者A", "架空術者B"]),
        field("assistant", "助手", "repeat", ["架空助手A", "架空助手B"]),
        field("anesthesia", "麻酔", "select", ["架空麻酔担当A", "架空麻酔担当B"]),
    ]),
    ("アプローチ", "方法と補足を記録します。位置は手術図にも記入できます。", [
        field("approach", "アプローチ方法", "select", ["胸腔鏡", "ロボット支援", "開胸", "その他"]),
        field("approach_note", "アプローチの補足", "textarea"),
    ]),
    ("術式詳細", "術式に応じて必要な内容を記録します。処理方法の推奨・自動決定は行いません。", [
        field("procedure", "術式", "select", PROCEDURES, True),
        field("procedure_other", "その他の術式", required=True, when={"procedure": OTHER}),
        field("position", "体位", "select", POSITIONS, True),
        field("lobe", "切除肺葉", "select", ["右上葉", "右中葉", "右下葉", "左上葉", "左下葉", OTHER], True, {"procedure": LOBECTOMY}),
        field("lobe_other", "その他の切除肺葉", required=True, when={"procedure": LOBECTOMY, "lobe": OTHER}),
        field("vein", "肺静脈の処理", "textarea", when={"procedure": LOBECTOMY}),
        field("artery", "肺動脈の処理", "textarea", when={"procedure": LOBECTOMY}),
        field("bronchus", "気管支の処理", "textarea", when={"procedure": LOBECTOMY}),
        field("segment_side", "区域切除の対象側", "select", ["右肺", "左肺"], when={"procedure": SEGMENTECTOMY}),
        field("segment_target", "対象区域名（自由入力・任意）", when={"procedure": SEGMENTECTOMY}),
        field("resection_note", "術式詳細・補足", "textarea"),
    ]),
    ("リンパ節郭清", "実施有無を選び、必要に応じて郭清度・リンパ節を記録します。", [
        field("lymph_done", "実施有無", "select", ["あり", "なし"]),
        field("lymph_grade", "郭清度", "select", ["ND0", "ND1a", "ND1b", "ND2a-1", "ND2a-2", "ND2b", "ND3", OTHER], when={"lymph_done": "あり"}),
        field("lymph_grade_other", "その他の郭清度", required=True, when={"lymph_done": "あり", "lymph_grade": OTHER}),
        field("lymph_stations", "郭清・摘出リンパ節", "checks", STATIONS, when={"lymph_done": "あり"}),
        field("lymph_note", "郭清の補足", "textarea", when={"lymph_done": "あり"}),
    ]),
    ("合併切除", "合併切除がある場合に、箇所を自由記載します。", [
        field("combined_done", "合併切除の有無", "select", ["あり", "なし"]),
        field("combined_site", "合併切除箇所", "textarea", when={"combined_done": "あり"}),
    ]),
    ("出血", "出血量と輸血を記録します。", [
        field("blood_loss", "出血量（mL）", "number"),
        field("transfusion", "輸血", "select", ["なし", "あり"]),
    ]),
    ("手術図", "症例に必要な手術図を追加してください。複数追加でき、手術図なしでも進めます。", []),
    ("手術所見・手術経過", "構造化項目や手術図だけでは表せない、症例ごとの手術所見・手術経過を記録します。", [
        field("narrative", "手術所見・手術経過", "textarea"),
    ]),
    ("内容確認・保存", "必要な項目を確認して完成保存します。下書きは各ステップから保存・再開できます。", []),
]
FIELDS = [item for _, _, items in STEPS for item in items]
LEGACY_NARRATIVE_FIELDS = [field("findings", "手術所見（旧入力）", "textarea"), field("course", "手術経過（旧入力）", "textarea")]


def field_visible(item, note):
    return all(note.get(key) == value for key, value in item["when"].items())


def blank_note():
    return {item["name"]: ([""] if item["kind"] == "repeat" else [] if item["kind"] == "checks" else "") for item in FIELDS}


def merge_narrative(data):
    """Keep both legacy texts, including their original whitespace and headings."""
    return "\n\n".join(label + "\n" + data[key] for key, label in (("findings", "【手術所見】"), ("course", "【手術経過】")) if data.get(key))

def normalize_note(data):
    """Read legacy completed records without rewriting or discarding their contents."""
    note = {**blank_note(), **data}
    if "narrative" not in data:
        note["narrative"] = merge_narrative(data)
    for name in ("surgeon", "assistant"):
        if isinstance(note[name], str):
            note[name] = ["架空助手A", "架空助手B"] if note[name] == "架空助手A・B" else [note[name]]
    if note["procedure"] == "右上葉切除術":
        note["procedure"] = LOBECTOMY
    note["lymph_done"] = {"実施": "あり", "未実施": "なし"}.get(note["lymph_done"], note["lymph_done"])
    return note


def display_value(value):
    return "、".join(v for v in value if v) if isinstance(value, list) else value


LEGACY_FIELDS = {"lymph_extent": "郭清範囲（旧入力）", "hemostasis": "止血確認", "air_leak": "air leak確認", "additional": "追加処置", "check_note": "確認の補足", "drain": "ドレーン", "ending_note": "手術終了の補足"}

DIAGRAMS = {
    "approach": {"label": "体位・アプローチ図", "layers": {"base": "体位ベース", "access": "ポート・切開", "annotation": "描画・注釈"}, "types": ["PORT", "INCISION", "FREEHAND", "TEXT"]},
    "lung": {"label": "肺・創部図", "layers": {"base": "解剖ベース", "lesion": "病変", "annotation": "描画・注釈"}, "types": ["TUMOR", "DIVISION_LINE", "ENCLOSURE", "FREEHAND", "TEXT"]},
    "hilum": {"label": "胸腔内・手術操作図", "layers": {"base": "解剖ベース", "lesion": "病変", "device": "手術デバイス", "annotation": "描画・注釈"}, "types": ["TUMOR", "STAPLER", "ENERGY_DEVICE", "DIVISION_LINE", "ENCLOSURE", "FREEHAND", "TEXT"]},
}
OBJECT_LAYERS = {"PORT": "access", "INCISION": "access", "TUMOR": "lesion", "STAPLER": "device", "ENERGY_DEVICE": "device", "DIVISION_LINE": "annotation", "ENCLOSURE": "annotation", "FREEHAND": "annotation", "TEXT": "annotation"}


def empty_diagrams(position="左側臥位"):
    return [dict(diagram_type=key, base_template=f"{key}-placeholder-v1", position=position if key == "approach" else "", layers={name: dict(visible=True, locked=name == "base") for name in spec["layers"]}, base_transform=dict(x=0, y=0, rotation=0), next_port=1, next_sequence=1, objects=[]) for key, spec in DIAGRAMS.items()]


def demo_payload():
    note = blank_note()
    note.update(case_id="DEMO-001", operation_date="2026-01-01", pre_diagnosis="右上葉肺癌（架空）", post_diagnosis="右上葉肺癌（架空）", procedure="右上葉切除術", lobe="右上葉", position="左側臥位", surgeon="架空術者A", assistant="架空助手A", anesthesia="架空麻酔担当A", start_time="09:00", end_time="11:30", findings="機能確認のためにゼロから作成した架空症例。医学的な詳細は未記録。", course="ガイド入力と手術図保存の機能検証用。")
    note.pop("narrative", None)
    note = normalize_note(note)
    note.pop("narrative", None)  # Keep the legacy seed payload useful for compatibility tests.
    diagrams = empty_diagrams()
    diagrams[0]["objects"] = [dict(id="demo-port", type="PORT", x=280, y=230, rotation=0, number=1)]
    diagrams[0]["next_port"] = 2
    diagrams[1]["objects"] = [dict(id="demo-tumor", type="TUMOR", x=350, y=180, rotation=0, size=24, note="配置テスト用・解剖学的意味なし")]
    diagrams[2]["objects"] = [dict(id="demo-stapler", type="STAPLER", x=420, y=250, rotation=35, sequence=1)]
    diagrams[2]["next_sequence"] = 2
    return dict(note=note, diagrams=diagrams)
