# Changelog

All notable changes to dep_cal (Depreciation Calculator) will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Status
- 🧾 **상각명세서(엑셀) 생성기를 vcore 벡터의 소비자로 정리** — 계산·판정을 생성기 안에서
  두 번째로 하던 자리를 걷어냈다. `docs/IMPROVEMENT_PLAN_2026-09-05.md` Phase 1(T1) + 트랙 B1.
  pytest **1,401** 통과·1 skip.

### Fixed
- **연도별 집계가 달력연도였다** (감사 G3, `asset_schedule_generator.py`): 시트2가
  `monthly["year"]`로 묶어 결산월 ≠ 12에서 월별 시트와 어긋났다. 2024-06 취득·3월 결산이면
  FY2025(10개월)이어야 할 집계가 2024(7개월)·2025(12개월)로 나왔다. `CalendarMonth`가
  연도별 표와 같은 `fy_index`에서 유도한 `fiscal_year`를 싣고, 시트2는 그 라벨로 묶는다.
- **자본적지출 + 전체양도가 부분양도로 해석됐다** (감사 G4, `depcal.py`): CLI가 '전체양도'를
  `disposal_amount = 취득원가`로 인코딩했는데, capex가 있으면 기준원가가 `원가 + 증가액`이라
  그 금액이 기준에 못 미쳐 부분양도가 됐다. 재현(1천만/5년/capex 5백만/2022-06 전체양도):
  60개월 표가 생성되고 **양도 후 30개월 상각이 계속**됐다. '전부'는 `None` 하나로 표현하고,
  판정은 `vcore.disposal.is_full_disposal` 한 곳에서만 한다.
- **시트1 「처분 제거액」이 vcore와 다른 산식이었다** (감사 G5): `_calculate_disposal_info`가
  양도월의 **직전월**을 기준으로 `int()` 절사해 자체 계산했다(vcore는 양도월 포함 누계에
  4사5입). 재현(정률 3천만/5년/2023-06 40% 양도): 시트1 10,387,502 vs 실제 제거 10,462,128 —
  같은 파일 안에서 시트1과 시트3이 74,626원 어긋났다. 분배 산식을
  `vcore.disposal.disposal_split` 하나로 합치고(자연종료 후 양도 경로의 3벌째도 함께),
  생성기는 그 값을 인쇄만 한다.
- **처분 후 자본적지출 입력이 통과했다** (감사 G13): `AssetInput.validate`에 양도일 > 증가일
  가드가 없어 웹 경로에서 그럴듯한 무의미 표가 나왔다(CLI만 검사). 가드를 `validate` 한 곳에
  두어 두 진입점이 같이 막힌다. 취득원가 이상 ~ 통합원가 미만의 모호한 처분금액도 거부한다.
- 생성기 위생 (감사 G22): 미사용 import(`sys`·`date`·`relativedelta`·`get_column_letter`) 제거,
  자동 파일명의 자산명 살균(경로 구분자·상위참조가 `output/` 밖을 가리키지 못하게).

### Added
- **내용연수 5·6년 밖 손계산 골든** (감사 G12 트랙 B1,
  `tests_vector/test_golden_handcalc_other_lives.py`): 정액 7·14년(별표4율 × n = 0.994 —
  정액에도 종료해 잔재가 생기는 축), 정률 9년(0.284 — G1이 71% 발화했던 연수). 3.6.0의 정수
  산술 전환이 59개 엔트리 전부의 연 상각액을 바꿔놓고도 밖에서는 5년 하나로만 검증되고
  있었다. 표 자체는 `test_rate_table_statutory.py`가 이미 닫았고, 이 파일이 채우는 것은
  **「표 엔트리 × 컨벤션」 격자**다.
- G4·G13 회귀 가드 (`tests/test_depreciation_scenarios.py`). 시나리오 12는 '전체양도'를
  `None`으로 고쳐 쓰고 양도월에서 끊기는지 확인한다.

### Added (Phase 2 — 회귀 방어선, T4)
- **시나리오 12건이 파일 크기가 아니라 숫자를 본다** (감사 G16,
  `tests/test_depreciation_scenarios.py`): `_assert_excel_matches_vcore`가 ① 시트3 == vcore
  월벡터, ② 시트2 == 시트3을 회계연도로 묶은 값, ③ 시트2 == vcore 연도별 API(독립 경로),
  ④ 시트1 「처분 제거액」 == 시트3의 실제 누계 하강액을 1원까지 대조한다. 그동안 이 12건은
  `file_size > 5000`만 봤고 **G3·G4·G5가 전부 이 구멍으로 샜다**.
- **시나리오 13 신설 — 3월 결산법인**: 기존 12건이 전부 12월 결산이라 연도별 집계가 달력연도든
  회계연도든 같았다. G3를 발화시킬 수 있는 입력이 하나도 없었다는 뜻이다.
- 역주입으로 가드의 검출력을 확인했다: 시트2를 달력연도로 되돌리면 시나리오 13이, 처분 제거액을
  직전월·`int()` 절사로 되돌리면 부분양도 4건이 실패한다.

### Changed
- **공허 통과 테스트를 걷어냈다** (감사 G14, `tests_vector/test_input_guards.py`):
  `_common_data()`에 `asset_code`가 없어 `AssetInfo.__post_init__`의 '자산코드는 필수입니다'로
  통과하고 있었다 — 정작 검사 대상인 날짜 가드에는 실행이 닿지 않았다.
- `conftest.py`에 실행 인터프리터를 적었다 (감사 G25): 시스템 python3는 Flask가 없어 웹 테스트가
  skip되고, `~/Python_envs/main/bin/python`은 전부 실행된다. 어디에도 없어 로컬 skip을 결함으로
  오인하기 쉬웠다. `.gitignore`에 `pytest-of-*/` 추가.

### Known (Phase 2에서 추가)
- **core가 오타 날짜를 조용히 2020-01-01로 바꾼다** (감사 G18-①): G14의 공허 통과를 걷어내니
  드러났다. `parse_date_safe`(`core/dep_common.py`)가 절대 raise하지 않아 날짜 가드
  (`depreciation_engine.py:475-480`)가 죽은 코드다. `'2020-13-99'`·`'날짜아님'` 둘 다 무예외
  통과에 `calculation_success=True`, 2,400,000원이라는 그럴듯한 값이 나온다. 오라클이 오타에
  그럴듯한 값을 내면 거울 스윕의 의미가 깨진다.
  `test_invalid_acquisition_date_raises_not_default`를 `xfail(strict=True)`로 기록했다 —
  수정은 Phase 4(T5)이고, 고치면 XPASS로 실패해 마커 제거를 강제한다.

### Added (Phase 3 — depverify 정밀화, T2)
- **대장 합계 통제합계 대사 신설** (감사 G11, `depverify/reader.py` `ControlTotal`):
  합계행을 버리지 않고 파싱해 자산행 Σ(당기상각·누계·장부)와 대조한다. 완전성은 방향이
  반대라 **자산행을 아무리 뒤져도 '빠진 행'은 나오지 않는다** — 리더가 자산행을 구조행으로
  오판해 버려도 지금까지 검출 채널이 아예 없었다. 실측 4개 대장이 맞았던 것은 드롭이
  없었다는 뜻이지 검출기가 있었다는 뜻이 아니다. 불일치는 요약 첫 줄 `[완전성]`에 Δ와 함께
  올리고 종료코드 1. 합계행이 없으면 '일치'가 아니라 **'대사 불가(완전성 미검증)'** 이다.
  `read_ledger`가 4-튜플(… , ControlTotal)을 반환한다.
