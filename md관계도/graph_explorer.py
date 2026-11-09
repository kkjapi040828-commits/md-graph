# -*- coding: utf-8 -*-
"""
graph_explorer.py - md 참조 관계를 브라우저에서 조작 가능한 도식으로 만든다.

요구사항 (사용자 요청 2026-11-08):
  - A(규칙 참조) · B(문서 참조) 는 기본 ON
  - C(설명 언급) · D(자리표시자) 는 선택했을 때만, 그리고 실선으로
  - 각 참조 유형은 색이 다르다
  - 유형별로 ON/OFF 할 수 있다

DESIGN.md 준수 (블랙 테마):
  - 배경 #0f0f10 / 바탕 #1c1c1e / 글자 #f2f2f3 / 흐림 #9a9aa2 / 선 #454545
  - 글자 13 / 12 / 10px 세 종류만
  - 칩 높이 38px, 둥글기 = 높이의 절반
  - 이모지 금지, 그라데이션 금지, 안내문구 금지, 오버레이 금지
  - 글꼴 Pretendard
  - 단, "유형별 다른 색"은 사용자 명시 요구라 accent 1색 규칙보다 우선한다.

쓰는 법:
    python graph_explorer.py
    -> _docs/관계도.html   (더블클릭)
"""
import html
import json
import os
import re
import sys
from pathlib import Path
from datetime import datetime

# ---- 작업 폴더를 "스크립트 위치"에서 찾는다 (범용 배포용)
# WHY: 예전엔 작업장 경로를 하드코딩해서 이 PC 에서만 돌았다.
#      이 파일은 <작업폴더>\_cli\graph_explorer.py 에 있으므로 두 단계 위가 ROOT 다.
#      --root 로 직접 지정할 수도 있다.
def _find_root() -> Path:
    """작업 폴더를 찾는다. 배포판에서는 '스크립트가 있는 폴더'가 아니라
    '스크립트 옆에 있는 md 들'이 대상이다.

    우선순위:
      1. --root 로 지정했으면 그것
      2. 스크립트가 ROOT 안의 _cli 폴더에 있으면 ROOT (이 PC 의 원래 구조)
      3. 스크립트가 든 폴더 자체 (배포판: zip 을 푼 폴더)
    """
    args = sys.argv[1:]
    if "--root" in args:
        i = args.index("--root")
        if i + 1 < len(args):
            return Path(args[i + 1]).resolve()

    here = Path(__file__).resolve()
    parent = here.parent

    # 2) <ROOT>\_cli\graph_explorer.py  →  ROOT
    if parent.name.lower() in ("_cli", "_tools", "tools", "bin"):
        cand = parent.parent
        if (cand / "AGENTS.md").exists() or (cand / ".git").exists():
            return cand

    # 3) 배포판: 스크립트가 든 폴더에서 md 를 찾는다.
    #    ⚠️ 여기서 상위로 올라가면 안 된다. zip 을 작업장 폴더 어딘가에 풀었을 때
    #    상위 작업장 폴더를 잡아 엉뚱한 곳에 결과를 쓰는 버그가 있었다(2026-11-09 실측).
    return parent


ROOT = _find_root()
HOME = Path(os.environ.get("USERPROFILE") or os.environ.get("HOME") or ".").resolve()


def _pick_out(root: Path) -> Path:
    """결과 HTML 을 놓을 곳. 쓰기가 되는 첫 후보를 쓴다.

    배포판은 폴더 구조가 다를 수 있다(원본은 <ROOT>\_docs\, 받는 사람은 그냥 폴더).
    없는 폴더에 쓰려다 죽는 일이 없게 후보를 순서대로 시도한다.
    """
    for sub in (("_docs",), ()):
        d = root.joinpath(*sub) if sub else root
        try:
            d.mkdir(parents=True, exist_ok=True)
            probe = d / ".write_probe"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
            return d / "관계도.html"
        except Exception:
            continue
    # 최후: 사용자 Downloads
    for cand in (HOME / "Downloads", HOME):
        try:
            cand.mkdir(parents=True, exist_ok=True)
            return cand / "관계도.html"
        except Exception:
            continue
    return Path.cwd() / "관계도.html"


OUT = _pick_out(ROOT)

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# 제외 폴더 — ROOT 바로 아래 이름만 본다 (상위 경로는 안 본다).
# WHY: 예전엔 경로 전체에 정규식을 걸어서, 이 스크립트를 C:\...\_tmp\ 아래에
#      두면 모든 md 가 걸러져 노드가 1개가 됐다(2026-11-09 실측).
#      배포 대상 폴더 이름이 뭐든 자기 md 는 다 읽어야 한다.
SKIP_DIR_NAMES = {
    "node_modules", ".git", "__pycache__", "_bak", "_tmp", "_push",
    "_도구", "_archive", "_가져오기", "office-skills",
    # 시험·임시 폴더 (2026-11-09: 팀원이 만든 _portest 가 노드로 섞여서 추가)
    "_portest", "_probe", "_test", "_review_output",
}


def should_skip(path: Path, root: Path) -> bool:
    """이 경로를 건너뛸까? ROOT 기준 상대경로의 '각 조각'만 검사한다."""
    try:
        parts = path.resolve().relative_to(Path(root).resolve()).parts
    except ValueError:
        return False
    for seg in parts:
        if seg.lower() in SKIP_DIR_NAMES:
            return True
    return False
# 참조 패턴. `.md` 앞 최소 길이가 **1** 이어야 한다.
# 2026-11-09 이식성검토 실측: 예전 `{2,140}` 은 `a.md`·`b.md`·`x.md` 를 매치조차
# 못 했다. 그래서 짧은 파일명을 쓰는 폴더에서 링크가 통째로 사라졌다.
REF_PAT = re.compile(r"`([^`\n]{1,140}?\.md)`")

# ---- 지침 파일: 폴더 구조에서 자동으로 찾는다 (범용 배포용)
# WHY: 예전엔 과제\과제3\, 투운사\ 를 하드코딩해서 다른 폴더에서는 틀렸다.
#
# ⚠️ 2026-11-09 이식성검토 지적: "ROOT 하위 모든 AGENTS.md 를 체인에 넣으면
#    형제 폴더 것까지 chain=True 로 승격돼서 그 폴더의 문서참조가 전부 A(규칙
#    참조)가 된다." 실제로 그랬다.
#    DSH 의 실제 로드 규칙은 **세션 cwd 에서 위로 올라가며 조상만** 읽는다.
#    그래서 두 가지를 나눈다:
#      ALL_AGENTS — 이 작업장에 있는 모든 AGENTS.md (범위 표시용)
#      CHAIN      — 지금 세션이 실제로 읽는 것 (전역 + 루트). A 판정에 쓰인다.
def _find_all_agents():
    found = []
    g = HOME / ".dsh" / "AGENTS.md"
    if g.exists():
        found.append(g)
    r = ROOT / "AGENTS.md"
    if r.exists():
        found.append(r)
    for p in ROOT.rglob("AGENTS.md"):
        if should_skip(p, ROOT):
            continue
        if any(p.resolve() == x.resolve() for x in found):
            continue
        found.append(p)
    found.sort(key=lambda p: (len(p.parts), str(p)))
    return found


ALL_AGENTS = _find_all_agents()

# CHAIN = "실제로 같이 읽히는 것". 전역 + 작업장 루트만. (cwd 조상 원칙)
CHAIN = [p for p in ALL_AGENTS if p.parent.resolve() in
         (ROOT.resolve(), (HOME / ".dsh").resolve())]

PLACEHOLDER = re.compile(r"[*{}<>]|^NN_|NNNN|^\.\.\.|…|^\.zh\.md$")
EXTERNAL = re.compile(
    r"^(docs/|solutions/|~|\.claude/|\.agents/)|"
    r"(CLAUDE|AGENTS\.local|CLAUDE\.local|MEMORY)\.md$|"
    r"^(architecture|testing|cordis-primer|agents-md-scope)\.md$",
    re.I,
)
DOC_MARK = re.compile(r"참고|참조|자세히|상세|근거|따른다|먼저 본다|본다|문서|지도")


def rel(p: Path) -> str:
    """표시용 경로. ROOT 밖(전역 ~/.dsh 등)은 **절대경로를 노출하지 않는다.**

    2026-11-09 이식성검토: 예전엔 ValueError 나면 str(p) 를 그대로 써서
    `C:\\Users\\User\\.dsh\\AGENTS.md` 가 HTML 에 15번 박혔다. 배포 시 개인정보.
    이제 `~/.dsh/AGENTS.md` 처럼 홈 기준 상대표기로 바꾼다.
    """
    try:
        return str(p.relative_to(ROOT))
    except ValueError:
        pass
    try:
        return "~/" + str(p.relative_to(HOME)).replace("\\", "/")
    except ValueError:
        return p.name          # 마지막 수단: 파일명만


def read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8")
    except Exception:
        return ""


def wc(t: str) -> int:
    return len([w for w in re.split(r"\s+", t) if w])


def resolve(src: Path, ref: str):
    ref = ref.strip().strip("`").replace("/", "\\")
    if not ref.lower().endswith(".md"):
        return None
    if re.match(r"^[A-Za-z]:\\", ref):
        c = Path(ref)
        return c if c.exists() else None
    for c in (src.parent / ref, ROOT / ref):
        if c.exists() and c.is_file():
            return c
    base = Path(ref).name
    if "*" in base:
        return None
    # 색인에서 찾는다. 예전엔 ROOT.rglob(base) 로 매번 전체를 뒤져서
    # 갱신 1회에 4초 걸렸다(구조검토 2026-11-08). 색인은 1회만 만든다 → 0.3초.
    return NAME_INDEX.get(base.lower())


# 파일명(소문자) -> 경로. 첫 호출 때 한 번만 만든다.
_NAME_INDEX = None


def _build_name_index():
    idx = {}
    for p in ROOT.rglob("*.md"):
        if should_skip(p, ROOT):
            continue
        key = p.name.lower()
        # 같은 이름이 여럿이면 짧은 경로를 쓴다 (가장 가까운 것)
        if key not in idx or len(str(p)) < len(str(idx[key])):
            idx[key] = p
    return idx


def _get_name_index():
    global _NAME_INDEX
    if _NAME_INDEX is None:
        _NAME_INDEX = _build_name_index()
    return _NAME_INDEX


# resolve() 안에서 쓰는 이름
class _NameIndexProxy:
    def get(self, k, default=None):
        return _get_name_index().get(k, default)


NAME_INDEX = _NameIndexProxy()


