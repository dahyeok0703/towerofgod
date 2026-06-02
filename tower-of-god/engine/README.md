# engine/ — 결정론적 판정 엔진

전투·판정·확률 계산을 담당하는 파이썬 엔진이다.

## ⚖️ 핵심 규칙 (GM 필수 준수)

> **GM은 전투/판정이 필요한 모든 순간에 반드시 이 엔진(`resolve.py`)을 호출하고,
> 반환된 JSON 결과를 그대로 서술한다. 직접 수치(명중/피해/성패/확률)를 지어내지 않는다.**
> (CLAUDE.md 철칙 ②)
>
> 엔진이 내놓은 숫자는 진실이다. GM은 그 숫자에 **연출(묘사)** 만 입힌다.
> 결과를 바꾸거나, 플레이어에게 유리/불리하게 조작하지 않는다.

## 파일

- `resolve.py` — 판정 엔진(아래 3개 명령). 결과는 JSON(stdout).
- `selftest.py` — 자가 테스트(결정론 + 위험성 샘플 전투).
- `fixtures/` — 테스트용 액터 예시(`weak_player.json`, `sample_player.json`).

## 명령어

### 1) 능력 판정 — `check`
```bash
python3 engine/resolve.py check --stat 근력 --difficulty 보통 --actor save/player.json
# 옵션: --dice d100|3d6 (기본 d100), --seed 정수(재현용)
```
→ 주사위 + 스탯 보정으로 **대성공/성공/실패/대실패** 반환.
난이도: 아주쉬움·쉬움·보통·어려움·아주어려움·극악.

### 2) 전투 1합 — `attack`
```bash
python3 engine/resolve.py attack --attacker save/player.json --defender en_iron_brute --skill fish_05
# --attacker/--defender 는 "액터 파일 경로" 또는 "enemies.json 의 적 id"
# 옵션: --seed 정수
```
→ 명중·피해·신수소모·잔여 HP/신수·상태이상까지 계산해 JSON 반환.

### 3) 턴제 전투 — `combat` (start / step)
```bash
# 시작: 전투 상태(state) JSON 생성
python3 engine/resolve.py combat --mode start \
  --attacker save/player.json --enemies en_gate_warden,en_storm_eel --seed 11 > save/combat.json

# 진행: 플레이어 행동을 넣고 한 라운드 해결 → 갱신된 state 반환
python3 engine/resolve.py combat --mode step \
  --state save/combat.json \
  --action '{"type":"skill","skill":"fish_05","target":"e0"}' > save/combat.json
```
- **단계별 상태 반환** — GM은 라운드마다 묘사를 끼워 넣을 수 있다.
- 행동 type: `skill`(+`skill`,`target`) · `defend`(방어 태세) · `pass`(대기).
- `state` 안에 RNG 상태가 직렬화되어 **단계 간 재현성**이 유지된다.
- 종료 시 `status` 가 `victory`/`defeat` 로 바뀐다.

## 밸런스 공식 (요약)

- **능력 판정:** d100에서 `목표 = 50 + (스탯-10)×3 − 난이도`. 굴림이 목표 이하면 성공,
  폭이 크면 대성공/대실패.
- **명중:** `75 + (공격 민첩 − 방어 민첩)×2` (5~95% 클램프).
- **피해:** `(주력스탯 × 1.2 + 5) × 스킬배율 × 공격버프` 에 방어자 신수저항으로 경감
  `(×100/(100+저항×1.5))`, 치명타 ×1.5.
- 주력 스탯은 스킬 포지션에 따른다(낚시꾼=근력, 창지기/탐색꾼=민첩, 신수계열=신수조작).
- 모든 계수는 `resolve.py` 상단 상수에 모여 있다(**4단계 튜닝 포인트**).

데이터: `data/skills.json`, `data/enemies.json` 을 읽어 계산한다.

## 자가 테스트
```bash
python3 engine/selftest.py
```
동일 seed 재현성과 "강한 적 vs 약한 플레이어"의 위험성을 검증한다.