- Phase 3 회귀 가드 13건 (`tests_vector/test_depverify_completeness.py`): 합계 일치/드롭 검출/
  합계행 부재/소계 오인 방지/검증불능 행도 합산, 컬럼 부재 메시지, 매핑 오타 키, 시트 인덱스,
  숫자 날짜셀 2종, G7 3종.

### Fixed (Phase 3)
- **무형 양도·상각완료 후 양도가 항상 '차이'였다** (감사 G7, `depverify/verdict.py`):
  양도 환산식 `cost − exp_acc`는 누계열이 실제 누계인 **간접법(유형) 전제**다. 무형은
  직접상각이라 누계열이 당기분만 표시하므로 2차연도 이후 무형 양도는 무조건 차이가 났다
  (소프트웨어 12,000,000/5년/2022-01, 2024-06 양도 → Δ장부 −4,800,000. 같은 수치가 유형이면
  '일치'). `cur is None` 분기의 `d_bk = cost − exp_bk`도 "장부가액이 취득원가여야 일치"라는
  뜻이라 자산이 제거돼 장부 0인 대장은 무엇을 적든 차이였다. 둘 다 실측 앵커 0건이므로
  **'검증불능 — 비교식미확립'** 으로 분류한다(fail-closed). 틀린 사유의 경보는 감사인 시간을
  태우고 진짜 경보를 가린다.
- **provenance `-dirty` 오탐** (감사 G17, `depverify/provenance.py`): `git status --porcelain`이
  미추적 디렉터리만 있어도 dirty를 붙여, 코드가 커밋과 동일한데도 모든 보고서에 "커밋된
  코드로 재현되지 않는다"가 상시 출력됐다. `--untracked-files=no`로 추적 파일만 본다.
- **`--sheet "1"`이 시트 이름으로 해석됐다** (감사 G19, `depverify/__main__.py`): 정수 문자열은
  인덱스로 변환한다.
- **`--mapping` 오타 키가 조용히 무시됐다** (감사 G23): `DOUZONE_COLUMNS`에 없는 키는 거부한다.
  매핑을 줬는데 안 먹고 기본 컬럼명이 쓰이던 사고.
- **필수 컬럼 검사가 8개뿐이었다** (감사 G23): 전 키로 확장하고 **없으면 어떤 판정이
  불가능해지는지** 메시지에 적는다. `capex`가 없으면 전 행이 '필드결손'으로 사유가 오도되고,
  `category`·`disposal_date`가 없으면 양도 자산이 전부 '보유'로 재계산돼 거짓 '차이'가 났다.
- **숫자 날짜셀이 1970-01-01로 둔갑했다** (감사 G24): `pd.to_datetime(20220115)`는 나노초
  epoch로 읽힌다. 8자리 YYYYMMDD인지 엑셀 일련번호인지 셀만 보고 확정할 수 없으므로 추정하지
  않고 '모호한날짜셀'로 분류하며 서식 수정을 요구한다.

### Changed (Phase 3)
- **±2원 승계차 허용목록에 재검증 조건을 달았다** (감사 G15, `depverify/verdict.py`): 상한 2는
  표본 1개사 1건(2분할)에서 관측된 값이다. 표본 3개사 이상이 되면 재실측하고, 3분할 자산이
  나오면 2로는 부족하다는 것을 코드 옆에 적었다. 근거 없이 넓힌 허용목록은 차이를 통과시키는
  구멍이 된다.

### Fixed (Phase 4 — 엔진·오라클 에지케이스, T3/T5)
- **분리자산 정액 종료해가 잔액을 남겼다** (감사 G6, `vcore/separate_asset.py`): 정률은 종료해에
  잔액 전액을 강제하는데 정액은 `min(yearly, remaining)`뿐이었다. 이 경로의 prior_accumulated는
  **외부 확정값**이라 어긋난 채로 들어올 수 있고(12,000,000/5년/prior 9,000,000 → 정액 장부
  600,000), 다음 해는 `[]`라 그 잔액이 영구히 남았다. 정률과 같이 강제한다.
- **종료해 월 배분이 사건에 따라 달라졌다** (감사 G9, `vcore/monthly_schedule.py`): 자연종료
  **이후**의 전부양도는 자를 것이 없는데도 `truncated=True`를 세워 종료해 균등 재배분을
  건너뛰었다(정률 종료해가 dump vs 균등). 실제로 잘렸을 때만 세운다.
- **자연종료 후 부분양도가 월별 API에서 무흔적으로 사라졌다** (감사 G8): `apply_ratio_from`이
  조용히 사본을 돌려줬다. 연도별 API는 같은 사건에 조정을 반영하므로 API마다 다르게 보였다.
  월벡터로 표현할 수 없다는 사실을 ValueError로 말한다.
- **종료월 부분양도가 같은 회계연도에 행을 둘 만들었다** (감사 G10, `vcore/disposal.py`):
  `fiscal_year`가 비유일해져 `next(r for r in sch if r.fiscal_year == fy)`류 소비자가 첫 행만
  보고 양도를 놓쳤다. 조정을 종료해 행에 병합한다(분배 수치는 손계산 골든 그대로).
- **core가 오타 날짜를 2020-01-01로 조용히 대체했다** (감사 G18-①·②, `core/dep_common.py`):
  `parse_date_safe`가 어떤 오류든 기본값을 돌려줘 상위 날짜 가드가 죽은 코드였다.
  `'2020-13-99'`가 무예외 통과에 `calculation_success=True`, 2,400,000원까지 냈다. 예외를 올린다.
- **core가 도메인 오류를 빈 결과로 삼켰다** (감사 G18-③, `core/depreciation_engine.py`):
  빈 결과는 스케줄 0건·장부가 0이라 **전액 양도된 자산과 구분되지 않는다**. ValueError는
  전파하고, 예상 밖 오류만 종전대로 축약한다.
- **정률 + 전기말확정 + 부분양도가 조용히 전액양도로 처리됐다** (감사 G18-④): 정액에는 있는
  분기가 정률에 없었다. 정답 규약이 확립되지 않은 조합이므로 그럴듯한 오답 대신 거절한다
  (거울 대조 범위에서 명시 제외 — 사유를 코드 옆에 적었다).
- **자본적지출이 조용히 빠진 상각표가 나왔다** (감사 G18-⑤, `core/dep_tang_engine.py` 4곳):
  증가 시점이 상각 기간 밖이면 `logger.error` 후 base를 그대로 반환했다. ValueError로 올린다.
- **입력 타입을 강제하지 않았다** (감사 G21, `vcore/projection.py`): `cost=12_000_000.5`가 그대로
  흘러 장부가액 9,600,000.5가 나왔다 — 원 단위 대조 도구에서 소수 금액은 그 자체로 오답이다.
  bool은 int의 하위형이라 따로 막는다.
- `vcore/disposal.py` 모듈 docstring의 낡은 서술 정정 (감사 G20): core의 양도월 컨벤션은
  2026-06-13에 통일됐는데 "core = 양도월 + 1, 한 달 매핑 필요"가 남아 있었다.
  `capex.apply_increase`의 미사용 `cost` 인자 제거.

### Added (Phase 4)
- **웹 인터페이스 결산월 선택** (`templates/calculator.html`, `dep_cal_web.py`): 폼에 필드 자체가
  없어 3월 결산법인이 12월 결산 표를 받았고, 그 사실이 산출물 어디에도 적히지 않았다.
