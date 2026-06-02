# 탑 (The Tower) — 웹 플레이 (StackBlitz에서 바로 실행)

신의 탑 세계관에서 영감받은 **오리지널 텍스트 RPG**. 이 저장소 **루트가 곧 플레이 가능한 웹 앱**입니다.

## ▶ StackBlitz에서 열기

저장소를 StackBlitz로 열면 됩니다. 루트의 `.stackblitzrc` 와 `package.json` 덕분에
**자동으로 `npm install` → `npm run dev`** 가 실행되어 게임이 바로 뜹니다.

- StackBlitz: `https://stackblitz.com/github/<계정>/<저장소>` (기본 브랜치 권장)
- 또는 StackBlitz에서 "Import from GitHub" 후 열기 → 미리보기 창에서 플레이.

> 예전엔 Vite 앱이 하위 폴더에 있어 StackBlitz가 빈 WebContainer만 띄웠습니다.
> 이제 **루트에 앱과 `.stackblitzrc`** 를 두어 열자마자 자동 실행됩니다.

## ▶ 로컬에서 실행

```bash
npm install
npm run dev      # http://localhost:5173
```

## 무엇을 하는 게임인가

캐릭터를 만들고 **탑 134층 정상까지 오르는** 풀 플레이입니다. 브라우저 단독으로 동작하며,
파이썬 엔진의 **결정론적 전투·성장 공식을 JS로 그대로 포팅**해 밸런스를 보존했습니다.

> **134층**: 하층(1~15층)은 손으로 짠 상세 콘텐츠, 16~134층은 같은 규칙으로 **절차 생성**되어
> 이어 오릅니다. 적은 플레이어 레벨에 맞춰 스케일되고(공정), 10층마다 가디언·5층마다 거점이
> 배치되며, **134층 정상의 최종 가디언**이 마지막 관문입니다. 위로 갈수록 정직하게 가혹합니다.

- **캐릭터 생성**: 6개 포지션 · 이레귤러(고위험 고성장) · 스탯 배분
- **층 진행**: 전투/생존/지력/탐색/추격/협동/선택/가디언 등 시험 유형별 처리, 갈림길·숨겨진 층·거점
- **턴제 전투**: 스킬·방어·회복약, **동료 영입 후 함께 전투**(AI), 상태이상·치명타·장비 보정
- **성장**: 경험치·레벨업·**스킬 습득(수련)**, 랭킹/등급 상승, 명성·악명 평판
- **상점/이벤트/퀘스트**: 거점 거래(평판 가격), 랜덤 이벤트(도덕 선택 포함), 메인 퀘스트 보상
- **세이브**: 브라우저 `localStorage` 자동 저장 → 이어하기. **HP 0이면 사망(봐주기 없음).**
- 상단 **☰** 메뉴로 캐릭터 시트·랭킹 리더보드 확인.

## 구조

```
/                      ← StackBlitz 진입점 (Vite)
├── index.html  package.json  vite.config.js  .stackblitzrc
├── src/
│   ├── game.js        # 게임 루프 + UI
│   ├── engine.js      # resolve/character/rank/quest 결정론 로직 JS 포팅
│   ├── style.css
│   └── data/          # 게임 데이터(원본 tower-of-god/data 스냅샷)
└── tower-of-god/      # 원본 풀게임 (Claude가 GM인 Python 버전 + 문서)
```

> **원본(풀 GM 경험)**: 웹 버전의 내레이션은 데이터 템플릿입니다. "Claude가 즉흥 GM"인 진짜 풀
> 경험은 `tower-of-god/` 에서 `claude` 를 실행해 플레이합니다(자세한 건 `tower-of-god/README.md`).
>
> `src/data/` 는 `tower-of-god/data/` 의 스냅샷입니다. 원본 데이터 변경 시
> `cp tower-of-god/data/*.json src/data/` 로 동기화하세요.