def line_of(text: str, pos: int):
    start = text.rfind("\n", 0, pos) + 1
    end = text.find("\n", pos)
    if end == -1:
        end = len(text)
    return text[start:end].strip()


def classify(is_chain: bool, ref: str, tgt, text: str, pos: int):
    line = line_of(text, pos)
    if re.match(r"^\s*\|", line) and is_chain:
        return "A", line
    if PLACEHOLDER.search(ref):
        return "D", line
    if EXTERNAL.search(ref):
        return "E", line
    if is_chain:
        return "A", line
    if tgt is None:
        return "F", line
    if DOC_MARK.search(line):
        return "B", line
    if re.match(r"^\s*[-*+]\s+", line) and line.find("`") < 6:
        return "B", line
    return "C", line


def display_name(p: Path) -> str:
    """화면 라벨. 같은 파일명이 여러 폴더에 있으면 부모 폴더명을 붙여 구별한다.

    WHY (2026-11-09): 라벨이 전부 `SKILL.md` 라 어느 스킬인지 알 수 없었다.
    사용자 지적: "각각 누구 agentmd 인지 알면 좋겠다".
    규칙은 외부 도구와 맞춘다 — 가장 짧은 구별 이름을 쓴다.
      · 스킬(`<이름>/SKILL.md`) → 폴더명 (`c4-architecture`)
      · 그 외 동명       → `부모/파일명` (`투운사/README.md`)
    동명이 아니면 파일명 그대로. 꼬리표가 길어지지 않게 1단계만 쓴다.
    """
    base = p.name
    # 스킬은 폴더명이 곧 이름이다. SKILL.md 라는 파일명은 정보가 없다.
    # AGENTS.md 도 포함한다 — 사용자 요청 2026-11-09: "각각 누구 agentmd 인지
    # 알면 좋겠다". 체인 노드는 화면에서 scope 를 덧붙이지만, 체인이 아닌
    # 하위 폴더 AGENTS.md(_dsh_config\, 과제\)는 그것만으로는 구별이 안 됐다.
    if base.lower() in ("skill.md", "claude.md", "agents.md", "readme.md", "index.md"):
        try:
            rel_parts = p.resolve().relative_to(ROOT.resolve()).parts
        except ValueError:
            rel_parts = p.parts
        # 부모 폴더명. 루트 바로 아래면 부모가 루트라 폴더명이 없다 → 파일명 유지.
        if len(rel_parts) >= 2:
            return f"{rel_parts[-2]}/{base}"
    return base


def collect():
    files = []
    for p in ROOT.rglob("*.md"):
        if should_skip(p, ROOT) or p.name.startswith("_"):
            continue
        files.append(p)
    g = HOME / ".dsh" / "AGENTS.md"
    if g.exists():
        files.append(g)
    seen = set()
    uniq = []
    for p in files:
        k = str(p.resolve())
        if k in seen:
            continue
        seen.add(k)
        uniq.append(p)
    files = sorted(uniq, key=lambda p: rel(p))
    chain_keys = {str(p.resolve()) for p in CHAIN if p.exists()}

    # ---- 각 md 가 "어느 AGENTS.md 지배를 받나" (scope)
    # WHY: 사용자 지적 2026-11-09 — "각각 누구 agentmd 인지 알면 좋겠다.
    #      범용인가 과제 파일인가". 상위(넓은) 규칙일수록 중요하다.
    #      판정: 자신의 상위 폴더 중 가장 가까운 AGENTS.md 를 가진 폴더.
    #      ALL_AGENTS 를 쓴다 — CHAIN 은 "같이 읽히는 것"이라 범위 표시에는 부족하다.
    agents_dirs = []
    for a in ALL_AGENTS:
        if a.exists() and a.name == "AGENTS.md":
            agents_dirs.append(a.parent)

    def scope_of(path: Path) -> str:
        if not agents_dirs:
            return "(없음)"
        cands = [d for d in agents_dirs if str(path).startswith(str(d))]
        if not cands:
            return "(없음)"
        best = max(cands, key=lambda d: len(d.parts))
        if best.resolve() == (HOME / ".dsh").resolve():
            return "(전역)"
        if best.resolve() == ROOT.resolve():
            return "(작업장 루트)"
        try:
            r = best.relative_to(ROOT)
            return str(r) if str(r) != "." else "(작업장 루트)"
        except ValueError:
            return best.name

    nodes = {}
    for p in files:
        t = read(p)
        nodes[rel(p)] = {
            "key": rel(p),
            # 라벨: 파일명 그대로는 안 된다. `SKILL.md` 처럼 같은 이름이 여러 폴더에
            # 있으면 화면에서 구별이 안 된다(2026-11-09 실측: 동명 4종이 노드 23개를
            # 덮었다 — SKILL.md 10, AGENTS.md 6, README.md 5, INDEX.md 2).
            # 외부 표준(Cosma=YAML title, iwe=경로 꼬리표, Foam=최소 식별자)과 같이
            # "구별되는 가장 짧은 이름"을 쓴다: 부모 폴더명을 앞에 붙인다.
            "name": display_name(p),
            # base = 실제 파일명. 라벨(name)이 "c4-architecture/SKILL.md" 처럼
            # 꼬리표가 붙으면 본문 검색(findMentionLine)에서 못 찾는다.
            # 본문에는 "SKILL.md" 나 폴더명으로 적혀 있기 때문이다.
            # 그래서 검색용으로 원래 파일명을 따로 남긴다(2026-11-09).
            "base": p.name,
            "dir": str(p.parent.relative_to(ROOT)) if str(p).startswith(str(ROOT)) else "~",
            "words": wc(t),
            "chain": str(p.resolve()) in chain_keys,
            "scope": scope_of(p),
            "indeg": 0,
            "outdeg": 0,
            "body": mask_private(t),
        }

    edges = []
    # G(연결 없음)도 센다. 예전엔 A~F 만 세서 고아 노드 칩이 영원히 안 보였다
    # (기능검토 #12 수정이 절반만 들어간 상태 — 외부도구 비교 지적 2026-11-09).
    bucket = {"A": 0, "B": 0, "C": 0, "D": 0, "E": 0, "F": 0, "G": 0}
    for p in files:
        sk = rel(p)
        if sk not in nodes:
            continue
    for p in files:
        sk = rel(p)
        if sk not in nodes:
            continue
        t = read(p)
        is_chain = str(p.resolve()) in chain_keys
        seen_ref = set()
        for m in REF_PAT.finditer(t):
            ref = m.group(1)
            if " " in ref and not re.match(r"^[A-Za-z]:\\", ref):
                continue
            tgt = resolve(p, ref)
            kind, line = classify(is_chain, ref, tgt, t, m.start())
            # ⚠️ 여기서 bucket 을 세면 안 된다. 예전엔 세고 나서 tgt is None 이면
            #    continue 해서, **실제 연결이 아닌 것까지 세는** 버그가 있었다
            #    (2026-11-09 이식성검토: bucket 합 769 vs 실제 선 447, 차이 322).
            #    그래서 칩 숫자와 화면의 선 개수가 달랐다.
            if tgt is None:
                bucket[kind] += 1      # 파일이 없는 참조도 "그 유형으로 언급됨"으로 센다
                continue
            tk = rel(tgt)
            if tk == sk or tk not in nodes:
                bucket[kind] += 1
                continue
            k = (sk, tk, kind)
            if k in seen_ref:
                continue
            seen_ref.add(k)
            bucket[kind] += 1
            edges.append({"s": sk, "t": tk, "k": kind, "line": mask_private(line)[:160]})

    for e in edges:
        nodes[e["s"]]["outdeg"] += 1
        nodes[e["t"]]["indeg"] += 1

    # 고아(G) = 엣지가 하나도 없는 노드. 지침 체인 노드는 규칙상 늘 보이므로 뺀다.
    linked = set()
    for e in edges:
        linked.add(e["s"])
        linked.add(e["t"])
    for k, n in nodes.items():
        if k not in linked and not n.get("chain"):
            bucket["G"] += 1
            n["orphan"] = True

    return nodes, edges, bucket


HTML = r"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>md 관계도</title>
<style>
/* DESIGN.md §2: "테마 이름표는 고정, 값만 갈아 끼운다."
   예전엔 hex 를 18종 하드코딩해서 테마를 바꾸려면 CSS 전체를 손봐야 했다.
   이제 아래 10개 값만 바꾸면 테마가 바뀐다. 문서에 없는 색(#8a8a8a,
   #c8c8ce, #8a8a94)은 --muted / --text / --line-strong 으로 흡수했다. */
:root{
  --bg:#0f0f10;
  --surface:#1c1c1e;
  --text:#f2f2f3;
  --muted:#9a9aa2;
  --line:#454545;
  --line-strong:#676767;
  --chip-on-bg:#2f2f34;
  --chip-on-text:#ffffff;
  --danger:#e5484d;
  /* 유형 식별색 — §2 의 '한 역할' 예외. 켜고 끄는 의미를 담으므로 구분이 필요하다. */
  --k-a:#f2f2f3;
  --k-b:#6ea8ff;
  --k-c:#8a8a94;
  --k-d:#e0a33e;
  --k-e:#a06bd6;
  --k-f:#e5484d;
  --k-g:#5a5a62;
  --mark:#ffd479;
  --mark-bg:#3a3016;
}
*{box-sizing:border-box}
html,body{margin:0;padding:0;height:100%}
body{background:var(--bg);color:var(--text);font-family:Pretendard,system-ui,sans-serif;
     display:grid;grid-template-rows:58px 1fr;overflow:hidden}
#bar{display:flex;align-items:center;gap:8px;padding:0 12px;
     border-bottom:1px solid var(--line);background:var(--bg);z-index:5}
h1{font-size:13px;font-weight:600;margin:0 8px 0 0;letter-spacing:0}
.tog{display:inline-flex;align-items:center;justify-content:center;gap:6px;
     height:38px;padding:0 14px;border-radius:19px;background:var(--surface);
     border:1px solid var(--line-strong);color:var(--muted);font-size:13px;cursor:pointer;
     user-select:none;font-family:inherit}
.tog:hover{border-color:var(--muted)}
/* DESIGN.md §3: 켜진 칩은 배경색만 바뀌고 굵은 글씨 (MODEL: border 색은 그대로) */
.tog.on{background:var(--chip-on-bg);color:var(--chip-on-text);font-weight:600}
.dot{width:8px;height:8px;border-radius:999px;flex:none}
/* DESIGN.md §2·§8: 꺼진 점을 opacity 로 흐리면 대비가 1.2~1.8:1 로 떨어진다.
   끄면 회색 한 색(--muted)으로 바꾼다. */