- **`INCIDENTS.md` 신설** (감사 G26): 같은 패턴의 2회차를 '두 번째'라고 부르기 위한 등록부.
  INC-01~INC-11, 반복 패턴 4종(원단위 산술 · 판단 2벌 · 조용한 기본값 · 완전성 채널 부재)과
  각각의 봉인 위치(실행되는 테스트 이름)를 적었다.
- Phase 4 가드 18건 (`tests_vector/test_phase4_edge_cases.py`).
- `.gitignore`에 gbrain 로컬 디렉터리(`depcal/`·`inbox/`·`projects/`) 추가.

### Known
- **정액 41·43·45·47·49·51·52·54·55·57·58·60년은 내용연수 종료 전에 상각이 끝난다**
  (정액율 × n > 1). vcore는 그 뒤에 상각액 0인 꼬리 행을 1~2개 붙이는데, 분리자산 경로가
  같은 상황에서 `[]`를 돌려주는 것과 어긋난다. 실측 앵커가 0건이라 어느 쪽이 옳은지 코드가
  정하지 못한다 — 현 동작을 골든으로 굳히지 않고 미결로 기록한다(G12-B 표본 확보 시 판정).
- G12-B(실대장 표본 5~10개사)는 **미해소**다. 표 엔트리별 실측은 여전히 5년 하나다.

## [3.6.0] - 2026-09-03

### Status
- 🔢 **연 상각액 산식을 float 곱셈에서 별표4 1000분율 정수 산술로 교체 (vcore + core 동반)**.
  전체 pytest **1,387** 통과·1 skip(시스템 python, 웹 테스트는 Flask 미설치) / venv **1,405** 통과.
- `docs/audit_lattice_2026-09-03.md` 전수 감사(G1·G2)에서 출발한 변경이다. 2026-07-25 D8은 이
  계열을 "10¹¹부터·실무 영향 없음"으로 닫았으나 스캔 범위(23,600조합)가 부족한 오판이었다.

### Fixed
- **정률 float 산식이 정확한 정수 결과를 1원 내리던 결함** (`vcore/declining_balance.py`·
  `monthly.py`·`separate_asset.py`의 `int(book × rate × months // 12)`): 0.284(9년)·0.349(7년)·
  0.071(41년)처럼 이진 표현이 참값보다 작은 상각률에서 10,000,000 × 0.284 = 2,840,000이
  2,839,999.99…로 계산돼 `//`가 2,839,999로 내렸다. 취득원가 100만~10억 1,000원 단위 표본에서
  **9·41년 71.3%, 33년 30%, 7년 24.8%, 19·40년 20.2%, 28·58년 17.8%** 발화. 5년(0.451)은 0건.
- **정액 4사5입이 정확히 x.5인 곱에서 내리던 결함** (`vcore/straight_line.py`의
  `round_half_up(cost × rate)`): 10,000,500 × 0.071 = 710,035.5가 710,035.4999…로 계산돼 710,035.
  .5 경계 표본에서 **7·14년 71.3%, 28·56·57·58년 49.6%, 23·46·47년 6.5%** 발화. 5·6·8·10년은 float가
  정확해 손계산 골든·A사 실측 99건이 전부 통과했다 — 즉 **더존 실측은 별표4 59개 엔트리 중
  1개(5년)만 덮고 있었고**, core가 같은 float 산식이라 거울도 눈이 멀어 있었다.
- 산식을 `vcore/rate_table.py`의 정수 관문 둘로 통합: `straight_line_annual(cost, life) =
  (cost × s + 500) // 1000`, `declining_balance_amount(book, life, months) = book × d × months // 12000`.
  정액·정률·월별·분리자산 경로가 전부 이 둘만 부른다(연 산식 3중 구현 해소 — 07-10 잔여).
  단수 규칙(정액 4사5입·정률 절사)은 그대로다. float 표(`STRAIGHT_LINE_RATES` 등)는 3자 대조·
  표시용으로만 남고 `check_life_years`가 범위 가드 단일 관문이 된다.
- **core 동반 수정**(`dep_common.annual_straight_line`·`yearly_declining` 신설, `dep_tang_engine.py`
  6곳 교체): oracle이 같은 결함을 가진 채 남으면 거울 스윕의 의미가 깨지므로 FREEZE_NOTICE 예외
  절차로 수정(P2 `round_half_up`·A-1 비망 캡 선례). core는 자체 float 리터럴에서 `round(rate × 1000)`
  으로 1000분율을 복원해 vcore 표와 데이터를 공유하지 않는다(독립 증인 유지).

### Added
- `tests_vector/test_integer_arithmetic_litmus.py` (272건) — 감사 실측 핀 8건, 연수 2~60 전수 ×
  취득원가 표본의 순수 정수 오라클 대조(정액 연상각·정률 첫해 12/7/1개월), 월별·분리자산 경로
  산식 일치, core 거울(해당 연수, 종료해 포함 전 구간 월별). **수정 전 코드에서 55건 실패**를 확인한 뒤 봉인.
- `tests_vector/test_intangible_golden_handcalc.py::test_core_intangible_monthly_matches_handcalc` —
  무형 6년 72개월을 core 월별로도 손계산 재구성과 대조(아래 G28 회귀 가드).

### Changed
- 기존 골든·실측(손계산·A사 99건·B사 6건·core 거울) **전부 무변화** — 5·6년은 float가 정확한
  연수라 예상대로다. `sample_data/verify_ledger.py` 재실행 불일치 0.
- `README.md` 상각률표 절·`docs/TRUTH_MATRIX.md` 단수처리 절에 "계산도 정수로" 추가.
- **core 정액 종료해 잔재의 12월 dump 해소** (감사 G28, `core/depreciation_engine.py`): 종료해
  균등 재배분(`_settle_terminal_evenly_schedule`)이 이벤트(capex·부분양도) 경로에만 걸려 있어,
  단순 스케줄에서는 별표4율 × n ≠ 1인 연수(6년 0.166×6=0.996, 7년 0.142×7=0.994, 14년 등)의
  잔재를 결산월에 몰아넣고 있었다(정액 7년 3,000,250: `35,503 ×11 + 52,501`). 같은 core가 정률은
  이미 균등이라 자기모순 상태였다 — 2026-06-13 "정액·정률 동일 원칙" 결정이 정액에 미적용된
  잔여다(당시 근거였던 `vcore/monthly.py` "정액법은 잔재가 없어 no-op" 주석은 별표4율 × n = 1인
  연수에만 참). 게이트에서 이벤트 조건을 제거해 자연완료 스케줄 전부에 적용 → core도
  `36,919 ×11 + 36,925`로 vcore·무형 6년 월단위 손계산 골든과 1원 일치. 연총액·누계·장부가는
  변경 전후 동일(엑셀 월별 명세서 종료해 행만 달라진다).

## [3.5.0] - 2026-08-27

### Status
- 🔀 **합병 승계자산 경로 신설 + 12개월 미만 사업연도 범위 서술 정정**. 전체 pytest **1114** 통과.
- 외부 사용 피드백(2026-08-27, 자기 회사 결산 목적의 vcore 단독 사용)에서 출발한 변경이다.
  "신설법인 첫 사업연도는 범위 밖"이라는 README 서술 때문에 사용자가 정상 계산되는 값을
  못 쓸 뻔했다 — 문서가 엔진의 실제 능력을 과소 고지하고 있었다.

