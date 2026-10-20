"""문장마다 리스닝 드릴 음성 파일을 목소리별로 만든다 (VOICEVOX 엔진, 로컬 실행).

cards.json 의 일본어 문장 하나당 audio/<목소리>/<해시>.mp3 하나:
같은 문장을 보통 속도로 10번 이어 붙인다. (1배/1.5배는 앱에서 재생 속도로 고른다)
audio/index.json 에 목소리 목록과, 각 반복이 시작되는 시각(초)을 적는다.
"""
import hashlib, json, os, subprocess, sys, tempfile, time, urllib.parse, urllib.request

API = "http://127.0.0.1:50021"
N, GAP, LEAD = 10, 0.7, 0.25
FORMAT = 4   # 파일 형식이 바뀌면 숫자를 올려서 전부 다시 만든다
VOICES = {   # id: (캐릭터, 스타일, 높이, 억양, 앱 표시 이름)
    "sora":     ("九州そら",  "ノーマル", 0.0,   1.0, "소라 · 또렷한 언니 톤"),
    "ritsu":    ("波音リツ",  "ノーマル", 0.0,   1.0, "리츠 · 쿨하고 담백한 톤"),
    "whitecul": ("WhiteCUL", "ノーマル", -0.02, 1.0, "화이트컬 · 부드럽고 차분한 톤"),
    "tobari":   ("夜語トバリ", "ノーマル", 0.0,   1.0, "토바리 · 차분한 톤"),
}

def call(path, data=None):
    req = urllib.request.Request(API + path, data=data, method="GET" if data is None else "POST")
    if data is not None: req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=180) as r:
        return r.read()

def key(t):
    return hashlib.sha256(t.strip().encode("utf8")).hexdigest()[:16]

for _ in range(120):
    try: call("/version"); break
    except Exception: time.sleep(2)
else:
    sys.exit("VOICEVOX engine did not start")
ids = {(s["name"], st["name"]): st["id"] for s in json.loads(call("/speakers")) for st in s["styles"]}

cards = json.load(open("cards.json", encoding="utf8"))
texts = sorted({c.strip() for c in cards if c and c.strip()})
idx_path = "audio/index.json"
old = json.load(open(idx_path, encoding="utf8")) if os.path.exists(idx_path) else {}
files = old.get("files", {}) if old.get("format") == FORMAT else {}
idx = {"format": FORMAT, "default": "sora", "voices": {}, "files": {}}
status = {"ok": True, "made": 0, "errors": []}

for vid, (who, style, pitch, inton, label) in VOICES.items():
    sid = ids.get((who, style))
    if sid is None:
        status["errors"].append(f"{vid}: {who}/{style} not found"); continue
    idx["voices"][vid] = {"label": label, "credit": f"VOICEVOX:{who}"}
    os.makedirs(f"audio/{vid}", exist_ok=True)
    have = files.get(vid, {})
    idx["files"][vid] = {}
    for t in texts:
        h = key(t); out = f"audio/{vid}/{h}.mp3"
        if h in have and os.path.exists(out):
            idx["files"][vid][h] = have[h]; continue
        try:
            q = json.loads(call(f"/audio_query?text={urllib.parse.quote(t)}&speaker={sid}", b""))
            q.update({"pitchScale": pitch, "intonationScale": inton, "prePhonemeLength": 0.05, "postPhonemeLength": 0.05})
            wav = call(f"/synthesis?speaker={sid}", json.dumps(q).encode())
        except Exception as e:
            status["ok"] = False; status["errors"].append(f"{vid}/{h}: {e!r}"); continue
        with tempfile.TemporaryDirectory() as td:
            base = os.path.join(td, "base.wav")
            open(base, "wb").write(wav)
            d0 = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", base],
                                      capture_output=True, text=True, check=True).stdout.strip())
            fc = f"[0:a]loudnorm=I=-18:TP=-1.5,asplit={N}" + "".join(f"[s{i}]" for i in range(N)) + ";" \
                 + ";".join(f"[s{i}]apad=pad_dur={GAP}[a{i}]" for i in range(N)) + ";" \
                 + "".join(f"[a{i}]" for i in range(N)) + f"concat=n={N}:v=0:a=1,adelay={int(LEAD*1000)}[out]"
            subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", base, "-filter_complex", fc, "-map", "[out]",
                            "-ac", "1", "-ar", "24000", "-b:a", "64k", out], check=True)
        idx["files"][vid][h] = {"starts": [round(LEAD + k * (d0 + GAP), 3) for k in range(N)], "len": round(d0, 3)}
        status["made"] += 1
    keep = set(idx["files"][vid])
    for f in os.listdir(f"audio/{vid}"):
        if f.endswith(".mp3") and f[:-4] not in keep: os.remove(f"audio/{vid}/{f}")

# 예전 형식 파일 정리
for f in os.listdir("audio"):
    if f.endswith(".mp3"): os.remove(f"audio/{f}")
json.dump(idx, open(idx_path, "w", encoding="utf8"), ensure_ascii=False, indent=1)
json.dump(status, open("audio/_status.json", "w", encoding="utf8"), ensure_ascii=False, indent=1)
print(json.dumps(status, ensure_ascii=False))
