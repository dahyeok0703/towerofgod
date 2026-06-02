# 탑 (The Tower) — 웹 플레이 버전 (StackBlitz)

브라우저에서 바로 즐기는 **단독 플레이 버전**입니다. 파이썬 엔진의 결정론적 전투·성장 공식을
**JavaScript로 충실히 포팅**했고, 데이터(`skills/enemies/floors/items`)로 굴러갑니다.

> 원본 게임은 "Claude Code가 GM"인 텍스트 RPG라 Python과 LLM이 필요합니다.
> StackBlitz/브라우저에서는 Python·LLM을 못 돌리므로, 여기서는 **GM 내레이션을 데이터 기반으로 대체**한
> 플레이 슬라이스(캐릭터 생성 → 1~5층 → 전투/상점/갈림길)를 제공합니다. **전투 수치 밸런스는 원본과 동일**합니다.

## StackBlitz에서 실행

1. StackBlitz에서 이 저장소를 엽니다(GitHub Import). 또는 아래 URL 패턴:
   `https://stackblitz.com/github/<계정>/<저장소>/tree/<브랜치>/tower-of-god/web`
2. StackBlitz가 `web/`의 `package.json`을 감지해 자동으로 `npm install` → `npm run dev` 합니다.
3. 미리보기 창에서 바로 플레이합니다.

> 브랜치 이름에 `/`가 있어 URL이 안 먹으면, StackBlitz에서 저장소를 연 뒤 좌측 트리에서
> `tower-of-god/web` 폴더로 이동해 터미널에 `npm install && npm run dev` 를 입력하세요.

## 로컬 실행

```bash
cd tower-of-god/web
npm install
npm run dev      # http://localhost:5173
```

## 플레이 방법

- **새 게임** → 이름 → 포지션(6종) → 출신(일반/이레귤러) → 스탯 12점 배분.
- 층마다 **시험에 도전**: 전투(턴제, 스킬/방어/회복약 선택), 거점(상점·휴식), 갈림길(전투 vs 지력 판정).
- 전투 승리 시 경험치·레벨업·랭킹 갱신. **HP 0이면 사망**(세이브 삭제, 봐주기 없음).
- 진행은 브라우저 `localStorage`에 자동 저장되어 **이어하기** 가능합니다.

## 구조

```
web/
├── index.html
├── package.json          # Vite
└── src/
    ├── game.js           # 게임 루프 + UI
    ├── engine.js         # resolve.py·character.py 결정론 로직 JS 포팅
    ├── style.css
    └── data/             # skills/enemies/floors/items (원본 data/의 스냅샷)
```

> `src/data/`는 상위 `tower-of-god/data/`의 **스냅샷 복사본**입니다. 원본 데이터를 바꾸면
> 이 폴더에도 반영해 주세요(`cp ../data/{skills,enemies,floors,items}.json src/data/`).