### Added
- **`separate_asset.schedule_merger_succession()`** — 합병 존속법인이 승계한 자산의
  회계연도 상각. 소멸법인이 `disposal.schedule_full_disposal(disp_month=등기월)`로
  등기월까지 상각하므로, 존속법인은 **등기월 다음 달부터** 이어받는다(사용자 결정).
  시행령 문언(§26⑧⑨)대로면 "1월 미만의 일수는 1월로 한다"가 소멸·존속 양쪽에 각각
  걸려 등기월이 중복 계산된다(등기 5/15 → 5개월 + 8개월 = 13개월). 금액이 이중상각되는
  것은 아니지만(§29의2② — 존속법인의 미상각잔액은 양도 당시 장부가액에서 출발) 그해
  합산 상각범위액이 12개월치를 넘으므로, 중복을 배제하는 쪽을 택했다. 승계 쪽 취득가액·
  상각방법·내용연수는 양도법인 기준(§29의2② 1호). 비적격합병(시가 취득)은 범위 밖.
- **`separate_asset.schedule_separate_asset(start_month=…)`** — 연도 중 진입 자산의
  상각 개시월. 기본 1(연초)로 기존 동작 불변. 종료해의 상각 가능 월(취득월−1)을 지나
  진입하면 `[]`. 등기월+1이라는 규칙은 호출부가 아니라 `schedule_merger_succession`
  안에 둔다 — off-by-one이 재발할 자리라서다.
- **`tests_vector/test_merger_succession.py`** 9건 — 이음매를 불변식으로 고정한다:
  등기월 1~11월 전 구간에서 ⓐ 두 법인 월수 합 = 그해 12개월, ⓑ 쪼갠 상각액 합 = 단일
  법인이었을 때의 그해 상각액(월할 절사 2회로 최대 1원 부족까지 허용).

### Changed
- **README 「범위」 정정** — "사업연도 월수 < 12개월"을 통째로 범위 밖으로 적어 두었으나,
  실제로 못 하는 것은 **계속기업의 사업연도 변경**뿐이다.
  - **신설법인 첫 사업연도**: §26⑧의 안분(× 사업연도 월수/12)과 §26⑨의 월할
    (× 사용월수/사업연도 월수)에서 사업연도 월수가 약분되어 결과가 언제나 `사용월수/12`
    — 엔진의 첫해 개월수(`13 − 취득월`)와 같다. A사 대장 실측(설립연도 취득
    84건, 상각누계까지 1원 일치)으로 확인. → 「하는 일」로 이동.
  - **합병·해산 소멸법인의 최종 의제사업연도**: §26⑧의 월수 안분이 "그 월수까지만 상각"과
    같고, 월수 규칙(1월 미만 일수는 1월 = 등기월 포함)이 더존 양도월 규칙과 일치하므로
    `schedule_full_disposal`이 그대로 정답. → 「하는 일」로 이동.
- **`depverify/report.py` 고지 문구** — 검증보고서 「고지」 시트에 인쇄되던 같은 서술을
  README와 동일하게 정정(감사조서에 붙는 문서라 어긋나면 안 되는 자리).
- **`FREEZE_NOTICE.md`** — `Current Version`이 3.3.0에 멈춰 있었다(3.4.0 릴리스 때
  갱신 누락). 손으로 적은 숫자를 `vcore.__version__` 포인터로 바꿔 같은 결함이 재발하지
  않게 했다. 3.4.0의 **core 동반 수정(비망가 캡, 정액·정률 2곳)** 예외 적용 기록도
  누락돼 있어 v3.3.0 절과 같은 형식으로 채웠다. `Effective Date: 2024-11-27`은 오타가
  아니라 v2.0.0 Production Release의 동결 발효일이므로, 그렇게 읽히도록 주를 달았다.

## [3.4.0] - 2026-07-25

### Status
- 🔧 **비망가 캡 결함 제거 + 연간 상각 로직 3중 구현 단일화**. 전체 pytest **853** 통과.
- 📋 `docs/IMPROVEMENT_PLAN_2026-07-25_AUDIT.md` — 전체 정밀평가(D1~D7)와 개선계획 A/B/C/D.
- 이 버전에는 앞선 미기재 작업(`depverify` V1 일괄 검증 파이프라인, 정률 첫 실대장 검증)도
  같은 미배포 구간에 포함돼 있다.

### Fixed
- **비망가 캡이 `remaining ≤ 0`에서 무력화되던 결함**: 캡 조건이 `if 0 < remaining < yearly`
  (core는 `if remaining > 0 and yearly > remaining`)라 **이미 비망가에 도달하면 캡을 통째로
  건너뛰고 계속 상각**했고, 그 초과분이 종료해에 **음수 상각**으로 되돌아왔다
  (cost=500·정액 5년 → 종료해 −900원, 누계 −500원, 장부가 1,000원 > 취득원가).
  실무 금액대(100만원↑)는 전건 정상이라 손계산 골든·더존 실측 어디에도 걸리지 않았고,
  결함 경계는 취득원가 약 4만원 이하 대역이었다(정액 10년 ≤5,016 / 60년 ≤40,000,
  정률 10년 ≤10,990 — 실측). `remaining ≤ 0 → 상각 0`으로 정정.
- **core 동반 수정**(`dep_tang_engine.py` 정액·정률 2곳): oracle이 같은 결함을 가진 채로
  남으면 core↔vcore 거울 스윕의 의미가 깨지므로 FREEZE_NOTICE 예외 절차로 직접 수정
  (P2 `round_half_up` 선례와 동일 계열). 분리자산 경로는 이미 `remaining <= 0` 조기
  반환이라 무결. core 자체 회귀 무변화.
- **내용연수 범위 밖 입력의 조용한 클램프**(`vcore/straight_line.py`, `declining_balance.py`):
  상각률 조회의 "가장 가까운 작은 연수로 폴백" 분기는 별표4 표가 2~60년 완전 수록이라
  표 안에서는 **죽은 코드**였고, 살아 있는 효과는 범위 밖 입력을 조용히 60년율(정률은
  기본율 0.1)로 클램프하는 것뿐이었다 — `life=100`에 예외 없이 60년 표가 나왔다.
  폴백 분기를 제거하고 표 직접 조회 + 범위 밖 ValueError로 정정. `life < 2` 가드도
  같은 메시지로 통합(별표4 상각률표 범위 2~60년). 정률의 `DEFAULT_DECLINING_RATE`
  import는 이 변경으로 미사용이 되어 제거.
- **무형 계정 오분류**(`depverify/reader.py`): 계정과목 `개발비`가 무형 목록에 없어 유형
  간접법으로 해석돼 취득원가가 기초가액 1,000원(실제 37,000,000원)으로 오복원됐다.
  상각완료 자산이라 비망 규칙 세 조건이 **우연히** 맞아 '일치'로 통과 — 같은 자산을
  종료해로 검증했다면 위 비망가 캡 결함까지 겹쳐 Δ당기상각 −816원이 났을 것이다.

### Added
- **`vcore/projection.py: capped_yearly()`** — "연 상각액 산출 + 비망가 캡"의 단일 관문.
  `straight_line.standard_vector` / `declining_balance.standard_vector` /
  `monthly.standard_monthly` 3중 구현을 하나로 합쳤다(방법 차이는 `yearly_fn` 주입만).
  위 결함이 정확히 이 3곳에 복제돼 있던 것이 단일화의 직접 근거.
