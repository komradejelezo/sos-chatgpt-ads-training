"""Convert Russian word-level alignments into two-line timed cues."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIX = {
    "тинге": "тенге", "тинге,": "тенге,", "пройдем": "пройдём", "возьмем": "возьмём", "компанию.": "кампанию.", "компанию,": "кампанию,",
    "компания.": "кампания.", "компания": "кампания", "компании.": "кампании.",
    "дюджет": "бюджет", "дюджет,": "бюджет,", "примене": "примере",
    "имкогнита": "инкогнито", "зрители": "зрителей",
}

def normalize(words):
    result = []
    for item in words:
        word = item["word"].strip()
        if result and result[-1]["word"].lower() == "чат" and word.startswith("GPT"):
            result[-1].update(word="Chat" + word, end=item["end"])
        else:
            result.append(dict(item, word=FIX.get(word, word)))
    return result


def cues(words):
    group = []
    for item in normalize(words):
        length = sum(len(w["word"]) + 1 for w in group)
        if group and (length + len(item["word"]) > 55 or
                      item["end"] - group[0]["start"] > 3.2 or
                      item["start"] - group[-1]["end"] > .52):
            yield make(group)
            group = []
        group.append(item)
        if item["word"].endswith((".", "?", "!")) and item["word"] not in {"ads.openai.com."}:
            yield make(group)
            group = []
    if group:
        yield make(group)


def make(group):
    words = [w["word"] for w in group]
    text = " ".join(words)
    if text.lower().startswith("узнайте больше"):
        text = "Узнайте больше на сайте"
        words = text.split()
    if len(text) > 29 and len(words) > 1:
        candidates = [(" ".join(words[:i]), " ".join(words[i:])) for i in range(1, len(words))]
        rows = list(min(candidates, key=lambda pair: max(map(len, pair))))
    else:
        rows = [text]
    key = max(words, key=len)
    return [group[0]["start"], group[-1]["end"], rows, key]


if __name__ == "__main__":
    result = []
    for path in sorted((ROOT / "work").glob("0[1-6]_*.json")):
        chapter = list(cues(json.loads(path.read_text())))
        if path.stem.startswith("01"):
            for cue in chapter:
                cue[2] = [line.replace("делегировании и задачи", "делегировании задач").replace("делегировании и", "делегировании") for line in cue[2]]
        if path.stem.startswith("02"):
            chapter = [[0.0, 3.56, ["Начинаем с сайта", "ads.openai.com."], "ads.openai.com."]] + [cue for cue in chapter if cue[0] >= 3.56]
            for cue in chapter:
                if 12 < cue[0] < 16:
                    cue[2] = [line.replace("кампании.", "компании.") for line in cue[2]]
        result.append(chapter)
    assert len(result) == 6
    # Correct the recognizer's split pronunciation of the closing URL.
    result[-1] = [cue for cue in result[-1] if cue[0] < 65.36]
    result[-1].extend([
        [65.36, 66.68, ["Узнайте больше на сайте"], "сайте"],
        [66.68, 68.88, ["soul-of-the-system.kz"], "soul-of-the-system.kz"],
    ])
    (ROOT / "master" / "captions.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