.tog.off .dot{background:var(--muted) !important}
.count{font-size:10px;color:var(--muted);margin-left:8px}
#meta{margin-left:auto;font-size:12px;color:var(--muted)}
#find{height:38px;padding:0 14px;border-radius:19px;background:var(--surface);
      border:1px solid var(--line-strong);color:var(--text);font-size:13px;
      font-family:inherit;width:180px;outline:none}
#find:focus{border-color:var(--muted)}
#find::placeholder{color:var(--muted)}
#focusbar{display:flex;align-items:center;gap:8px}
#focusbar:empty{display:none}
.kv{font-size:12px;color:var(--muted);margin:8px 0}
/* DESIGN.md §3: 누르는 것은 38px 이상. 예전 30px 이었다. */
.row{display:flex;align-items:center;gap:8px;height:38px;padding:0 8px;border-radius:10px;
     cursor:pointer;font-size:12px;color:var(--text)}
.row:hover{background:var(--chip-on-bg);color:var(--chip-on-text)}
.row .nm{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
/* DESIGN.md §5: 페이지 안에 또 스크롤 영역을 만들지 않는다.
   예전엔 .body 에 max-height:340px + overflow-y:auto 를 줘서
   페이지(잠김) → 패널(스크롤) → 본문상자(스크롤) 3중이었다.
   이제 스크롤은 오른쪽 패널(#side .bd) 하나뿐이다. */
.body{font-size:10px;color:var(--muted);line-height:1.6;white-space:pre-wrap;
      word-break:break-word;background:var(--bg);border:1px solid var(--line);
      border-radius:10px;padding:10px}
.ln{padding:0 2px}
.ln.hit{background:var(--mark-bg);color:var(--mark)}
.chk{padding:10px;border-radius:10px;background:var(--bg);border:1px solid var(--line);margin:8px 0}
.chk-t{font-size:12px;color:var(--text)}
.chk-d{font-size:10px;color:var(--muted);margin-top:8px;line-height:1.5}
.chk-meta{font-size:10px;margin-top:8px;line-height:1.5;color:var(--muted)}
.chk-tgt{color:var(--k-b)}   /* 대상 = 파랑 */
.chk-m{color:var(--k-d)}     /* 보는 것 = 주황 */
.chk-o{color:var(--k-f)}     /* 결과 = 빨강 */
.nn{font-weight:600;font-size:12px}
.nn-ok{color:var(--k-b)}
.nn-bad{color:var(--k-f)}
#wrap{position:relative;overflow:hidden;background:var(--bg)}
canvas{display:block;width:100%;height:100%;cursor:grab}
canvas.drag{cursor:grabbing}
#tip{position:absolute;pointer-events:none;display:none;background:var(--surface);
     border:1px solid var(--line-strong);border-radius:10px;padding:8px 10px;font-size:12px;
     max-width:340px;line-height:1.5;z-index:9}
#tip .k{font-size:10px;color:var(--muted);margin-bottom:8px}
#tip .l{font-size:10px;color:var(--muted);margin-top:8px;border-top:1px solid var(--line);padding-top:8px}
#side{position:absolute;right:0;top:0;bottom:0;width:340px;background:var(--surface);
      border-left:1px solid var(--line);display:none;flex-direction:column;z-index:6}
#side.open{display:flex}
#side .hd{display:flex;align-items:center;gap:8px;padding:10px 14px;
          border-bottom:1px solid var(--line)}
#side .hd .t{font-size:13px;font-weight:600;flex:1;word-break:break-all}
#side .bd{padding:10px 14px;overflow-y:auto;font-size:12px;line-height:1.7;color:var(--text);
          white-space:pre-wrap;word-break:break-word}
.x{display:inline-flex;align-items:center;justify-content:center;width:38px;height:38px;
   border-radius:19px;border:1px solid var(--line-strong);background:var(--surface);
   color:var(--muted);cursor:pointer;font-size:13px;font-family:inherit;flex:none}
.x:hover{color:var(--text);border-color:var(--muted)}
</style>
</head>
<body>
<div id="bar">
  <h1>md 관계도</h1>
  <div id="togs"></div>
  <input id="find" placeholder="노드 찾기" autocomplete="off">
  <div id="focusbar"></div>
  <div id="meta"></div>
  <div class="tog" id="btnReset" title="확대·이동 초기화 (R)">전체 보기</div>
  <div class="tog" id="btnArrows" title="연결 방향 화살표">방향</div>
  <div class="tog" id="btnScope" title="어느 AGENTS.md 지침 범위인지 색으로">범위색</div>
  <div class="tog" id="btnClean" title="기준을 지키는 md 만 보기">기준OK만</div>
  <div class="tog" id="btnQuality">품질</div>
  <div class="tog" id="btnChecks">검사 항목</div>
</div>
<div id="wrap">
  <canvas id="cv"></canvas>
  <div id="tip"></div>
  <div id="side">
    <div class="hd"><div class="t" id="sideT"></div><button class="x" id="sideX">닫기</button></div>
    <div class="bd" id="sideB"></div>
  </div>
</div>
<script>
const DATA = __DATA__;

// 유형 정의 — 색은 서로 구분되게, 채도는 낮게 (DESIGN.md: 무채색 위주 + 필요한 색만)
// 색은 CSS 변수에서 읽는다 (DESIGN.md §2: 값만 갈아 끼운다).
// 캔버스는 CSS 변수를 직접 못 쓰므로 한 번 읽어서 쓴다.
function cssVar(name, fallback){
  try {
    const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    return v || fallback;
  } catch (e) { return fallback; }
}
const C = {
  bg:    cssVar('--bg', '#0f0f10'),
  surface: cssVar('--surface', '#1c1c1e'),
  text:  cssVar('--text', '#f2f2f3'),
  muted: cssVar('--muted', '#9a9aa2'),
  lineStrong: cssVar('--line-strong', '#676767'),
  chipOnText: cssVar('--chip-on-text', '#ffffff'),
  pinned: cssVar('--k-d', '#e0a33e')
};

const KINDS = {
  A: {name:'규칙 참조', color:cssVar('--k-a','#f2f2f3'), on:true,  solid:true,  desc:'지침서가 "이걸 봐라"라고 시킨 것'},
  B: {name:'문서 참조', color:cssVar('--k-b','#6ea8ff'), on:true,  solid:true,  desc:'본문에서 "참고/자세히"로 단 것'},
  C: {name:'설명 언급', color:cssVar('--k-c','#8a8a94'), on:false, solid:true,  desc:'문장 속에 이름만 나온 것'},
  D: {name:'자리표시자', color:cssVar('--k-d','#e0a33e'), on:false, solid:true, desc:'NN_, * 같은 형식. 파일이 아님'},
  E: {name:'외부 경로',  color:cssVar('--k-e','#a06bd6'), on:false, solid:true, desc:'남의 저장소·다른 제품 파일'},
  F: {name:'없는 파일',  color:cssVar('--k-f','#e5484d'), on:false, solid:true, desc:'가리키는데 실제 없음'},
  G: {name:'연결 없음',  color:cssVar('--k-g','#5a5a62'), on:false, solid:true, desc:'어느 문서도 가리키지 않고 이 문서도 안 가리킴'}
};

const cv = document.getElementById('cv');
const ctx = cv.getContext('2d');
const tip = document.getElementById('tip');
const wrap = document.getElementById('wrap');

let W = 0, H = 0, DPR = Math.min(2, window.devicePixelRatio || 1);

// ---- 노드 배치: 지침 체인은 세로 기둥, 나머지는 고리
const nodes = DATA.nodes.map(n => ({...n, x:0, y:0, vx:0, vy:0, r:0, vis:false}));
const byKey = {};
nodes.forEach(n => byKey[n.key] = n);

function layout(){
  const chain = nodes.filter(n => n.chain);
  const cx = W * 0.42, cy = H * 0.5;
  chain.forEach((n,i) => {
    n.x = cx;
    n.y = cy - (chain.length-1)*34 + i*68;
    n.vx = n.vy = 0;
  });
  const rest = nodes.filter(n => !n.chain);
  const rings = [Math.min(W,H)*0.26, Math.min(W,H)*0.40, Math.min(W,H)*0.52];
  rest.forEach((n,i) => {
    const ring = i < 40 ? 0 : (i < 110 ? 1 : 2);
    const perRing = ring===0 ? 40 : (ring===1 ? 70 : rest.length-110);
    const idx = ring===0 ? i : (ring===1 ? i-40 : i-110);
    const a = (Math.PI*2*idx/Math.max(1,perRing)) + ring*0.6;
    n.x = cx + rings[ring]*Math.cos(a);
    n.y = cy + rings[ring]*Math.sin(a)*0.86;
    n.vx = n.vy = 0;
  });
  nodes.forEach(n => {
    const deg = n.indeg + n.outdeg;
    n.r = n.chain ? 9 : 4 + Math.min(9, Math.sqrt(deg)*2.2);
  });
}

// ---- 시뮬레이션 (간단한 스프링)
const visEdges = [];
function activeEdges(){
  return DATA.edges.filter(e => KINDS[e.k] && KINDS[e.k].on);
}

function tick(){
  const es = activeEdges();
  // 척력
  for (let i=0;i<nodes.length;i++){
    const a = nodes[i];
    if (!a.vis) continue;
    for (let j=i+1;j<nodes.length;j++){
      const b = nodes[j];
      if (!b.vis) continue;
      let dx = b.x-a.x, dy = b.y-a.y;
      let d2 = dx*dx+dy*dy;
      if (d2 < 1) { dx = (Math.random()-.5); dy = (Math.random()-.5); d2 = 1; }
      if (d2 > 40000) continue;
      const d = Math.sqrt(d2);
      const f = 340 / d2;
      const fx = dx/d*f, fy = dy/d*f;
      a.vx -= fx; a.vy -= fy;
      b.vx += fx; b.vy += fy;
    }
  }
  // 인력 (보이는 엣지만)
  for (const e of es){
    const a = byKey[e.s], b = byKey[e.t];
    if (!a || !b || !a.vis || !b.vis) continue;
    let dx = b.x-a.x, dy = b.y-a.y;
    const d = Math.max(1, Math.hypot(dx,dy));
    const f = (d - 90) * 0.0032;
    a.vx += dx/d*f; a.vy += dy/d*f;
    b.vx -= dx/d*f; b.vy -= dy/d*f;
  }
  // 위치 고정: 지침 체인 + 사용자가 드래그해서 붙박은 노드
  // (Obsidian 에는 이 기능이 없다 — 사용자 요청 2026-11-08.
  //  드래그한 자리에 그대로 있게 한다. 한 번 더 누르면 풀린다.)
  // 돌려주는 값: 눈에 보일 만큼(2px) 움직인 노드가 있었나.
  // 구조검토 실측: 0.02px 로는 안 멈춘다 — 노드가 0.29px 씩 영원히 진동해서
  // 200,000프레임(55분)을 돌려도 "움직였다"가 계속 참이다. 2.0px 이면 2~3초에 멈춘다.
  let moved = false;
  for (const n of nodes){
    if (!n.vis) continue;
    if (n.chain){ n.vx = n.vy = 0; continue; }
    if (n.pinned){ n.vx = n.vy = 0; continue; }
    n.vx *= 0.84; n.vy *= 0.84;
    const dx = Math.max(-3, Math.min(3, n.vx));
    const dy = Math.max(-3, Math.min(3, n.vy));
    if (Math.abs(dx) > 2.0 || Math.abs(dy) > 2.0) moved = true;
    n.x += dx;
    n.y += dy;
    n.x = Math.max(20, Math.min(W-20, n.x));
    n.y = Math.max(20, Math.min(H-20, n.y));
  }
  return moved;
}