- **취득원가 스코프 가드**: `cost ≤ 비망가액(1,000)`은 상각할 금액 자체가 없으므로
  `validate_asset_inputs`에서 ValueError(기존 `cost <= 0` 가드를 포섭).
- **`tests_vector/test_schedule_invariants.py`**: 손계산 골든 사이의 빈 공간을 덮는 구조
  불변식 — (1) 비망가 캡(음수 상각·누계 금지, 비망가 ≤ 장부가 ≤ 취득원가, 종료 시
  장부가=비망가)을 소액 대역 전수 + 실무 금액대에서, (2) **연도별표 ↔ 월별표 회계연도
  집계 일치**(내용연수 2~20 × 취득월 1~12 × 금액 3종 × 정액·정률 = 1,368 조합)를 고정.
  후자는 A-1 단일화의 게이트이자, depverify(연도별표)와 상각명세서(월별표)가 갈리지
  않음을 구조적으로 보장한다.
- **`depverify` 간접법 불변식 가드**: 유형 이월이면 `기초가액 > 전기말상각누계액`이어야
  한다(비망가 때문에 누계가 취득원가에 도달 불가). 위반 시 조용한 오복원 대신
  검증불능 분류 — 계정 화이트리스트 확장보다 근본적인 방어선.
- **`tests_vector/fixtures/douzone_golden_b.json`**: B사 FY2025 대장 익명 골든 6건.
  정률 실측 앵커 확대(455,000원·2021-06 / 1,088,728원·**2022-12 취득 = 첫해 1개월**),
  정률·정액 상각완료 비망유지 2건, 무형 직접상각 2건(진행 1 + **완료 1**).

## [3.3.0] - 2026-07-02

### Status
- 🔧 **원단위 반올림 banker's rounding 함정 제거**. 전체 pytest **778** 통과.
- 🔒 **core "oracle-only 봉인" 선언**: 실행 경로에서 완전 배제, 골든 대조·불변식 테스트 전용으로 결착.
  영구 상태가 아닌 과도기 — vcore가 core 기능을 패리티·무오류로 재현하면 대조 축 역할을 접고 순수
  보존(박제)으로 전환 예정. 상세: `FREEZE_NOTICE.md`.

