# API Source Mapping

이 문서는 승인받은 외부 API를 MK-MAP 엔진에 연결하기 위한 실제 매핑 상태를 정리한다. 비밀키는 여기에 적지 않고, 배포 환경변수에만 둔다.

## 확인 완료

| 서비스 | 엔진 | Base URL | Operation | 남은 작업 |
| --- | --- | --- | --- | --- |
| 기상청 작물별 농업주산지 상세날씨 | `agri_weather` | `http://apis.data.go.kr/1360000/FmlandWthrInfoService` | `getDayStatistics` | 품목별 `PA_CROP_SPE_ID`, 주산지별 `AREA_ID` 매핑 |
| 기상청 기상특보 | `disaster_event` | `http://apis.data.go.kr/1360000/WthrWrnInfoService` | `getWthrWrnList` | 특보 지역코드와 MK-MAP 지역코드 매핑 |
| 기상청 태풍정보 | `disaster_event` | `http://apis.data.go.kr/1360000/TyphoonInfoService` | `getTyphoonInfo` | 목록 조회 후 `tmFc` 선택 흐름 |
| 기상청 중기예보 | `forecast_context` | `http://apis.data.go.kr/1360000/MidFcstInfoService` | `getMidFcst` | 지역별 `stnId` 매핑 |

공식 근거:

- 기상청 작물별 농업주산지 상세날씨: https://www.data.go.kr/data/15059518/openapi.do
- 기상청 기상특보: https://www.data.go.kr/data/15000415/openapi.do
- 기상청 태풍정보: https://www.data.go.kr/data/15043565/openapi.do
- 기상청 중기예보: https://www.data.go.kr/data/15059468/openapi.do

## 추가 확인 필요

| 서비스 | 필요한 정보 |
| --- | --- |
| KAMIS 지역별 품목별 도소매 가격정보 | 요청 URL, 품목/부류/품종 코드, 응답 필드 |
| aT 지역별 품목별 도소매 가격정보 | 첨부 API 명세의 endpoint/operation, 품목코드 |
| aT 전국 공영도매시장 정산정보 | 첨부 API 명세의 endpoint/operation, 시장/품목코드 |
| RDA 농업기상 상세 관측데이터 | 관측지점 코드, 조회 단위, endpoint/operation |
| 기상청 영향예보 | 폭염/한파 operation, 지역코드 |

## KMA 주산지 후보 매핑 상태

현재 5개 핵심 품목에는 `external_mappings.kma_crop_weather` 슬롯을 추가했다.

- `mapping_status: candidate_regions_only`: 후보 주산지는 있으나 공식 `PA_CROP_SPE_ID`, `AREA_ID` 미확정
- `mapping_status: verified`: 공식 코드표 기준으로 실제 호출 가능

상태 확인:

```powershell
python scripts/show_external_mapping_status.py
python scripts/validate_external_mappings.py
```

## KMA 코드표 반영

공공데이터포털의 활용가이드 첨부자료에서 `PA_CROP_SPE_ID`, `AREA_ID`를 확인한 뒤 아래 CSV에 채운다.

```text
config/external_mappings/kma_crop_weather_template.csv
```

반영 전 미리보기:

```powershell
python scripts/import_kma_crop_weather_mapping.py
```

품목 JSON에 실제 반영:

```powershell
python scripts/import_kma_crop_weather_mapping.py --apply
python scripts/validate_external_mappings.py
```

import 동작 자체는 임시 CSV로 검증할 수 있다.

```powershell
python scripts/smoke_kma_mapping_import.py
```

코드표가 `verified`로 반영되고 `DATA_GO_KR_API_KEY`가 환경변수에 있을 때 라이브 호출을 확인한다.

```powershell
python scripts/test_live_kma_crop_weather.py --item cabbage --date 2026-06-29
```

기상특보는 주산지 코드 매핑 없이 `DATA_GO_KR_API_KEY`만 있으면 먼저 테스트할 수 있다.

```powershell
python scripts/test_live_weather_alert.py --date 2026-06-29
python scripts/test_live_typhoon.py --date 2026-06-29
python scripts/test_live_midterm_forecast.py --date 2026-06-29
```

## 품목 메타데이터 확장 예시

```json
{
  "external_mappings": {
    "kma_crop_weather": {
      "pa_crop_spe_id": "PA020101",
      "area_ids": ["4827000001"]
    },
    "kamis": {
      "item_code": "211",
      "kind_code": "01"
    }
  }
}
```

`external_mappings`는 품목별 JSON에 선택적으로 추가한다. 매핑이 없으면 라이브 커넥터는 호출을 건너뛰고, 기존 수동 주산지 메타데이터 기반 신호는 계속 생성된다. `area_ids`가 여러 개면 KMA 주산지 날씨 커넥터가 지역별로 순회 호출한다.

## Newly Confirmed Endpoints

- AT regional price: `http://apis.data.go.kr/B552845/perRegion` with operation `price`.
- AT market settlement: `http://apis.data.go.kr/B552845/katSale` with operation `trades`.
- RDA agri weather: `http://apis.data.go.kr/1390802/AgriWeather/WeatherObsrInfo/V4/InsttWeather` with operation `getWeatherMonDayList4`.
- KMA impact forecast: `http://apis.data.go.kr/1360000/ImpactInfoServiceV2` with operation `getHWImpactValueV2`.

These are reflected in `.env.example` and `config/api_services.json`. KMA impact forecast, AT regional price, AT market settlement, and RDA agri weather now have live diagnostics.

## 요청 프리뷰

공식 endpoint가 확인된 API는 아래 명령으로 샘플 호출 형태를 확인한다. 인증키 값은 출력하지 않는다.

```powershell
python scripts/preview_api_requests.py
```

환경변수 준비 상태는 값 노출 없이 아래 명령으로 확인한다.

```powershell
python scripts/check_env_status.py
```