// ---- 그리기
let hover = null, selected = null, dragNode = null;
let focus = null;          // 포커스 모드: 이 노드 + 직접 연결된 것만 보인다
let focusDepth = 1;        // 1 = 직접 이웃만, 2 = 이웃의 이웃까지
let view = {x:0, y:0, scale:1};
// Obsidian Graph view 의 Display > Arrows 토글에 해당
let ARROWS_ON = true;
// 노드 색을 "어느 AGENTS.md 지침 범위인가(scope)"로 칠할지 여부.
// 사용자 지적 2026-11-09: "거의 맨 상위 애들은 무슨 폴더인지 구분할 방법 없나"
let COLOR_BY_SCOPE = false;
// "기준을 지키는 md 만 보기" — 사용자 요청 2026-11-09.
// 품질 점수 100점(문제 0개)인 노드만 남긴다.
let ONLY_CLEAN = false;

// scope 별 색. :root 토큰을 읽고, 없으면 기본 팔레트를 만든다.
// 상위(넓은) 규칙일수록 밝게 — "맨 위가 중요하다"는 지적을 시각화한다.
const SCOPE_COLORS = {};
function scopeColor(scope){
  if (SCOPE_COLORS[scope]) return SCOPE_COLORS[scope];
  const palette = ['#f2f2f3', '#6ea8ff', '#4cc88c', '#e0a33e', '#a06bd6', '#e5484d', '#4cc8c8'];
  const keys = Object.keys(DATA.scopes || {});
  const i = keys.indexOf(scope);
  const c = palette[(i < 0 ? 0 : i) % palette.length];
  SCOPE_COLORS[scope] = c;
  return c;
}

// 포커스 대상 집합을 계산한다. null 이면 포커스 없음(전체).
function focusSet(){
  if (!focus) return null;
  const es = activeEdges();
  const keep = new Set([focus.key]);
  // 이웃 수집 (무방향으로 본다 — "연결된 것"이니까)
  let frontier = new Set([focus.key]);
  for (let d=0; d<focusDepth; d++){
    const next = new Set();
    for (const e of es){
      if (frontier.has(e.s)) next.add(e.t);
      if (frontier.has(e.t)) next.add(e.s);
    }
    for (const k of next) keep.add(k);
    frontier = next;
  }
  return keep;
}

// 지금 그려야 하는 엣지: 유형이 켜졌고, 포커스가 있으면 양 끝이 다 살아있는 것만
function drawnEdges(){
  const keep = focusSet();
  const es = activeEdges();
  if (!keep) return es;
  return es.filter(e => (keep.has(e.s) && keep.has(e.t)) &&
                        (e.s === focus.key || e.t === focus.key || focusDepth > 1));
}

function draw(){
  ctx.setTransform(DPR,0,0,DPR,0,0);
  ctx.clearRect(0,0,W,H);
  ctx.fillStyle = C.bg;
  ctx.fillRect(0,0,W,H);

  ctx.save();
  ctx.translate(view.x, view.y);
  ctx.scale(view.scale, view.scale);

  const keep = focusSet();
  const es = drawnEdges();
  // 엣지: 유형 색, 전부 실선 (요구: C·D 도 켜면 실선)
  // Obsidian Graph view 의 "Arrows" 옵션에 해당 — 방향을 보여준다.
  // 사용자 지적 2026-11-09: "A가 B를 가리킨다"와 "B가 A를 가리킨다"가
  // 화면에서 똑같이 보였다.
  ctx.lineWidth = 1;
  for (const e of es){
    const a = byKey[e.s], b = byKey[e.t];
    if (!a || !b || !a.vis || !b.vis) continue;
    const k = KINDS[e.k];
    const hot = hover && (hover.key===e.s || hover.key===e.t);
    const onFocus = focus && (e.s===focus.key || e.t===focus.key);
    ctx.strokeStyle = k.color;
    ctx.globalAlpha = onFocus ? 0.95
                    : hot ? 0.85
                    : (e.k==='A' ? 0.5 : (e.k==='B' ? 0.34 : 0.18));
    ctx.lineWidth = onFocus ? 2 : (hot ? 1.6 : 1);
    ctx.beginPath();
    ctx.moveTo(a.x, a.y);
    ctx.lineTo(b.x, b.y);
    ctx.stroke();

    // 화살표 머리 — 선 끝(대상 쪽)에서 조금 앞에 붙인다.
    // 노드 원 밖으로 나오게 해서 점이 가리지 않게 한다.
    if (ARROWS_ON){
      const dx = b.x - a.x, dy = b.y - a.y;
      const len = Math.hypot(dx, dy);
      if (len > (a.r + b.r + 6)){
        const ux = dx/len, uy = dy/len;
        // 화살촉 위치: 대상 원 테두리 바로 앞
        const tipX = b.x - ux * (b.r + 2);
        const tipY = b.y - uy * (b.r + 2);
        const sz = onFocus ? 7 : (hot ? 6 : 4.5);
        // 화살촉 두 갈래
        ctx.beginPath();
        ctx.moveTo(tipX, tipY);
        ctx.lineTo(tipX - ux*sz - uy*sz*0.55, tipY - uy*sz + ux*sz*0.55);
        ctx.moveTo(tipX, tipY);
        ctx.lineTo(tipX - ux*sz + uy*sz*0.55, tipY - uy*sz - ux*sz*0.55);
        ctx.lineWidth = onFocus ? 2 : 1.2;
        ctx.stroke();
      }
    }
  }
  ctx.globalAlpha = 1;

  // 노드
  for (const n of nodes){
    if (!n.vis) continue;
    if (keep && !keep.has(n.key)) continue;
    const isHover = hover && hover.key === n.key;
    const isSel = selected && selected.key === n.key;
    const isFocus = focus && focus.key === n.key;
    const isPinned = n.pinned && !n.chain;
    const sc = COLOR_BY_SCOPE ? scopeColor(n.scope) : null;
    ctx.beginPath();
    ctx.arc(n.x, n.y, isFocus ? n.r + 3 : n.r, 0, Math.PI*2);
    // scope 색 모드면 노드를 그 색으로 채운다 (안쪽은 어둡게 유지해 글자가 읽히게)
    ctx.fillStyle = sc ? sc : C.surface;
    ctx.fill();
    if (sc){
      // 채운 위에 어두운 점을 하나 더 얹어 테두리만 색이 남게 한다
      ctx.beginPath();
      ctx.arc(n.x, n.y, Math.max(1, (isFocus ? n.r + 3 : n.r) - 3), 0, Math.PI*2);
      ctx.fillStyle = C.surface;
      ctx.fill();
    }
    ctx.lineWidth = isFocus ? 3 : (n.chain ? 2 : (isPinned ? 2 : 1));
    ctx.strokeStyle = isFocus ? C.chipOnText
                    : isPinned ? C.pinned
                    : sc ? sc
                    : (isSel ? C.chipOnText : (isHover ? C.text :
                      (n.chain ? C.text : C.lineStrong)));
    ctx.stroke();
  }
  // 이름표: 지침 + 호버/선택 + (확대했을 때 전부)
  // Obsidian 의 "Text fade threshold" 에 해당 — 작게 보이면 글자를 숨긴다.
  const showAllNames = view.scale >= 1.25;
  ctx.font = '10px Pretendard, system-ui, sans-serif';
  for (const n of nodes){
    if (!n.vis) continue;
    const isChain = n.chain;
    const isHov = (hover && hover.key===n.key) || (selected && selected.key===n.key);
    // ⚠️ 위 노드 반복문(:770)의 isFocus 는 **그 블록 안의 const** 라 여기서 안 보인다.
    //    2026-11-09 실측: 이 줄이 없어서 draw() 가 ReferenceError 로 죽었고,
    //    loop() 가 상단 버튼 배선보다 앞이라 버튼 8개·검색·Esc 가 전부 안 붙었다.
    //    증상은 "동그라미는 그려지는데 이름표가 없고 아무것도 안 눌린다".
    const isFocus = focus && focus.key === n.key;
    if (!(isChain || isHov || showAllNames)) continue;
    ctx.fillStyle = isHov ? C.text : C.muted;
    // 지침 체인은 "어느 폴더인지"까지, 그리고 전부 n/n(검사 통과 수)을 붙인다.
    // 사용자 요청 2026-11-09: "무엇을 안 지키는지 볼 수 있게 n/n 하고"
    const q = DATA.quality ? DATA.quality[n.key] : null;
    const qn = q ? `  ${q.pass}/${q.total}` : "";
    const label = (isChain && n.scope) ? `${n.name}  ·  ${n.scope}${qn}` : `${n.name}${qn}`;
    ctx.fillText(label, n.x + (isFocus ? n.r + 8 : n.r + 5), n.y + 3);
  }
  ctx.restore();
}

// ---- 루프
// 성능 (2026-11-08 구조검토 실측): 처음엔 매 프레임 nodes.map().join('|') 을
// 두 번 만들어 비교했다. 측정 결과 이득 0, 손해 프레임당 34us (문자열 비교가
// tick() 의 136%). 노드가 영원히 0.29px 씩 진동해서 두 문자열이 절대 같아지지
// 않기 때문이다(30,000프레임 일치 0회). 그래서 문자열 비교를 지우고,
// tick() 이 "움직였나"를 직접 돌려주게 했다 — vx/vy 를 이미 손에 쥐고 있으니
// 이동량은 그 자리에서 공짜로 알 수 있다.
let raf = null;
let needsDraw = true;
let physicsOn = true;
let stillFrames = 0;

