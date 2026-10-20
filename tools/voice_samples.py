"""목소리 고르기용 샘플: VOICEVOX 엔진(로컬 실행)으로 같은 문장을 여러 목소리로 읽는다."""
import json, os, subprocess, sys, time, urllib.parse, urllib.request

API = "http://127.0.0.1:50021"
TEXT = "いつもお世話になっております。ご確認のほど、よろしくお願いいたします。"
WANT = [  # (파일 이름, 캐릭터, 스타일, 높이 조정, 억양)
    ("F1_kyushu_sora", "九州そら", "ノーマル", 0.0, 1.0),
    ("F2_shikoku_metan_low", "四国めたん", "ノーマル", -0.05, 1.0),
    ("F3_namine_ritsu", "波音リツ", "ノーマル", 0.0, 1.0),
    ("F4_whitecul", "WhiteCUL", "ノーマル", -0.02, 1.0),
    ("F5_no7_low", "No.7", "ノーマル", -0.03, 1.05),
    ("F6_himari_up", "冥鳴ひまり", "ノーマル", 0.04, 1.1),
    ("F7_yogatari_tobari", "夜語トバリ", "ノーマル", 0.0, 1.0),
    ("F8_kurosawa_saeha", "黒沢冴白", "ノーマル", 0.0, 1.0),
]

def call(path, data=None, ctype="application/json"):
    req = urllib.request.Request(API + path, data=data, method="POST" if data is not None or "audio_query" in path or "synthesis" in path else "GET")
    if data is not None: req.add_header("Content-Type", ctype)
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()

for _ in range(90):
    try: call("/version"); break
    except Exception: time.sleep(2)
speakers = json.loads(call("/speakers"))
ids = {(s["name"], st["name"]): st["id"] for s in speakers for st in s["styles"]}
os.makedirs("samples", exist_ok=True)
for f in os.listdir("samples"):
    if f.endswith(".mp3"): os.remove(os.path.join("samples", f))
report = {"available": sorted(f"{a}/{b}" for a, b in ids)}
for fname, who, style, pitch, inton in WANT:
    sid = ids.get((who, style))
    if sid is None:
        report[fname] = "missing"; continue
    q = json.loads(call(f"/audio_query?text={urllib.parse.quote(TEXT)}&speaker={sid}", b""))
    q.update({"intonationScale": inton, "pitchScale": pitch, "prePhonemeLength": 0.1, "postPhonemeLength": 0.1})
    wav = call(f"/synthesis?speaker={sid}", json.dumps(q).encode())
    open(f"samples/{fname}.wav", "wb").write(wav)
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", f"samples/{fname}.wav", "-ac", "1", "-b:a", "64k", f"samples/{fname}.mp3"], check=True)
    os.remove(f"samples/{fname}.wav")
    report[fname] = f"{who}/{style} id={sid}"
json.dump(report, open("samples/report.json", "w", encoding="utf8"), ensure_ascii=False, indent=1)
print(json.dumps(report, ensure_ascii=False)[:2000])