### Fixed
- **원단위 round() banker's rounding → 4사5입(round_half_up)**: Python 내장 `round()`는
  x.5를 짝수로 반올림(banker's rounding)하는데, 이는 상용/세법 회계의 4사5입 관행과
  정확히 x.500인 금액에서 1원 갈릴 수 있다. TI 더존 실측 99건에는 x.500 자산이 없어
  그동안 미검증 잠복 결함이었음(x.500 손계산 리트머스로 발견, `tests_vector/test_rounding_litmus.py`).
  `vcore`(`straight_line.py`, `disposal.py` 3곳) + `core`(`dep_tang_engine.py` 9곳,
  `dep_intang_engine.py`·`depreciation_engine.py` 각 1곳, 총 11곳) 전부를
  `round_half_up`(`math.floor(x+0.5)`)으로 교체. **산출 의미 변경 없음**(A사 99건 골든
  Δ=0 불변) — x.500 경계에 해당하는 금액대에서만 값이 1원 확정(내림→올림)됐다.
- core 수정은 FREEZE_NOTICE.md 예외 사유 2번(심각한 회계 오류) 적용. 두 엔진 모두
  같은 결함을 갖고 있었음을 실측 확인(패치 전후 core 자체 회귀 216개 전부 무변화) 후
  동일 수정 — core↔vcore 자기참조 스윕(`test_slim_vs_reference.py`)이 x.500 경계에서
  이탈했다가(14건) core도 함께 고쳐 재일치. 수정 직후 TI 실제 xlsx 3개년(99건) 재검증도
  Δ=0 유지 확인.

## [3.2.0] - 2026-07-02

### Status
- ⭐ **TRUTH_MATRIX 캠페인 완주**: 손계산 절대 골든값으로 라이브 경로(정률 7·정액 6·무형 4,
  총 17경로) 전부 🟢外(외부기준: 손계산 절대 골든 또는 더존 실측) 도달. 전체 pytest **775** 통과.
- ✅ **더존 실측 검증 CI 상시화**: 익명 골든 픽스처(`tests_vector/fixtures/douzone_golden_a.json`,
  99건)로 xlsx 파일 없이도 CI에서 상시 대조 가능해짐.

### Added
- **`docs/TRUTH_MATRIX.md`**: 계산 경로(정액·정률·무형 × 단순·capex·전체양도·부분양도·combo ×
  12월/3월결산)별 검증기준 등급화(🟢外=외부기준·❗=자기참조뿐·⛔=미지원) + core 거취 결착 로직
  ("모든 라이브 경로 🟢外 도달 시 core는 제거 or oracle-only 봉인").
- **손계산 절대 골든값** 다수(`tests_vector/test_*_golden_handcalc.py`): 정액(단순·CAPEX·전체양도·
  부분양도·CAPEX+부분양도·CAPEX+전체양도, 12월/3월결산), 정률(전체양도·부분양도·combo, 3월결산
  확장), 무형(부분양도·완전 월단위) — core·vcore 어느 쪽에도 의존하지 않는 제3의 외부 기준.
  자기참조(core==vcore)만으로는 잡을 수 없던 검증 공백을 메움.
- **원단위 단수처리 조사**(`docs/TRUTH_MATRIX.md` 결론): 법인세법 미규정·더존 설정값 존재를 확인하고
  A사 실측 2건(FY2025 cost 6,097,749 / 81,915,104)으로 반올림(round) 확정 실증 — Python `round()`의
  banker's rounding 잠복 리스크는 이 조사에서 처음 식별([3.3.0]에서 수정).

### Fixed
- **core 정액 CAPEX+부분양도 임의결산월 1원 이탈**: 손계산 골든 작성 중 core 1원 실격 발견 →
  vcore 위임으로 즉시 해소.

## [3.1.0] - 2026-06-16

### Status
- 🔧 **정률·무형·분리자산 정합 강화**. 전체 pytest **725** 통과.
- ✅ **정률 손계산 절대 골든**(7경로 16건) 도입 — 더존 정률 실데이터 부재를 외부 기준으로 보완. 엔진 모듈 미사용 순수 산술 재현이 core·vcore와 1원 일치 확인 후 하드코딩.

### Added
- **vcore 분리자산 경로** `vcore/separate_asset.py`: `prior_accumulated`(전기말 누계) 기초로 당기(`target_year`)만 계산(정액·정률). core와 1원 일치. 12월 결산만 지원.
- **정률 손계산 골든** `tests_vector/test_declining_golden_handcalc.py`: 단순(12·3월결산)·capex·부분양도·capex+부분양도·capex+전체양도. core·vcore 양쪽 또는 vcore 단독(core 버그 경로) 대조.
- **입력 가드** `tests_vector/test_input_guards.py`: 부분양도≥원가→전부양도 위임, capex 증가월≤취득월→`ValueError`, 무형 capex 지원.
- **자연종료 후 부분양도 처분 조정행**: 양도 연도에 양도분 취득가액 안분 제거(상각 0).

### Changed (산출 의미 변경)
- **정률 종료해 5% 잔재 균등 배분**: 마지막 달 dump → 월할 균등(core·vcore, capex·부분양도 잔여표까지 확장). 연간합계·최종 장부가 불변, 월별 분포만 변경.
- **무형자산 전체 별표4 통일**: core 무형이 1/n 직접나눗셈 → 별표4(유형 정액 함수 재사용). 3·6·7·9년 등에서 값 변경(별표4가 정답). core==vcore 1원 일치.
- **자연종료(완전상각) 후 부분양도 비망가 안분**: 비망가는 가치가 아닌 자산 단위 메모이므로 양도 비율로 안분(60% 양도 → 잔존가액 400). 종료 전 양도는 현행 유지(잔류분 1,000).

### Fixed
- **정률 capex+부분양도 음수 월상각** (core): 부분양도 연도 결산월 보정의 양도 전/후 누적 혼선 → 음수(-11,953,058) + 종료해 떠밀림. vcore 위임 + 양도 후 전용 누적으로 수정, 1원 일치.
- **정률 분리자산(prior_accumulated) 조용한 무시** (core): 함수 미전달로 prior 무시하고 전체 스케줄 반환 → 당기만 계산하도록 수정.
- **무형 capex 증가액 누락** (core): 무형 분기 부재로 증가액 무시 → 유형 정액 capex 함수 재사용으로 지원.
- **도메인 외 입력 가드 3종**: 음수 상각(부분양도≥원가)·인덱스 폭주(capex k≤0)·무형 capex 누락을 위임/예외로 차단.

## [3.0.0] - 2026-06-11

### Status
- ⭐ **실행 엔진 교체**: 모든 실행 경로(웹·CLI·dep_verify)가 vcore 슬림 코어 사용. core는 동결 oracle(골든 가드·동등성 매트릭스 전용)로 강등
- ✅ **회귀**: pytest **681/681** (골든 가드·월별 정합·실데이터 포함)
- ✅ **실데이터**: A사 더존 대장 FY2022/2024/2025 — 99 자산-연도 **1원 일치** (전액양도 11건 포함)
- ✅ **동등성 선언**: 정액·정률 core↔vcore 같은 결과 산출 확정 (실무 기준: 100만원 이상 등록, 별표 테이블 연수 보간 인정)

### Changed (BREAKING — 산출물 의미 변경)
- **양도월 규칙 더존식 채택**: `vcore.disposal`의 `disp_month` = 양도월(그 달까지 월할 상각, WEHAGO 공식). 기존 core 의미(disposal_date 직전월 중단)와 한 달 차이 — core 비교 시 `vcore 양도월 = core 월 - 1` 매핑. dep_verify 어댑터 매핑 반전 적용(공개 계약 불변).
- **실행 경로 core → vcore**: `asset_schedule_generator.generate_schedule`이 `vcore.monthly_schedule.monthly_events`(단일 진입점) 호출. capex×양도 동시 조합은 변환 합성(증가→양도 스케일)으로 지원.
- **부분양도 rebase 시점**: 양도월은 전체 취득원가 기준 상각, 잔존 기준 재기준화는 익월부터 (더존식).
- **무형 종료연도 월 분배 통일**: 유형 정액과 동일하게 균등 분배 (연총액 동일 — 구 core는 유형/무형 엔진끼리도 분배가 달랐음).

### Added
- **`vcore/monthly_schedule.py`**: 달력 매핑 월별 스케줄 공개 API (`CalendarMonth`). 연도별 표와 같은 월벡터를 공유해 월별↔연도별 정합 구조 보장. 단순·capex·전체/부분양도 + `monthly_events` 일반 디스패치.
- **골든 가드** `tests_vector/test_golden_core_vs_vcore.py`: 유형 정액·정률(단순·capex·전체/부분양도)은 core와 **월 단위(상각·누계·장부) 완전 일치**, 무형은 연 합계, 조합은 ±1원+최종값 수렴.
- **월별 정합 가드** `tests_vector/test_monthly_schedule.py` (128개): 월별 합계 == 연도별 표 (전 결산월×취득월).
- **실데이터 회귀 가드** `tests_vector/test_real_ledger_a.py`: FY2022/2024/2025 더존 대장 대조 (xlsx 부재 환경은 skip).
- `.gitignore` 신설 — pyc·pytest_cache·실고객 xlsx 추적 해제.
- `docs/REPO_AUDIT_2026-06-11.md`: 저장소 종합 점검 보고서 (엔진 품질 실측·정리 후보·배포 전 체크리스트).

### Fixed
- **부분양도 경계 가드**: 양도 시점이 자연상각 종료 이후일 때 IndexError → 경계 클램프(자연 스케줄 유지). 실데이터에 실존한 케이스.
- **실데이터 하네스 파일선택 버그**: glob이 임의 연도 대장을 집던 문제 → FY에서 파일명 파생, None 가드, `verify(fy)` 함수화.
- **(발견) core 조합 경로 버그**: 정률+capex+부분양도에서 core가 음수 월상각(-1,342,036원) 산출 — 인증된 적 없는 경로의 연말보정 폭주. vcore는 음수 없이 동일 최종값 수렴, 전환으로 자연 해소.

## [2.3.0] - 2026-06-02

### Status
- 🆕 **vcore 슬림 코어 신설** (실행 경로 불변 — 검증·후보 엔진 단계)
- ✅ 저장소 정본 통합: dep_vector 단일 정본, Dep_API 아카이브

### Added
- **vcore 슬림 코어** (~450 LOC, core 대비 1/7): "모든 시나리오 = 표준형 월별 벡터의 변환" 단일 원리.
  - 정액법·정률법: 표준형+프로젝션, 레퍼런스와 각 720/720 1원 일치
  - 자본적지출(정액·정률): Vector 비율 합성, 각 240/240 1원 일치
  - 전체양도·부분양도(정액·정률): 벡터 절단 / 역 capex 누계 분배, 각 160/160 1원 일치
  - 무형자산: 별표4 정액 (직접상각은 표시차이뿐)
- **`tests_vector/test_slim_vs_reference.py`**: 슬림 vs 레퍼런스 회귀 가드 (등가성 포함)
- **A사 실데이터 검증 하네스** `sample_data/verify_ledger.py`
- LICENSE·NOTICE 편입, README를 정본(vector) 기준으로 재작성

## [2.2.0] - 2026-05-22

### Status
- 🔒 **Code Freeze 예외 적용** (사유 2번: 회계 도메인 본질 결함 — 회계기간 1급 시민화)
- ⭐ **Quality**: Enterprise Grade (5/5) 유지
- ✅ **Compliance**: 한국 법인세법 [별표 4], 한국 관행 회계기간 표기 (결산일 속한 연도)
- ✅ **회귀**: pytest **122/122** (기존 105 + 신규 fiscal_period_view 17개, 비-12월 결산 스모크 포함)

### Added (회계기간 1급 시민화)
- **회계기간 개념 엔진 필수화**: `calculate_depreciation_enhanced(financials, asset_info, fiscal_year_end_month)` 시그니처에 `fiscal_year_end_month` keyword-only 필수 인자 추가. 한국 12월 결산 외(미국 1/31, 일본 3/31 결산 등)에서도 정확한 schedule 생성.
- **`extract_fiscal_period(result, fiscal_year)` view 함수 신설**: schedule을 회계기간으로 절단한 당기 요약 추출. dep_verify의 `company_dep`/`company_acc_dep`/`company_book_value` 어휘와 1:1 매칭되는 `FiscalPeriodSummary` 반환.
- **`FiscalPeriodSummary` 데이터클래스**: `fiscal_year`, `fiscal_year_end_month`, `period_start_date`, `period_end_date`, `period_depreciation`, `period_end_accumulated`, `period_end_book_value`, `months_in_period`.
- **`DepreciationResult.fiscal_year_end_month`** 필드: 계산 컨텍스트 보존, view 함수가 일관성 보장에 사용.
- **헬퍼 함수**: `get_fiscal_year(year, month, end_month)`, `get_fiscal_period_dates(fy, end_month)`, `get_fiscal_year_period(fy, end_month)`, `get_fiscal_year_dep_window(...)`.

### Changed (yearly_info 묶음 fiscal year화)
- **6개 유형자산 엔진 함수 + 1개 무형자산 엔진 함수** 의 `yearly_info`/`yearly_accumulated` 묶음이 calendar year에서 **fiscal year 단위**로 재구성. 결산월에 따라 schedule 자체가 다르게 산출됨 (월할 + 잔재 보정 위치 변경).
  - 12월 결산은 산술적으로 동일 결과 → 기존 회귀 매트릭스 105개 통과 보장
  - 비-12월 결산은 정확한 회계기간 단위 schedule 생성
- **14곳 `month == 12` 결산월 잔재 보정 발화 위치** 를 `month == fiscal_year_end_month` 로 일반화. calendar 날짜 인접 판정(`dp_month==12 and disposal_month==1`)은 12월 유지 (회계기간과 무관).
- **`generate_yearly_summary`** 가 calendar year 대신 fiscal year 단위로 묶음. `YearlySummary.year` 의미가 회계연도로 재해석.
- **`AssetInput`** 에 `fiscal_year_end_month: int = 12` 옵션 추가 (application 레이어 default=12, 한국 실무).
- **`depcal.py` CLI** 에 "13. 결산월 (1~12, default=12)" 입력 단계 추가.

### Added (회계기간 1급화의 코드 원칙)
- `AssetFinancials` 에 회계기간 필드 **추가하지 않음** — "자산은 회계기간을 모른다" 원칙. 회계기간은 회사의 회계정책이며 호출 컨텍스트.
- 엔진 함수 시그니처에 default 없음 — silent trap(v2.1에서 제거된 `target_year=2024` 패턴)과 동일 사유. 한국 실무 default=12는 application 레이어에서만 명시적 주입.

### Added (테스트)
- **`dep_cal/tests/test_fiscal_period_view.py`** (17개): 헬퍼 단위 검증 + 비-12월 결산 schedule 생성 + extract_fiscal_period view + v2.2 분리자산 가드 ValueError. 3·6·9·1월 결산 스모크 시나리오 포함.

### Added (문서)
- `dep_cal/specs/fiscal_period_first_class_spec.md`: 회계기간 1급 뷰 spec. 대원칙(자산은 회계기간을 모른다) + 책임 분리 + 한국 관행 표기 + 월할/결산월 잔재 보정 + yearly_info 재구성 + Acceptance Criteria + 회귀 시나리오 F-FP-01~10.

### Deferred (v2.3 분리)
- **분리자산 경로(`prior_accumulated`) fiscal year 일반화**: v2.1에서 정교하게 설계된 calendar year 가정이 깊이 박혀 있어 회귀 위험. 한국 실무 12월 결산이 분리자산의 99% 케이스라 영향 적음. v2.2 분리자산 경로는 `fiscal_year_end_month != 12` 호출 시 명시적 `ValueError` 발화 (v2.3 미지원 안내).

### dep_verify 영향
- dep_verify(별도 폴더)는 wrapper `calculate_from_common_format` 의 default=12로 12월 결산은 호환. 비-12월 결산 검증은 dep_verify 측 schema에 `fiscal_year_end_month` 컬럼 추가 + `extract_fiscal_period` view 적용 필요 (별도 작업).

## [2.1.0] - 2026-05-22

### Status
- 🔒 **Code Freeze 예외 적용** (사유 2번: 심각한 회계 오류)
- ⭐ **Quality**: Enterprise Grade (5/5) 유지
- ✅ **Compliance**: 한국 법인세법 [별표 4]
- ✅ **회귀**: pytest **105/105** (기존 21 + 매트릭스 영구화 84, 유·무형 전체양도/부분양도/자본적지출+양도 통합)

### Fixed (회계 정확성 critical)
- **🔴 매각 시간 인과율 위반 수정**: 양도 직전월에 잔여 장부가 거의 전부가 일괄상각되어 폭증하던 결함 제거. 양도 발생을 미리 알고 있던 것처럼 처리되어 직전월까지의 결산 마감 원칙에 위배되었음. 대원칙 *"매각은 직전월의 장부가액을 들여다 볼 뿐이며, 감가상각은 매월 정상적으로 회계장부에 반영된다"* 를 모든 매각·처분 경로(중도매각·부분매각·상각완료 자산 매각·폐기·자본적지출 후 매각)에 적용.
  - `_calculate_korean_straight_line_enhanced` (정액법 전체양도)
  - `_calculate_korean_declining_balance_enhanced` (정률법 전체양도)
  - `_calculate_with_increase` / `_calculate_with_increase_declining` (자본적지출+양도)
  - `_calculate_intangible_asset_enhanced` (무형자산 전체양도)
- **🟡 자본적지출 일자 검증**: `increase_date >= acquisition_date` 조건을 `AssetFinancials.__post_init__`에 추가. 취득 전 자본적지출 발생 불가 원칙 강제.
- **🟡 정률+자본적지출 부분양도 분기 분배 통일 (누락 수정)**: `_calculate_with_increase_declining` L1175 분기가 옛 패턴(`book_value_ratio` floor + 차감) 그대로 남아 시점에 따라 1원 차이 발생. 매트릭스 영구화 작업 중 발견. `round + 차감` 원칙으로 통일.

### Changed (회계 무결성·일관성)
- **부분양도 분배 통일**: `양도 누계 = round(원 누계 × disposal_amount / cost)`, `잔존 누계 = 원 누계 − 양도 누계` 단일 원칙으로 6곳 분배 로직 통합. 무결성(합 = 원본) 자동 보장.
  - `_calculate_with_partial_disposal` (정액법 부분양도, 2분기)
  - `_calculate_with_partial_disposal_declining` (정률법 부분양도)
  - `_calculate_with_increase` / `_calculate_with_increase_declining` 의 `is_partial_disposal` 분기
  - `_calculate_intangible_with_partial_disposal` (무형자산 부분양도)
- **처분비율 소수점 허용**: `depcal.py`에서 정수만 받던 처분비율 입력을 float으로 변경. `get_float_input` 헬퍼 추가.
- **`round_amount` → `to_int` rename**: 실제 동작이 `int()` 절사인데 명명이 "round"라 회계 도메인의 round/floor 혼동을 초래하던 부분 정정. 25곳 호출처 일괄 변경.

### Removed
- Dead 파라미터 `precision` (`round_amount` 시그니처)
- Dead 상수 `ROUNDING_PRECISION` (`dep_common.py`)

### Added (테스트)
- **`dep_cal/tests/test_disposal_invariants.py`**: 매각·처분 invariant 회귀 84개 영구화 (parametrize 기반). 직전월 동등성 + 분배 무결성 + 잔존 비망가 + 종료월. 유·무형 × 전체/부분 × 자본적지출 유무 매트릭스 총망라. 단발 검증으로 놓친 결함(정률+자본적지출 분기 누락)을 즉시 표면화하는 활성 검증 도구로 기능.

### Added (문서)
- `dep_cal/specs/monthly_settlement_preservation_spec.md`: 매각 월 결산 보존 대원칙 + 적용 범위 + Acceptance Criteria + 회귀 시나리오 (유·무형 통합).
- README "📐 계산 특성 / 정률법 마지막 달 폭증" 섹션 추가: 법령 5% 잔재 + 비망가 1,000원의 수학적 불가피성 설명 + 수치 예시.
- 정률법 비망가 처리 코드 주석에 회계·수학적 근거 명시.

## [2.0.0] - 2024-11-27

### Status
- 🔒 **Code Freeze**: Production Ready
- ⭐ **Quality**: Enterprise Grade (5/5)
- ✅ **Compliance**: Korean Corporate Tax Law

### Added

#### Core Calculation Engine
- **유형자산 정액법** (Straight Line Method for Tangible Assets)
  - 한국 법인세법 [별표 4] 상각률표 완벽 적용
  - 취득월 기반 월할 계산
  - 연말 보정 로직
  - 비망가액 1,000원 처리

- **유형자산 정률법** (Declining Balance Method for Tangible Assets)
  - 한국 법인세법 [별표 4] 상각률표 완벽 적용
  - 미상각잔액 기준 계산
  - 연말 보정 로직
  - 비망가액 1,000원 처리

- **무형자산 직접상각법** (Direct Method for Intangible Assets)
  - 취득원가 직접 차감 방식
  - 누계액 기록 유지
  - 비망가액 1,000원 처리

#### Advanced Features (Vector Logic)
- **자본적지출 처리** (Capital Expenditure)
  - Vector 합성 논리 구현
  - 증가 전후 정확한 계산
  - 통합 장부가액 관리
  - 정액법/정률법 모두 지원

- **부분양도 처리** (Partial Disposal)
  - Vector 축소 논리 구현
  - 양도비율 정확 계산
  - 잔존 비율 기반 계속 감가상각
  - 유형자산/무형자산 모두 지원

- **전체양도/폐기 처리** (Full Disposal/Retirement)
  - 양도 직전월까지 계산
  - 보정 없이 기본 월상각비 적용
  - 비망가액 남기지 않음

- **복합 시나리오** (Combined Scenarios)
  - 자본적지출 + 부분양도
  - 자본적지출 + 전체양도
  - 모든 조합 정확히 처리

#### User Interface
- **CLI 대화형 인터페이스** (Interactive CLI)
  - 사용자 친화적 입력 프롬프트
  - 입력값 자동 검증
  - 날짜/금액 다양한 형식 지원
  - 오류 처리 및 재입력

- **Excel 자동 생성** (Automatic Excel Generation)
  - 3시트 구조 (입력정보, 연도별집계, 월별상세)
  - 전문적인 포맷팅
  - 천단위 구분 및 정렬
  - 타임스탬프 파일명

#### API Interface
- **명확한 API 설계**
  - `calculate_depreciation_enhanced()`: 메인 계산 함수
  - `AssetFinancials`: 재무 정보 데이터클래스
  - `AssetInfo`: 자산 기본 정보 데이터클래스
  - `DepreciationResult`: 결과 데이터클래스
  - `MonthlyDepreciation`: 월별 감가상각 정보

- **파일간 인터페이스**
  - `convert_common_data_to_financials()`: 더존 형식 변환
  - `calculate_from_common_format()`: 공통 형식 계산
  - fixed_asset 모듈과 완벽한 호환성

### Technical Achievements

#### Accuracy
- ✅ **Integer 기반 계산**: 반올림 오차 0
- ✅ **Vector 논리**: 수학적 우아함
- ✅ **법인세법 준수**: 상각률표 완벽 적용
- ✅ **회계 정확성**: 100% (오차 없음)

#### Performance
- ⚡ **2ms/60개월**: 매우 빠른 계산 속도
- ⚡ **최적화된 알고리즘**: 불필요한 반복 없음

#### Code Quality
- 📝 **타입 힌트**: 모든 함수에 적용
- 📝 **데이터클래스**: @dataclass 활용
- 📝 **로깅**: 상세한 계산 과정 기록
- 📝 **오류 처리**: try-except + 검증

#### Testing
- ✅ **12가지 시나리오 검증**
- ✅ **9가지 엣지 케이스 처리**
- ✅ **실행 샘플 파일**: output/ 폴더

### Architecture

#### Module Structure
```
dep_cal/
├── depcal.py                    # CLI Interface
├── asset_schedule_generator.py # Excel Generator
├── requirements.txt             # Dependencies
└── core/                        # Calculation Engine (Frozen)
    ├── depreciation_engine.py  # Wrapper
    ├── dep_common.py           # Common (1,557 lines)
    ├── dep_tang_engine.py      # Tangible Assets
    ├── dep_intang_engine.py    # Intangible Assets
    └── utils.py                # Utilities
```

#### Design Patterns
- **Separation of Concerns**: CLI, Calculation, Output
- **Dataclass Pattern**: Type safety
- **Wrapper Pattern**: depreciation_engine.py
- **Strategy Pattern**: Method-specific engines

### Dependencies
- openpyxl >= 3.0.0 (Excel generation)
- python-dateutil >= 2.8.0 (Date processing)

### Supported Scenarios

| # | Scenario | 정액법 | 정률법 | 무형자산 |
|---|---------|-------|-------|---------|
| 1 | 기본 감가상각 | ✅ | ✅ | ✅ |
| 2 | 자본적지출 | ✅ | ✅ | ❌ |
| 3 | 부분양도 | ✅ | ✅ | ✅ |
| 4 | 전체양도/폐기 | ✅ | ✅ | ✅ |
| 5 | 자본적지출 + 부분양도 | ✅ | ✅ | ❌ |
| 6 | 자본적지출 + 전체양도 | ✅ | ✅ | ❌ |

### Known Issues
- **Unicode Display**: Windows에서 이모지 표시 문제 (UTF-8 환경 변수 설정 필요)
  - 해결 방법: `PYTHONIOENCODING=utf-8` 설정 또는 이모지 제거 버전 사용

### Intentional Limitations
- **무형자산 자본적지출**: 지원하지 않음 (세법상 불필요)
- **복수 자본적지출**: 단일 증가 이벤트만 지원
- **복수 부분양도**: 단일 양도 이벤트만 지원

### Compliance & Certification
- ✅ **Korean Corporate Tax Law**: 법인세법 시행령 제26조
- ✅ **Depreciation Rate Table**: 법인세법 [별표 4]
- ✅ **Memorandum Value**: 1,000원 (법인 46012-3734, 1999.10.14)
- ✅ **IFRS & K-GAAP**: 정액법/정률법 모두 지원

### Credits
Developed with Claude (Anthropic AI)

---

## [1.0.0] - 2024-XX-XX (Historical)

### Initial Release
- Basic depreciation calculation
- (Details not documented)

---

## Future Plans

### Not Planned (Code Freeze)
이 프로젝트는 v2.0.0부터 코드 동결 상태입니다.

### Exception Cases
다음 경우에만 업데이트됩니다:
1. 한국 세법 변경 (법인세법 개정)
2. 심각한 회계 오류 발견
3. 보안 취약점 수정

### New Features
신규 기능은 `dep_cal_ext/` 별도 모듈로 추가됩니다.

---

## Version History

- **v2.0.0** (2024-11-27): Production Release - Code Freeze
- **v1.0.0** (2024-XX-XX): Initial Release