// 그리기만 깨운다 (화면 표시가 바뀌었을 때: 호버, 확대, 패널 열기).
// 물리는 건드리지 않는다 — 이미 멈췄으면 계속 멈춰 있는 게 맞다.
function markDraw(){ needsDraw = true; }

// 물리까지 다시 켠다 (배치가 바뀌었을 때: 필터, 포커스, 검색, 고정 해제).
// 구조검토 지적: 예전엔 needsDraw 를 켜는 곳이 if(physicsOn) 안에만 있어서
// 물리가 멈추면 화면이 영원히 얼어붙었다. 이제 입력 이벤트가 직접 켠다.
function markDirty(){ needsDraw = true; physicsOn = true; stillFrames = 0; }

function loop(){
  if (physicsOn){
    if (tick()){
      stillFrames = 0;
      needsDraw = true;
    } else {
      stillFrames++;
      if (stillFrames > 20) physicsOn = false;
    }
  }
  if (needsDraw){
    draw();
    needsDraw = false;
  }
  raf = requestAnimationFrame(loop);
}

// ---- 칩 (유형 ON/OFF)
function buildToggles(){
  const box = document.getElementById('togs');
  box.innerHTML = '';
  const order = ['A','B','C','D','E','F','G'];
  for (const k of order){
    const def = KINDS[k];
    const cnt = DATA.bucket[k] || 0;
    if (!cnt) continue;
    const el = document.createElement('div');
    el.className = 'tog' + (def.on ? ' on' : ' off');
    el.innerHTML = `<span class="dot" style="background:${def.color}"></span>` +
                   `<span>${def.name}</span><span class="count">${cnt}</span>`;
    el.title = def.desc;
    el.onclick = () => {
      KINDS[k].on = !KINDS[k].on;
      el.classList.toggle('on', KINDS[k].on);
      el.classList.toggle('off', !KINDS[k].on);
      applyVisibility();
      updateMeta();
    };
    box.appendChild(el);
  }
}

// 노드 표시 규칙: 켜진 엣지에 걸린 노드만 보인다.
// UX 검토 문제 12: 연결이 하나도 없는 md 9개는 어떤 필터를 켜도 안 보였다.
// → "연결 없음" 유형(orphan)으로 따로 보이게 한다.
function applyVisibility(){
  const es = activeEdges();
  const live = new Set();
  for (const e of es){ live.add(e.s); live.add(e.t); }
  for (const n of nodes){
    // "기준OK만" 켜면 문제 0개(n/n)인 문서만 남긴다 (사용자 요청 2026-11-09)
    if (ONLY_CLEAN){
      const q = DATA.quality && DATA.quality[n.key];
      if (!q || q.failed.length > 0){ n.vis = false; continue; }
    }
    if (n.chain){ n.vis = true; continue; }
    if (DATA.edges.length && !hasAnyEdge(n.key)){
      n.vis = KINDS.G ? KINDS.G.on : false;   // 고아 노드
      n.orphan = true;
      continue;
    }
    n.vis = live.has(n.key);
  }
  markDirty();
}

// 이 노드에 연결이 하나라도 있나 (유형 무관)
function hasAnyEdge(key){
  for (const e of DATA.edges){
    if (e.s === key || e.t === key) return true;
  }
  return false;
}

function updateMeta(){
  const on = Object.keys(KINDS).filter(k => KINDS[k].on);
  const es = drawnEdges().length;
  const keep = focusSet();
  const vn = nodes.filter(n => n.vis && (!keep || keep.has(n.key))).length;
  let s = `노드 ${vn} · 연결 ${es} · 켠 유형 ${on.length}`;
  if (focus) s = `포커스 ${focus.name} · ` + s;
  // 생성 시각 — 옛 HTML 을 열고 "고쳤는데 안 된다"고 오판하지 않게 (2026-11-09)
  if (DATA.generated){
    const hhmm = DATA.generated.slice(11, 16);
    s += `  ·  생성 ${hhmm}`;
  }
  document.getElementById('meta').textContent = s;
}

// ---- 포커스 바 (Obsidian Local Graph 의 depth 슬라이더에 해당)
function updateFocusBar(){
  const fb = document.getElementById('focusbar');
  fb.innerHTML = '';
  if (!focus) return;
  const lab = document.createElement('div');
  lab.className = 'tog on';
  lab.style.cursor = 'default';
  lab.textContent = `Local: ${focus.name}`;
  fb.appendChild(lab);
  for (const d of [1,2,3]){
    const b = document.createElement('div');
    b.className = 'tog' + (focusDepth === d ? ' on' : ' off');
    b.textContent = `깊이 ${d}`;
    b.onclick = () => { focusDepth = d; updateFocusBar(); updateMeta(); markDirty(); };
    fb.appendChild(b);
  }
  const x = document.createElement('div');
  x.className = 'tog';
  x.textContent = '포커스 끄기';
  x.onclick = () => { focus = null; updateFocusBar(); updateMeta(); };
  fb.appendChild(x);
}

// ---- 노드 찾기 (Obsidian 의 Search files 필터에 해당)
function gotoNode(q){
  const s = (q||'').trim().toLowerCase();
  if (!s) return;
  const hits = nodes.filter(n => n.key.toLowerCase().includes(s));
  if (!hits.length) return;
  // 가장 짧은 이름 = 가장 직접적인 매치
  hits.sort((a,b) => a.key.length - b.key.length);
  const n = hits[0];
  // UX 검토 문제 4: 지금 필터에 걸려 안 보이는 노드를 찾으면 카메라만
  // 텅 빈 곳으로 갔었다. 그 노드에 연결된 유형을 자동으로 켜서 보이게 한다.
  if (!n.vis){
    for (const e of DATA.edges){
      if (e.s === n.key || e.t === n.key){
        if (KINDS[e.k]) KINDS[e.k].on = true;
      }
    }
    buildToggles();
    applyVisibility();
  }
  selected = n;
  renderSide(n);
  document.getElementById('side').classList.add('open');
  view.x = W/2 - n.x*view.scale;
  view.y = H/2 - n.y*view.scale;
  hover = n;
}


// ---- 좌표 변환
function toWorld(px, py){
  return {x: (px - view.x)/view.scale, y: (py - view.y)/view.scale};
}
function pick(px, py){
  const w = toWorld(px, py);
  let best = null, bd = 1e9;
  for (const n of nodes){
    if (!n.vis) continue;
    const keep = focusSet();
    if (keep && !keep.has(n.key)) continue;
    // DESIGN.md §8 MUST: 누르는 영역 최소 24×24px.
    // 보이는 점은 작아도 판정 반경을 n.r+10 으로 넓혀 지름 24px 이상 확보한다.
    const hit = Math.max(n.r + 10, 13);
    const d = Math.hypot(n.x-w.x, n.y-w.y);
    if (d < hit && d < bd){ bd = d; best = n; }
  }
  return best;
}

// ---- 이벤트
cv.addEventListener('mousemove', e => {
  const r = cv.getBoundingClientRect();
  const px = e.clientX-r.left, py = e.clientY-r.top;
  if (dragNode){
    const w = toWorld(px, py);
    dragNode.x = w.x; dragNode.y = w.y;
    dragNode._moved = true;
    dragNode.vx = dragNode.vy = 0;
    clearTimeout(pressTimer);   // 움직였으면 꾸욱 취소
    return;
  }
  const n = pick(px, py);
  const changed = (n && (!hover || hover.key !== n.key)) || (!n && hover);
  if (changed){
    hover = n;
    markDraw();   // 호버 강조는 그리기만이면 된다 (물리는 그대로)
    if (n){
      const outs = DATA.edges.filter(x => x.s===n.key && KINDS[x.k] && KINDS[x.k].on);
      const ins  = DATA.edges.filter(x => x.t===n.key && KINDS[x.k] && KINDS[x.k].on);
      let h = `<div class="k">${n.dir} · ${n.words}단어</div><div>${n.key}</div>`;
      if (ins.length) h += `<div class="l">나를 가리킴 ${ins.length}</div>`;
      if (outs.length) h += `<div class="l">내가 가리킴 ${outs.length}</div>`;
      tip.innerHTML = h;
      tip.style.display = 'block';
    } else tip.style.display = 'none';
  }
  if (n){
    const tw = tip.offsetWidth, th = tip.offsetHeight;
    tip.style.left = Math.min(px+14, W-tw-8) + 'px';
    tip.style.top  = Math.min(py+14, H-th-8) + 'px';
  }
  cv.style.cursor = n ? 'pointer' : 'grab';
});

// 꾸욱 누르기(500ms) = 그 노드와 연결된 것만 보기.
// 사용자 요청 2026-11-09: "꾸욱 누르면 그 애랑 연결된 애들만 보이게 되려나?"
// Obsidian Local Graph 를 손가락 하나로 하는 셈이다.
let pressTimer = null;
let pressFired = false;
const LONG_PRESS_MS = 500;

cv.addEventListener('mousedown', e => {
  const r = cv.getBoundingClientRect();
  const n = pick(e.clientX-r.left, e.clientY-r.top);
  pressFired = false;
  if (n){
    dragNode = n;
    dragNode._moved = false;
    // 문제 3(UX 검토): 드래그하는 동안 물리가 노드를 잡아당겨 커서에서 도망갔다
    // (측정: 2초에 최대 225px). 잡는 순간부터 고정한다.
    dragNode.pinned = true;
    dragNode.vx = dragNode.vy = 0;
    cv.classList.add('drag');

    // 꾸욱 누르기 타이머 — 움직이면 취소된다(아래 mousemove 에서)
    clearTimeout(pressTimer);
    pressTimer = setTimeout(() => {
      if (dragNode && !dragNode._moved){
        pressFired = true;
        focus = dragNode;
        focusDepth = 1;
        updateFocusBar();
        updateMeta();
        markDirty();
        selected = dragNode;
        renderSide(dragNode);
      }
    }, LONG_PRESS_MS);
  }
});

window.addEventListener('mouseup', () => {
  clearTimeout(pressTimer);
  // 드래그를 실제로 했으면 그 자리에 그대로 둔다 (요청: "거기 있게")
  // 실제로 안 움직였으면(그냥 클릭) 고정을 풀어준다 — 클릭으로 고정 해제가
  // 되도록. 예전엔 _justDragged 플래그로 click 을 무시했는데, 그 플래그가
  // 안 지워져서 "다음 클릭이 조용히 사라지는" 버그가 있었다(UX 검토 2026-11-08).
  // 이제 플래그 대신 "이번 누름에서 실제로 움직였나"로만 판정한다.
  if (dragNode && !dragNode._moved && !pressFired){
    dragNode.pinned = false;
  }
  dragNode = null;
  cv.classList.remove('drag');
});

