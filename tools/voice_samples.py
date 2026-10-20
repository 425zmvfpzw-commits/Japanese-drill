"""목소리 고르기용 샘플: VOICEVOX 엔진(로컬 실행)으로 같은 문장을 여러 목소리로 읽는다."""
import json, os, subprocess, sys, time, urllib.parse, urllib.request

API = "http://127.0.0.1:50021"
TEXT = "いつもお世話になっております。ご確認のほど、よろしくお願いいたします。"
WANT = [  # (파일 이름, 캐릭터, 스타일)
    ("A_female_announce", "No.7", "アナウンス"),
    ("B_female_normal", "No.7", "ノーマル"),
    ("C_female_calm", "冥鳴ひまり", "ノーマル"),
    ("D_male_calm", "青山龍星", "ノーマル"),
    ("E_male_normal", "玄野武宏", "ノーマル"),
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
report = {"available": sorted(f"{a}/{b}" for a, b in ids)}
for fname, who, style in WANT:
    sid = ids.get((who, style))
    if sid is None:
        report[fname] = "missing"; continue
    q = json.loads(call(f"/audio_query?text={urllib.parse.quote(TEXT)}&speaker={sid}", b""))
    q.update({"intonationScale": 0.9, "prePhonemeLength": 0.1, "postPhonemeLength": 0.1})
    wav = call(f"/synthesis?speaker={sid}", json.dumps(q).encode())
    open(f"samples/{fname}.wav", "wb").write(wav)
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", f"samples/{fname}.wav", "-ac", "1", "-b:a", "64k", f"samples/{fname}.mp3"], check=True)
    os.remove(f"samples/{fname}.wav")
    report[fname] = f"{who}/{style} id={sid}"
json.dump(report, open("samples/report.json", "w", encoding="utf8"), ensure_ascii=False, indent=1)
print(json.dumps(report, ensure_ascii=False)[:2000])
