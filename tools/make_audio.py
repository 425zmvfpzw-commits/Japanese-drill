"""문장마다 리스닝 드릴 음성 파일을 목소리별로 만든다 (VOICEVOX 엔진, 로컬 실행).

cards.json 의 일본어 문장 하나당 audio/<목소리>/<해시>.mp3 하나:
한 번 읽은 짧은 파일을 만들고, 앱이 10번 반복해서 재생한다.
audio/index.json 에 목소리 목록과, 각 반복이 시작되는 시각(초)을 적는다.
"""
import hashlib, json, os, subprocess, sys, tempfile, time, urllib.parse, urllib.request

API = "http://127.0.0.1:50021"
N, GAP, LEAD = 10, 0.7, 0.25
FORMAT = 5   # 파일 형식이 바뀌면 숫자를 올려서 전부 다시 만든다
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

def render(t, sid, pitch, inton):
    """문장 하나 → (한 번 읽은 mp3 바이트, 길이 정보)"""
    q = json.loads(call(f"/audio_query?text={urllib.parse.quote(t)}&speaker={sid}", b""))
    q.update({"pitchScale": pitch, "intonationScale": inton, "prePhonemeLength": 0.05, "postPhonemeLength": 0.05})
    wav = call(f"/synthesis?speaker={sid}", json.dumps(q).encode())
    with tempfile.TemporaryDirectory() as td:
        base = os.path.join(td, "base.wav"); out = os.path.join(td, "out.mp3")
        open(base, "wb").write(wav)
        d0 = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", base],
                                  capture_output=True, text=True, check=True).stdout.strip())
        # 한 번만 읽은 짧은 파일 (앞 0.1초, 뒤 쉼 GAP초). 10번 반복은 앱이 재생하면서 한다
        fc = f"[0:a]loudnorm=I=-18:TP=-1.5,adelay=100,apad=pad_dur={GAP}[out]"
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", base, "-filter_complex", fc, "-map", "[out]",
                        "-ac", "1", "-ar", "22050", "-b:a", "32k", out], check=True)
        data = open(out, "rb").read()
    return data, {"loop": True, "len": round(d0 + 0.1, 3)}

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
            data, meta = render(t, sid, pitch, inton)
        except Exception as e:
            status["ok"] = False; status["errors"].append(f"{vid}/{h}: {e!r}"); continue
        open(out, "wb").write(data)
        idx["files"][vid][h] = meta
        status["made"] += 1
        continue
    keep = set(idx["files"][vid])
    for f in os.listdir(f"audio/{vid}"):
        if f.endswith(".mp3") and f[:-4] not in keep: os.remove(f"audio/{vid}/{f}")

# ---- 비공개 문장: 암호화된 목록(private.enc)을 풀어서 음성을 만들고, 음성도 암호화해서 올린다 ----
def private_audio():
    import base64, hmac
    k64 = os.environ.get("DRILL_KEY", "").strip()
    if not k64 or not os.path.exists("private.enc"):
        status["private"] = "skipped (no key or list)"; return
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    key = base64.b64decode(k64); aes = AESGCM(key)
    blob = open("private.enc", "rb").read()
    try:
        ptexts = json.loads(aes.decrypt(blob[:12], blob[12:], None).decode("utf8"))
    except Exception as e:
        status["private"] = f"key mismatch: {e!r}"; status["ok"] = False; return
    pid = lambda t: hmac.new(key, t.strip().encode("utf8"), "sha256").hexdigest()[:16]
    pidx_path = "paudio/index.json"
    pold = json.load(open(pidx_path, encoding="utf8")) if os.path.exists(pidx_path) else {}
    pfiles = pold.get("files", {}) if pold.get("format") == FORMAT else {}
    pidx = {"format": FORMAT, "files": {}}
    made = 0
    for vid, (who, style, pitch, inton, label) in VOICES.items():
        sid = ids.get((who, style))
        if sid is None: continue
        os.makedirs(f"paudio/{vid}", exist_ok=True)
        have = pfiles.get(vid, {}); pidx["files"][vid] = {}
        for t in sorted({x.strip() for x in ptexts if x and x.strip()}):
            h = pid(t); out = f"paudio/{vid}/{h}.bin"
            if h in have and os.path.exists(out):
                pidx["files"][vid][h] = have[h]; continue
            try:
                mp3, meta = render(t, sid, pitch, inton)
            except Exception as e:
                status["ok"] = False; status["errors"].append(f"private {vid}: {e!r}"); continue
            nonce = os.urandom(12)
            open(out, "wb").write(nonce + aes.encrypt(nonce, mp3, None))
            pidx["files"][vid][h] = meta; made += 1
        keep = set(pidx["files"][vid])
        for f in os.listdir(f"paudio/{vid}"):
            if f.endswith(".bin") and f[:-4] not in keep: os.remove(f"paudio/{vid}/{f}")
    json.dump(pidx, open(pidx_path, "w", encoding="utf8"), indent=1)
    status["private"] = f"{made} made, {sum(len(v) for v in pidx['files'].values())} total"

private_audio()

# 예전 형식 파일 정리
for f in os.listdir("audio"):
    if f.endswith(".mp3"): os.remove(f"audio/{f}")
json.dump(idx, open(idx_path, "w", encoding="utf8"), ensure_ascii=False, indent=1)
json.dump(status, open("audio/_status.json", "w", encoding="utf8"), ensure_ascii=False, indent=1)
print(json.dumps(status, ensure_ascii=False))