cv.addEventListener('click', e => {
  const r = cv.getBoundingClientRect();
  const n = pick(e.clientX-r.left, e.clientY-r.top);
  if (!n) return;
  // 고정 해제는 mouseup 에서 이미 처리한다(실제로 안 움직였으면 pinned=false).
  // 여기서는 "지침 체인 노드"만 예외로 풀 수 있게 한다 — 체인은 드래그로
  // 옮겨지고 고정 표시도 되는데 클릭으로 안 풀리면 규칙이 달라 보인다(UX 검토).
  if (n.pinned && n.chain){
    n.pinned = false;
  }
  selected = n;
  renderSide(n);
  document.getElementById('side').classList.add('open');
});

// 오른쪽 패널: 연결 목록을 누르면 그 노드로 이동 + 가리킨 줄로 이동
// jumpLine: 대상 파일 본문에서 "이 파일을 언급한 줄" 의 인덱스 (없으면 null)
function renderSide(n, jumpLine){
  const keep = focusSet();
  const outs = DATA.edges.filter(x => x.s===n.key && KINDS[x.k] && KINDS[x.k].on);
  const ins  = DATA.edges.filter(x => x.t===n.key && KINDS[x.k] && KINDS[x.k].on);
  document.getElementById('sideT').textContent = n.name;
  const B = document.getElementById('sideB');
  B.innerHTML = '';

  const head = document.createElement('div');
  head.className = 'kv';
  head.textContent = `${n.dir} · ${n.words}단어`;
  B.appendChild(head);

  const mk = (arr, label) => {
    const box = document.createElement('div');
    if (!arr.length) return box;
    const t = document.createElement('div');
    t.className = 'kv';
    t.textContent = `${label} ${arr.length}`;
    box.appendChild(t);
    for (const e of arr.slice(0, 40)){
      const other = (e.s === n.key) ? e.t : e.s;
      const row = document.createElement('div');
      row.className = 'row';
      const dot = document.createElement('span');
      dot.className = 'dot';
      dot.style.background = KINDS[e.k].color;
      const nm = document.createElement('span');
      nm.className = 'nm';
      nm.textContent = other;
      row.appendChild(dot);
      row.appendChild(nm);
      row.title = KINDS[e.k].name + ' · ' + (e.line || '');
      row.onclick = () => {
        const o = byKey[other];
        if (!o) return;
        selected = o;
        // "가리킨다 -> 그 부분으로 이동":
        // 지금 노드가 저 파일을 언급한 줄(e.line)을 저 파일 본문에서 찾아 스크롤한다.
        const jl = findMentionLine(o.body, n.base || n.name, e.line);
        renderSide(o, jl);
        view.x = W/2 - o.x*view.scale;
        view.y = H/2 - o.y*view.scale;
      };
      box.appendChild(row);
    }
    return box;
  };
  B.appendChild(mk(outs, '내가 가리킴'));
  B.appendChild(mk(ins, '나를 가리킴'));

  // ---- 본문 (전체). 가리킨 줄로 이동할 수 있게 한다.
  const body = document.createElement('div');
  body.className = 'kv';
  body.style.marginTop = '12px';
  body.textContent = '본문';
  B.appendChild(body);

  const pre = document.createElement('div');
  pre.className = 'body';
  pre.id = 'bodyBox';

  // 본문을 줄 단위로 그린다. jump 할 줄에 표시를 달 수 있다.
  const lines = (n.body || '').split('\n');
  lines.forEach((ln, i) => {
    const d = document.createElement('div');
    d.className = 'ln';
    d.dataset.i = String(i);
    d.textContent = ln || ' ';
    pre.appendChild(d);
  });
  B.appendChild(pre);

  // 어디로 갈지 알려주는 안내 (요청 2026-11-08: "가리킨다 -> 그 부분으로 이동")
  if (jumpLine !== null && jumpLine !== undefined){
    const note = document.createElement('div');
    note.className = 'kv';
    note.style.color = '#6ea8ff';
    note.textContent = `↳ 가리킨 줄로 이동 (${jumpLine + 1}번째 줄)`;
    B.insertBefore(note, body);
    setTimeout(() => scrollToLine(pre, jumpLine), 30);
  }

  // 포커스 버튼 — DESIGN.md §5 "같은 일을 하는 버튼 두 개" 금지.
  // 끄기는 위 바(focusbar)에만 둔다. 여기엔 "이 노드만 보기"만 두고,
  // 이미 이 노드가 포커스면 버튼을 숨긴다(위 바에 끄기가 있으니까).
  if (!(focus && focus.key === n.key)){
    const btn = document.createElement('button');
    btn.className = 'tog on';
    btn.style.marginTop = '12px';
    btn.textContent = '이 노드만 보기';
    btn.onclick = () => { toggleFocus(n); renderSide(n); };
    B.appendChild(btn);
  }
}

// 본문에서 특정 줄로 스크롤 + 잠깐 강조
function scrollToLine(box, idx){
  const el = box.querySelector(`.ln[data-i="${idx}"]`);
  if (!el) return;
  el.classList.add('hit');
  el.scrollIntoView({block:'center', behavior:'smooth'});
  setTimeout(() => el.classList.remove('hit'), 2200);
}

// 가리킨 쪽(대상 파일)의 어느 줄이 "이 파일을 언급"하는지 찾는다
function findMentionLine(targetBody, srcName, refStr){
  const lines = (targetBody || '').split('\n');
  const needles = [srcName, refStr].filter(Boolean);
  for (let i = 0; i < lines.length; i++){
    for (const nd of needles){
      if (nd && lines[i].includes(nd)) return i;
    }
  }
  return null;
}

function toggleFocus(n){
  focus = (focus && focus.key === n.key) ? null : n;
  updateFocusBar();
  updateMeta();
  markDirty();
}

document.getElementById('sideX').onclick = () => {
  document.getElementById('side').classList.remove('open');
  selected = null;
};

// 휠 확대
cv.addEventListener('wheel', e => {
  e.preventDefault();
  const r = cv.getBoundingClientRect();
  const px = e.clientX-r.left, py = e.clientY-r.top;
  const w = toWorld(px, py);
  const f = e.deltaY < 0 ? 1.12 : 1/1.12;
  view.scale = Math.max(0.25, Math.min(3.5, view.scale*f));
  view.x = px - w.x*view.scale;
  view.y = py - w.y*view.scale;
  markDraw();   // 확대/축소는 그리기만
}, {passive:false});

// 드래그로 화면 이동
let panning = null;
cv.addEventListener('mousedown', e => {
  const r = cv.getBoundingClientRect();
  if (!pick(e.clientX-r.left, e.clientY-r.top)) panning = {x:e.clientX, y:e.clientY, vx:view.x, vy:view.y};
});
cv.addEventListener('mousemove', e => {
  if (panning){
    view.x = panning.vx + (e.clientX - panning.x);
    view.y = panning.vy + (e.clientY - panning.y);
    markDraw();   // 화면 이동은 그리기만
  }
});
window.addEventListener('mouseup', () => { panning = null; });

function resize(){
  const r = wrap.getBoundingClientRect();
  W = r.width; H = r.height;
  cv.width = W*DPR; cv.height = H*DPR;
  cv.style.width = W+'px'; cv.style.height = H+'px';
}
window.addEventListener('resize', () => {
  // UX 검토 문제 9: 애써 고정한 노드가 창 크기를 바꾸면 전부 원래 자리로
  // 튀었다(layout() 재호출 때문). 이제 크기만 다시 재고, 이미 배치된 노드는
  // 그대로 둔다. 아직 배치 전(첫 호출)일 때만 layout() 한다.
  resize();
  if (!nodes.length || nodes.every(n => n.x === 0 && n.y === 0)) layout();
});

// ---- 시작
resize();
layout();
buildToggles();
applyVisibility();
updateFocusBar();
updateMeta();
loop();

// 검색창
const findEl = document.getElementById('find');
findEl.addEventListener('keydown', e => {
  if (e.key === 'Enter') gotoNode(findEl.value);
});
findEl.addEventListener('input', e => {
  const s = e.target.value.trim().toLowerCase();
  if (s.length >= 2) gotoNode(s);
});

// ---- Esc (UX 검토 문제 7): 창 닫기 → 포커스 끄기 → 고정 전체 해제 순
window.addEventListener('keydown', e => {
  // 검색창에 글자를 치는 중이면 단축키를 먹지 않는다
  const inInput = document.activeElement && document.activeElement.id === 'find';
  if (e.key === 'r' || e.key === 'R'){
    if (inInput) return;
    view.x = 0; view.y = 0; view.scale = 1;
    markDraw();
    return;
  }
  if (e.key !== 'Escape') return;
  const side = document.getElementById('side');
  if (side.classList.contains('open')){
    side.classList.remove('open');
    selected = null;
    return;
  }
  if (focus){
    focus = null;
    updateFocusBar();
    updateMeta();
    return;
  }
  let anyPinned = false;
  for (const n of nodes){ if (n.pinned){ n.pinned = false; anyPinned = true; } }
  if (anyPinned) markDirty();
});

// ---- 전체 보기 (Cosma 의 Reset 버튼 + R 키)// 기능검토 상 #11: 휠로 확대하다 길을 잃으면 F5 말고 돌아올 길이 없었다.
const btnReset = document.getElementById('btnReset');
btnReset.onclick = () => {
  view.x = 0; view.y = 0; view.scale = 1;
  markDraw();
};
const btnArrows = document.getElementById('btnArrows');
btnArrows.classList.add(ARROWS_ON ? 'on' : 'off');
btnArrows.onclick = () => {
  ARROWS_ON = !ARROWS_ON;
  btnArrows.classList.toggle('on', ARROWS_ON);
  btnArrows.classList.toggle('off', !ARROWS_ON);
  markDraw();
};

// ---- 범위색 토글 (어느 AGENTS.md 지침 범위인지)
const btnScope = document.getElementById('btnScope');
btnScope.classList.add('off');
btnScope.onclick = () => {
  COLOR_BY_SCOPE = !COLOR_BY_SCOPE;
  btnScope.classList.toggle('on', COLOR_BY_SCOPE);
  btnScope.classList.toggle('off', !COLOR_BY_SCOPE);
  markDraw();
};

// ---- 기준OK만 (문제 0개인 md 만 보기) — 사용자 요청 2026-11-09
const btnClean = document.getElementById('btnClean');
btnClean.classList.add('off');
btnClean.onclick = () => {
  ONLY_CLEAN = !ONLY_CLEAN;
  btnClean.classList.toggle('on', ONLY_CLEAN);
  btnClean.classList.toggle('off', !ONLY_CLEAN);
  applyVisibility();
  updateMeta();
};

