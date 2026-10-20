"""문장마다 리스닝 드릴 음성 파일을 만든다.

cards.json 의 일본어 문장 하나당 audio/<해시>.mp3 하나:
같은 문장을 보통 속도로 10번 이어 붙인다. (1배/1.5배는 앱에서 재생 속도로 고른다)
audio/index.json 에 각 반복이 시작되는 시각(초)을 적어 앱이 몇 번째인지 표시한다.
음성: Style-Bert-VITS2 (JVNV 공개 모델, 여성), 실패하면 Kokoro.
"""
import hashlib, json, os, subprocess, sys, tempfile

import numpy as np
import soundfile as sf

N, GAP, LEAD = 10, 0.7, 0.25
RATES = [1.0] * N
FORMAT = 3   # 파일 형식이 바뀌면 숫자를 올려서 전부 다시 만든다
os.makedirs("audio", exist_ok=True)
cards = json.load(open("cards.json", encoding="utf8"))
texts = sorted({c.strip() for c in cards if c and c.strip()})
idx_path = "audio/index.json"
idx = json.load(open(idx_path, encoding="utf8")) if os.path.exists(idx_path) else {}

def key(t):
    return hashlib.sha256(t.strip().encode("utf8")).hexdigest()[:16]

_engine = None
VOICE = os.environ.get("DRILL_VOICE", "jvnv-F1-jp")
def _sbv2():
    from huggingface_hub import hf_hub_download, list_repo_files
    from style_bert_vits2.constants import Languages
    from style_bert_vits2.nlp import bert_models
    from style_bert_vits2.tts_model import TTSModel
    bert = "ku-nlp/deberta-v2-large-japanese-char-wwm"
    bert_models.load_model(Languages.JP, bert)
    bert_models.load_tokenizer(Languages.JP, bert)
    repo = "litagin/style_bert_vits2_jvnv"
    files = [f for f in list_repo_files(repo) if f.startswith(VOICE + "/")]
    pick = lambda suf: hf_hub_download(repo, sorted(f for f in files if f.endswith(suf))[-1])
    model = TTSModel(model_path=pick(".safetensors"), config_path=pick("config.json"), style_vec_path=pick("style_vectors.npy"), device="cpu")
    def run(t):
        sr, a = model.infer(text=t, language=Languages.JP, style="Neutral", style_weight=1.0, sdp_ratio=0.2, noise=0.6, noise_w=0.8, length=1.0)
        a = np.asarray(a)
        a = a.astype("float32") / (32768.0 if a.dtype == np.int16 else 1.0)
        return a, sr
    return run
def _kokoro():
    from kokoro import KPipeline
    pipe = KPipeline(lang_code="j")
    def run(t):
        parts = [a.cpu().numpy() if hasattr(a, "cpu") else np.asarray(a) for _, _, a in pipe(t, voice="jf_alpha", speed=1.0)]
        return np.concatenate(parts).astype("float32"), 24000
    return run
def synth(text):
    """returns (float32 mono samples, sample rate)"""
    global _engine
    if _engine is None:
        for name, make in (("sbv2:" + VOICE, _sbv2), ("kokoro", _kokoro)):
            try:
                _engine = (name, make()); break
            except Exception as e:
                print(f"{name} unavailable:", repr(e), file=sys.stderr)
        if _engine is None: sys.exit("no voice engine")
    return _engine[1](text)

made = 0
for t in texts:
    h = key(t)
    out = f"audio/{h}.mp3"
    if h in idx and os.path.exists(out) and idx[h].get("format") == FORMAT:
        continue
    x, sr = synth(t)
    peak = float(np.max(np.abs(x))) or 1.0
    x = (x / peak * 0.9).astype("float32")
    with tempfile.TemporaryDirectory() as td:
        base = os.path.join(td, "base.wav")
        sf.write(base, x, sr)
        d0 = len(x) / sr
        chains = [f"[0:a]apad=pad_dur={GAP}[a{i}]" for i in range(N)]
        fc = f"[0:a]asplit={N}" + "".join(f"[s{i}]" for i in range(N)) + ";" + ";".join(c.replace("[0:a]", f"[s{i}]") for i, c in enumerate(chains)) + ";" + "".join(f"[a{i}]" for i in range(N)) + f"concat=n={N}:v=0:a=1,adelay={int(LEAD*1000)}[out]"
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", base, "-filter_complex", fc, "-map", "[out]",
                        "-ac", "1", "-ar", "24000", "-b:a", "64k", out], check=True)
    starts, cur = [], LEAD
    for r in RATES:
        starts.append(round(cur, 3)); cur += d0 / r + GAP
    idx[h] = {"starts": starts, "ja": t, "voice": _engine[0], "format": FORMAT}
    made += 1
    print("made", h)

keep = {key(t) for t in texts}
for h in list(idx):
    if h not in keep:
        idx.pop(h)
        try: os.remove(f"audio/{h}.mp3")
        except FileNotFoundError: pass

json.dump({k: idx[k] for k in sorted(idx)}, open(idx_path, "w", encoding="utf8"), ensure_ascii=False, indent=1)
print(f"done: {made} new, {len(idx)} total")
