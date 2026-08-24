"""
dep_vector — 무형자산 슬림 코어 (직접상각법, 별표4 상각률)
========================================================

무형자산은 정액법으로 상각하되, 감가상각누계액 계정을 쓰지 않고 취득원가에서 직접
차감하는 직접상각법을 쓴다. 직접상각은 **표시(재무제표) 차이일 뿐 상각액·장부가는
정액법과 동일** — 엔진 수치에는 영향이 없다.

상각률은 법인세법 [별표4] 정액법 상각률을 사용한다 (= round(cost × 별표4율)).
  - 4·5·8·10년: 별표4율 = 1/내용연수 → 1/n 직접 나눗셈과 동일(과거 실무가 4·5년이라 무차이)
  - 3·6·7·9·11·12…년: 별표4율은 1/n을 소수 3자리 절사 → 1/n과 다름. **별표4가 정답.**
    (사용자 도메인 판단 2026-06-02: 무형도 별표4 상각률을 쓴다.)

따라서 무형자산 = 유형 정액법과 회계연도 수치 동일. 단순취득·자본적지출·양도 모두
유형 정액법 슬림을 그대로 재사용한다.

주의: 무형 검증의 oracle은 별표4(=유형 정액 슬림)다. 과거 core/dep_intang_engine.py 의
무형 함수는 base_annual = int(cost // life) 로 1/n 직접 나눗셈이라 3·6·7·9년 등에서
별표4와 어긋났으나, 2026-06-16부터 core(depreciation_engine)의 무형 경로 전체가 유형
정액 함수를 재사용해 별표4로 통일됐다(core==vcore 1원 일치). dep_intang_engine 의 1/n
함수는 단위 테스트가 직접 호출하므로 잔존하나 실행 경로에서는 더 이상 쓰이지 않는다.
"""

from vcore import straight_line, capex, disposal

# 무형자산 = 별표4 정액법. 직접상각은 표시 차이일 뿐 수치 동일 → 유형 정액 슬림 재사용.
schedule = straight_line.schedule
schedule_with_increase = capex.schedule_with_increase
schedule_full_disposal = disposal.schedule_full_disposal
schedule_partial_disposal = disposal.schedule_partial_disposal