// ---- 품질 패널: md 별 n/n + 무엇을 못 지켰나
const btnQuality = document.getElementById('btnQuality');
btnQuality.onclick = () => {
  const side = document.getElementById('side');
  if (side.classList.contains('open') &&
      document.getElementById('sideT').textContent === '품질') {
    side.classList.remove('open');
    return;
  }
  document.getElementById('sideT').textContent = '품질';
  const B = document.getElementById('sideB');
  B.innerHTML = '';
  const Q = DATA.quality || {};
  const rows = Object.keys(Q).map(k => ({ k, ...Q[k] }));
  // 문제 있는 것부터, 그다음 이름순
  rows.sort((a, b) => (a.pass - b.pass) || a.k.localeCompare(b.k));
  const bad = rows.filter(r => r.failed.length > 0 && !r.snapshot);
  const snap = rows.filter(r => r.failed.length > 0 && r.snapshot);
  // 낡은 사본 — 원본이 더 최신인 스냅샷. 실패 배지가 아니라 별도 절로 보여준다.
  // (2026-11-09: c4-architecture 사본이 1,098 B 뒤처져 있었는데 아무 표시가 없었다)
  const stale = rows.filter(r => r.stale);
  const good = rows.filter(r => r.failed.length === 0 && !r.stale);

  const head = document.createElement('div');
  head.className = 'kv';
  head.textContent =
    `기준 통과 ${good.length} · 문제 ${bad.length} · 스냅샷 ${snap.length}` +
    (stale.length ? ` · 낡은 사본 ${stale.length}` : '') +
    ` · 전체 ${rows.length}`;
  B.appendChild(head);

  const mkRow = (r) => {
    const box = document.createElement('div');
    box.className = 'chk';
    const t = document.createElement('div');
    t.className = 'chk-t';
    // n/n 을 앞에 크게
    const nn = document.createElement('span');
    nn.className = 'nn ' + (r.failed.length ? 'nn-bad' : 'nn-ok');
    nn.textContent = `${r.pass}/${r.total}`;
    t.appendChild(nn);
    const nm = document.createElement('span');
    nm.textContent = ' ' + r.k;
    t.appendChild(nm);
    box.appendChild(t);
    if (r.failed.length){
      const f = document.createElement('div');
      f.className = 'chk-meta chk-o';
      f.textContent = '못 지킴: ' + r.failed.join(' · ');
      box.appendChild(f);
    }
    // 낡은 사본은 실패가 아니라 "원본이 더 최신"이라는 별개 사실이다.
    // 실패 배지에 섞으면 "내가 뭘 잘못했나"로 오해된다.
    if (r.stale){
      const s = document.createElement('div');
      s.className = 'chk-meta chk-o';
      s.textContent = '낡은 사본 — 원본 ' + (r.stale_src || '') + ' 이 더 최신이다';
      box.appendChild(s);
    }
    if (r.issues && r.issues.length){
      const iv = document.createElement('div');
      iv.className = 'chk-meta';
      iv.textContent = r.issues.join(' / ');
      box.appendChild(iv);
    }
    box.onclick = () => {
      const nd = byKey[r.k];
      if (!nd) return;
      selected = nd;
      renderSide(nd);
    };
    return box;
  };

  if (bad.length){
    const h = document.createElement('div');
    h.className = 'kv';
    h.textContent = '문제 있는 md (고칠 곳)';
    B.appendChild(h);
    bad.forEach(r => B.appendChild(mkRow(r)));
  }
  if (snap.length){
    const h = document.createElement('div');
    h.className = 'kv';
    h.textContent = '스냅샷 (원본이 문제 — 여기서 고치지 않는다)';
    B.appendChild(h);
    snap.forEach(r => B.appendChild(mkRow(r)));
  }
  if (stale.length){
    const h = document.createElement('div');
    h.className = 'kv';
    h.textContent = '낡은 사본 (원본이 더 최신 — sync-dsh.ps1 을 다시 돌린다)';
    B.appendChild(h);
    stale.forEach(r => B.appendChild(mkRow(r)));
  }
  if (good.length){
    const h = document.createElement('div');
    h.className = 'kv';
    h.textContent = '기준 통과';
    B.appendChild(h);
    good.forEach(r => B.appendChild(mkRow(r)));
  }
  side.classList.add('open');
};

// ---- 검사 항목 패널 (요청 2026-11-08: "검사기가 뭘 검사하는지도 여기서")
// DATA.checks 는 _docs_check.ps1 을 실제로 읽어서 뽑은 것이라,
// 검사기에 절을 추가하면 여기에도 자동으로 뜬다.
const btnChecks = document.getElementById('btnChecks');
btnChecks.onclick = () => {
  const side = document.getElementById('side');
  if (side.classList.contains('open') && document.getElementById('sideT').textContent === '검사기') {
    side.classList.remove('open');
    return;
  }
  document.getElementById('sideT').textContent = '검사기';
  const B = document.getElementById('sideB');
  B.innerHTML = '';
  const head = document.createElement('div');
  head.className = 'kv';
  head.textContent = `_check.bat 이 실행하는 항목 ${DATA.checks.length}개`;
  B.appendChild(head);
  for (const c of DATA.checks){
    const box = document.createElement('div');
    box.className = 'chk';
    const t = document.createElement('div');
    t.className = 'chk-t';
    t.textContent = `${c.n}  ${c.t}`;
    box.appendChild(t);
    if (c.d){
      const dd = document.createElement('div');
      dd.className = 'chk-d';
      dd.textContent = c.d;
      box.appendChild(dd);
    }
    // "어느 파일들의 무엇을 보는가" — 사용자 요청 2026-11-09
    const mkRow = (label, items, cls) => {
      if (!items || !items.length) return;
      const r = document.createElement('div');
      r.className = 'chk-meta ' + (cls || '');
      r.textContent = `${label}: ${items.join(' · ')}`;
      box.appendChild(r);
    };
    mkRow('대상', c.targets, 'chk-tgt');
    mkRow('보는 것', c.measures, 'chk-m');
    mkRow('결과', c.outcomes, 'chk-o');
    B.appendChild(box);
  }
  const foot = document.createElement('div');
  foot.className = 'kv';
  foot.style.marginTop = '12px';
  foot.textContent = '실행: _check.bat';
  B.appendChild(foot);
  side.classList.add('open');
};
</script>
</body>
</html>
"""


def score_docs(nodes, edges):
    """md 하나하나가 "기준을 지키나"를 검사해서 점수를 매긴다.

    사용자 요청 2026-11-09: "좋은 md 기준(전역 적용?) 되고 있는 건 따로
    내가 빼서 볼 수 있게".

    검사 4종:
      1. 길이   — **지침서(AGENTS.md/SKILL.md)만** 상한이 있다.
                  전역 2080 / 하위 600 단어. 기록·자료는 길어도 정상이다.
      2. BOM    — 있으면 .bat 이 안 돌아간다 (전 파일 적용)
      3. 중복   — 같은 내용이 두 곳에 있으면 하나는 썩는다.
                  단 **자동 스냅샷(_dsh_config)은 의도된 사본**이라 제외.
      4. 죽은참조 — 가리키는 파일이 실제 없으면 링크가 깨진다

    2026-11-09 1차 실행에서 오탐이 나와서 위 1·3번을 고쳤다:
      - 기록·과제자료를 "길이 초과"로 잡았다 (기준에 없던 규칙을 내가 만든 것)
      - _dsh_config 의 AGENTS.md 를 "중복"으로 잡았다 (sync 스크립트 결과물)
    """
    from collections import defaultdict
    import hashlib

    # ---- 스냅샷 낡음 판정 (2026-11-09 추가)
    # WHY: _dsh_config 는 sync-dsh.ps1 이 ~/.dsh·~/.agents 에서 복사한 사본이다.
    #   사본이 낡으면 화면에 "옛 판본이 진짜인 것처럼" 보인다. 실제로 그랬다:
    #   c4-architecture 사본 5,809 B vs 원본 6,907 B — 원본이 1,098 B 더 최신.
    #   원본은 ROOT 밖(~/.agents)이라 노드가 아니다. 그래서 파일 시스템으로 직접
    #   비교한다. 원본이 없으면(배포판) 판정하지 않는다 — "모른다"가 맞다.
    def stale_snapshots():
        """{스냅샷 key: (원본경로표시, 사본바이트, 원본바이트)} — 낡은 것만."""
        pairs = {
            "_dsh_config\\AGENTS.md": HOME / ".dsh" / "AGENTS.md",
        }
        skills_src = HOME / ".agents" / "skills"
        if skills_src.is_dir():
            for d in sorted(skills_src.iterdir()):
                src = d / "SKILL.md"
                if d.is_dir() and src.exists():
                    pairs[f"_dsh_config\\skills\\{d.name}\\SKILL.md"] = src
        stale = {}
        for key, src in pairs.items():
            if key not in nodes or not src.exists():
                continue
            dst = ROOT / key            # 사본은 ROOT 안에 있다
            if not dst.exists():
                continue
            try:
                dst_bytes = dst.stat().st_size
                src_bytes = src.stat().st_size
            except OSError:
                continue
            # BOM·개행 차이는 있을 수 있으니 5% 이상 차이날 때만 "낡음".
            if src_bytes > 0 and abs(src_bytes - dst_bytes) / src_bytes > 0.05:
                try:
                    shown = "~/" + src.relative_to(HOME).as_posix()
                except ValueError:
                    shown = src.name
                stale[key] = (shown, dst_bytes, src_bytes)
        return stale

    stale_map = stale_snapshots()

    # 중복 판정용 해시. 파이썬 내장 hash() 는 실행마다 값이 바뀌므로 md5 로 고정.
    by_hash = defaultdict(list)
    for k, n in nodes.items():
        # 자동 스냅샷은 사본이 정상이다 — 중복 판정에서 뺀다
        if k.lower().startswith("_dsh_config"):
            continue
        base = k.split("\\")[-1].lower()
        if base.startswith("_dsh_config"):
            continue
        body = (n.get("body") or "").strip()
        if len(body) > 50:
            h = hashlib.md5(body.encode("utf-8", "replace")).hexdigest()
            by_hash[h].append(k)
    dup_map = {}
    for h, ks in by_hash.items():
        if len(ks) > 1:
            for k in ks:
                dup_map[k] = [x for x in ks if x != k]

    # 죽은 참조 (F 유형)
    dead = defaultdict(int)
    for e in edges:
        if e.get("k") == "F":
            dead[e["s"]] += 1

    def is_guidance(n):
        """지침서인가 — 이것만 단어 상한이 있다."""
        nm = (n.get("name") or "").lower()
        return nm in ("agents.md", "skill.md") or n.get("chain")

    out = {}
    for k, n in nodes.items():
        issues = []
        checks_total = 4
        checks_pass = 0
        failed = []

        # 1) 길이 — 지침서만
        w = n.get("words", 0)
        if is_guidance(n):
            cap = 2080 if n.get("scope") == "(전역)" else 600
            if w > cap:
                issues.append(f"지침 길이 초과 {w}/{cap}단어")
                failed.append("길이")
            else:
                checks_pass += 1
        else:
            checks_pass += 1   # 일반 문서는 길이 제한 없음

        # 2) BOM
        body = n.get("body") or ""
        if body.startswith("\ufeff"):
            issues.append("BOM 있음 (.bat 실행 방해)")
            failed.append("BOM")
        else:
            checks_pass += 1

        # 3) 중복
        if k in dup_map:
            issues.append("같은 내용이 " + str(len(dup_map[k]) + 1) + "곳")
            failed.append("중복")
        else:
            checks_pass += 1

        # 4) 죽은 참조
        if dead.get(k):
            issues.append(f"없는 파일 참조 {dead[k]}개")
            failed.append("죽은참조")
        else:
            checks_pass += 1

        score = round(100 * checks_pass / checks_total)
        badges = [f"{checks_pass}/{checks_total}"]
        # _dsh_config 는 자동 스냅샷이다. 문제가 생겨도 원본 문제이므로
        # "고칠 곳"이 아니다 — 배지에 구분해서 표시한다 (2026-11-09).
        is_snapshot = k.lower().startswith("_dsh_config")
        stale = stale_map.get(k)
        # 낡은 사본은 원본이 더 최신이라는 뜻이다. "스냅샷"이라는 말만으로는
        # 안심이 안 된다 — 화면에 "낡음"을 붙여야 사용자가 옛 판본을 진짜로
        # 오해하지 않는다 (2026-11-09, c4-architecture 사본 1,098 B 뒤처짐).
        stale_issue = None
        if stale:
            shown, dst_b, src_b = stale
            stale_issue = f"사본이 낡음 ({dst_b:,} < {src_b:,} B) — 원본 {shown}"
            issues.append(stale_issue)
        if failed:
            if is_snapshot:
                badges.append("스냅샷")
            else:
                badges.extend(failed)
        if stale:
            badges.append("낡음")
        if n.get("chain") and n.get("scope"):
            badges.append(n["scope"])

        out[k] = {
            "score": score,
            "pass": checks_pass,
            "total": checks_total,
            "failed": failed,
            "issues": issues,
            "badges": badges,
            "guidance": is_guidance(n),
            "snapshot": is_snapshot,
            "stale": bool(stale),
            "stale_src": stale[0] if stale else None,
        }
    return out


def name_has_bom(n):
    return (n.get("body") or "").startswith("\ufeff")


def mask_private(text: str) -> str:
    """본문에 박히는 개인정보를 지운다. 배포용으로 남에게 줄 때 필요하다.

    2026-11-09 이식성검토 지적: 생성된 HTML 에 `C:\\Users\\User` 경로와
    전역 규칙 전문이 그대로 들어있었다. zip 으로 주면 개인정보가 같이 간다.
    화면에서 읽는 데는 지장이 없고, 원문 파일 자체는 안 건드린다.
    """
    if not text:
        return text
    # 1) 사용자 홈 경로 → ~
    home = str(HOME)
    if home:
        text = text.replace(home, "~")
        text = text.replace(home.replace("\\", "/"), "~")
        # 대소문자 변형
        text = re.sub(re.escape(home), "~", text, flags=re.IGNORECASE)
    # 2) 남은 C:\Users\<이름> 패턴
    text = re.sub(r"[A-Za-z]:\\Users\\[^\\\s`'\"]+", "~", text)
    text = re.sub(r"/Users/[^/\s`'\"]+", "~", text)
    text = re.sub(r"/home/[^/\s`'\"]+", "~", text)
    # 3) 작업장 경로는 남겨도 의미가 없으니 상대표기로
    root_s = str(ROOT)
    if root_s and root_s != home:
        text = re.sub(re.escape(root_s), ".", text, flags=re.IGNORECASE)
    # 4) tailscale IP · 사설 IP
    text = re.sub(r"\b100\.\d{1,3}\.\d{1,3}\.\d{1,3}\b", "<IP>", text)
    text = re.sub(r"\b192\.168\.\d{1,3}\.\d{1,3}\b", "<IP>", text)
    text = re.sub(r"\b10\.\d{1,3}\.\d{1,3}\.\d{1,3}\b", "<IP>", text)
    return text


def read_checks():
    """_docs_check.ps1 을 실제로 읽어서 "무엇을 대상으로 무엇을 보는지" 뽑는다.

    하드코딩하지 않는 이유: 검사기에 절을 추가하면 관계도에도 자동으로 뜬다.
    2026-11-08 실측 — 처음엔 손으로 적었는데 4b/4c/1b 를 추가하고 안 고쳐서
    화면이 옛날 목록을 보여줬다.

    사용자 요청 2026-11-09: "각 검사기가 뭘 보는지 정확히 — 어느 파일들의 뭐를
    검사하는지". 그래서 절 본문에서 ① 대상(파일 패턴) ② 세는 것 ③ 결과 종류를
    뽑아서 같이 넘긴다.
    """
    p = ROOT / "_docs_check.ps1"
    try:
        src = p.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return []
    out = []
    lines = src.split("\n")

    # 절 시작 위치를 먼저 모은다 (본문 범위를 잘라내려고)
    starts = []
    for i, ln in enumerate(lines):
        m = re.match(r"^#\s*-+\s*(\d+[a-z]?)\.\s*(.+?)\s*$", ln)
        if m:
            starts.append((i, m.group(1), m.group(2)))

    for idx, (i, num, title) in enumerate(starts):
        end = starts[idx + 1][0] if idx + 1 < len(starts) else len(lines)
        body = "\n".join(lines[i:end])

        # 1) 사람용 설명: 절 제목 다음 줄의 주석
        desc = ""
        for j in range(i + 1, min(i + 4, len(lines))):
            nxt = lines[j].strip()
            if nxt.startswith("#"):
                d = re.sub(r"^#\s*", "", nxt).strip()
                if d and not re.match(r"^\d+[a-z]?\.", d) and not d.startswith("-"):
                    desc = d
                    break
            elif nxt:
                break

        # 2) 대상 파일 패턴 — -Filter '*.md' / -Filter "AGENTS.md" 같은 것
        targets = []
        for pat in re.findall(r"-Filter\s+['\"]([^'\"]+)['\"]", body):
            if pat not in targets:
                targets.append(pat)
        # $candidates / $allMd / $liveMd 같은 변수 이름도 단서가 된다
        for var, human in [
            ("$candidates", "지침 파일(AGENTS.md)"),
            ("$allMd", "모든 .md"),
            ("$liveMd", "살아있는 .md (스냅샷 제외)"),
            ("$bomTargets", "지침·스킬 파일"),
            ("$mdFiles", "모든 .md"),
            ("$noteFiles", "기록 파일"),
        ]:
            if var in body and human not in targets:
                targets.append(human)

        # 3) 무엇을 세는가 — Get-WordCount / Get-FileHash / Select-String 등
        measures = []
        for fn, human in [
            ("Get-WordCount", "단어 수"),
            ("Get-FileHash", "내용 해시(중복 판정)"),
            ("Select-String", "특정 문자열 존재"),
            ("[regex]", "정규식 매칭"),
            ("ReadAllBytes", "바이트(BOM 확인)"),
            ("Get-ChildItem", "파일 목록"),
            ("\\.Count", "개수"),
        ]:
            if fn in body:
                measures.append(human)

        # 4) 결과 종류 — Bad(실패)/Warn(경고)/Info(정보)
        outcomes = []
        if re.search(r"[^A-Za-z]Bad\s", body):
            outcomes.append("실패")
        if re.search(r"[^A-Za-z]Warn\s", body):
            outcomes.append("경고")
        if re.search(r"[^A-Za-z]Info\s", body):
            outcomes.append("정보")

        out.append(
            {
                "n": num,
                "t": title,
                "d": desc,
                "targets": targets[:4],
                "measures": measures[:4],
                "outcomes": outcomes,
            }
        )
    return out


def main():
    nodes, edges, bucket = collect()
    # scope 목록: 넓은 것(전역/루트)부터. "맨 위가 중요하다"는 지적을
    # 색 순서로도 드러내기 위해 정렬해서 넘긴다.
    scopes = {}
    for nd in nodes.values():
        s = nd.get("scope") or "(없음)"
        scopes[s] = scopes.get(s, 0) + 1
    # "(전역)" → "(작업장 루트)" → 그 아래 순으로, 나머지는 이름순
    _head = ["(전역)", "(작업장 루트)"]
    ordered = [s for s in _head if s in scopes]
    ordered += sorted([s for s in scopes if s not in _head])
    payload = {
        "nodes": list(nodes.values()),
        "edges": edges,
        "bucket": bucket,
        "checks": read_checks(),
        "scopes": {s: scopes[s] for s in ordered},
        "quality": score_docs(nodes, edges),
        # 생성 시각 — "고쳤는데 안 된다"는 오판을 막는다.
        # 실제 사고: 소스 23:38 수정 / HTML 23:34 생성 → 사용자가 옛 화면을 봤다.
        # file:// 로 열면 자동 갱신이 안 되므로, 최소한 신선도를 보여준다.
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        # root 는 배포 시 노출되면 안 되므로 홈 기준 상대표기만 넣는다.
        "root": rel(ROOT) if ROOT != HOME else ".",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    # 본문에 `</script>` `</style>` 같은 문자열이 들어 있으면 브라우저가 거기서
    # 스크립트를 끊는다(2026-11-08 실측: SyntaxError). `</` 를 `<\/` 로 바꾼다.
    # JSON 문자열 안에서는 `\/` 가 `/` 와 같으므로 값은 안 변한다.
    blob = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    OUT.write_text(HTML.replace("__DATA__", blob), encoding="utf-8")
    size = OUT.stat().st_size / 1024
    print(f"OK  {OUT}")
    print(f"    노드 {len(nodes)} · 연결 {len(edges)} · 크기 {size:.0f} KB")
    print("    " + " ".join(f"{k}={bucket[k]}" for k in "ABCDEF"))


if __name__ == "__main__":
    main()
