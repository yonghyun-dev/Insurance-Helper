# 같은 와이파이인데 나만 SSH가 막힌다 — 범인은 Wi-Fi 칩셋이었다

> GPU 서버 접속 트러블슈팅. 결론부터 말하면 **노트북에 들어간 Wi-Fi 칩셋 제조사(MAC OUI)에 따라 회사 라우터가 외부 회선을 다르게 매핑**하고 있었다는 이야기.

---

## TL;DR

- 회사가 신청한 IP(`AAA.BBB.0.x`)는 잘 등록됐다.
- 그런데 **내 노트북만** 그 IP가 아니라 **다른 공인 IP(`CCC.DDD.x.x`)로 인터넷에 나간다.**
- 같은 사무실, 같은 와이파이, 같은 AP에 붙어있는데도 그렇다.
- 원인은 회사 라우터의 **OUI 기반 WAN 분기 정책**.
  - Intel Wi-Fi 칩셋(팀원들 LG 노트북) → 메인 회선
  - 그 외 칩셋(내 Acer + MediaTek MT7925) → 백업 회선
- 회사 라우터는 디바이스를 식별할 때 MAC 주소의 앞 3바이트(OUI)를 보는데, Intel OUI만 메인 회선 화이트리스트에 들어가 있었다.

---

## 0. 발단

GPU 서버 접속 정보를 받았다.

```
서버 IP: XXX.XX.XX.XXX
ID/PW: tta / ********
허용된 접속 IP: AAA.BBB.0.129  ← 회사 사무실 IP
```

회사 사무실 와이파이에서만 SSH로 들어올 수 있다는 뜻이다. 보안 정책상 흔한 구성.

평범하게 SSH를 띄웠다.

```powershell
ssh tta@XXX.XX.XX.XXX
```

```
ssh: connect to host XXX.XX.XX.XXX port 22: Connection timed out
```

**타임아웃**. 핑도 안 간다. TCP 22가 막힌 게 아니라 **IP 자체가 차단**되는 전형적인 화이트리스트 DROP 패턴이다.

## 1. "내 공인 IP가 사무실 IP 맞나?"

가장 먼저 의심해야 할 것. 외부 IP 조회 서비스로 확인.

```powershell
curl https://ipinfo.io/ip
# → CCC.DDD.XX.XXX
```

신청한 `AAA.BBB.0.129`와 **완전히 다른 IP**가 나왔다. 더 충격적인 사실은 두 IP가 ISP는 같지만(둘 다 KT) 대역이 완전히 달랐다는 것.

```
사무실 신청 IP:    AAA.BBB.0.129    (KT, Seoul)
내 노트북 outbound: CCC.DDD.XX.XXX  (KT, Seoul)
```

같은 ISP인데 IP 대역이 다르다? 일단 단순한 가설부터 잘라 나간다.

## 2. 가설 1: WSL 안에서 신청해서 그런가?

> Windows에서 작업할 때 흔히 WSL을 쓰는데, WSL이 NAT 모드면 호스트와 다른 IP로 나갈 수 있나?

```powershell
wsl -- curl -s https://ipinfo.io/ip
# → CCC.DDD.XX.XXX  (호스트와 동일)
```

호스트와 같다. WSL2는 호스트의 네트워크 스택을 NAT로 공유하기 때문에 외부에서 보면 같은 공인 IP다. **기각.**

## 3. 가설 2: 사실 다른 네트워크에 잡혀있는 건가?

VPN, 핫스팟, 게스트 와이파이 등.

```powershell
# 활성 네트워크 인터페이스 확인
Get-NetIPConfiguration | Where-Object { $_.IPv4Address -ne $null }

# 기본 게이트웨이 확인 (인터넷으로 나가는 경로)
Get-NetRoute -DestinationPrefix "0.0.0.0/0"

# 시스템 프록시
netsh winhttp show proxy

# VPN 클라이언트 프로세스
Get-Process | Where-Object { $_.ProcessName -match "vpn|wire|tailscale|warp|globalprotect" }

# 와이파이 SSID/BSSID
netsh wlan show interfaces | findstr "SSID BSSID"
```

결과:
- Wi-Fi 단일 인터페이스, default route도 단일
- 프록시 없음, VPN 프로세스 없음, 핫스팟 없음
- SSID: `Company-AP1`, BSSID: `34:98:b5:XX:XX:XX`

깨끗하다. 노트북에 이상한 변수는 없다. **기각.**

## 4. 가설 3: 내가 IP를 고정으로 박아둔 건가?

```powershell
Get-NetIPAddress -InterfaceAlias "Wi-Fi" -AddressFamily IPv4 |
    Select-Object IPAddress, PrefixOrigin, SuffixOrigin
```

```
IPAddress     PrefixOrigin  SuffixOrigin
---------     ------------  ------------
172.30.1.93   Dhcp          Dhcp
```

`PrefixOrigin/SuffixOrigin = Dhcp` → DHCP로 자동 할당 받음. 정적 박은 거 없음.

그리고 더 본질적으로, **공인 IP는 노트북에서 정할 수 있는 게 아니다.** 그건 라우터의 NAT가 정하는 거다. 일찍 이걸 인지했어야 했는데 한 번 혼동했다. **기각.**

## 5. 결정적 단서: 옆자리 팀원과 비교

여기서 의미있는 데이터가 나왔다. 팀원 노트북에서 SSID/BSSID를 찍어보니:

```
내 노트북:    SSID=Company-AP1, BSSID=34:98:b5:XX:XX:XX
팀원 노트북:  SSID=Company-AP1, BSSID=34:98:b5:XX:XX:XX   ← 동일

공인 IP:     CCC.DDD.XX.XXX   vs   AAA.BBB.0.XXX           ← 다름
```

**같은 AP에 같이 붙어있는데 공인 IP만 다르다.**

이쯤 되면 와이파이 인프라(AP, SSID) 단계의 문제가 아니라, **AP 뒤쪽 라우터에서 클라이언트별로 WAN 회선을 분기**하고 있다는 결론이 나온다.

## 6. 가설 4: 노트북 브랜드 차이? — 거의 맞았다

팀원의 한마디:
> "다른 사람들은 다 LG 노트북인데 너만 Acer잖아."

브랜드 자체가 변수일 리는 없지만, **브랜드가 다르면 그 안에 들어간 Wi-Fi 칩셋도 다르다.** 그리고 MAC 주소의 앞 3바이트(OUI)는 **칩셋 제조사**를 나타낸다. 라우터/방화벽이 OUI 기반 정책을 가질 가능성은 충분히 있다.

내 Wi-Fi 칩셋 확인:

```powershell
Get-NetAdapter -Name "Wi-Fi" | Select-Object MacAddress, InterfaceDescription
```

```
MacAddress           InterfaceDescription
----------           --------------------
58-02-05-XX-XX-XX    MediaTek Wi-Fi 7 MT7925 Wireless LAN Card
```

MAC OUI `58:02:05`를 lookup:

```powershell
Invoke-RestMethod "https://api.macvendors.com/58:02:05"
# → AzureWave Technology Inc.
```

- **내 Acer**: MediaTek MT7925 (AzureWave 모듈)
- **팀원 LG (추정)**: Intel Wi-Fi (LG 노트북은 거의 다 Intel 칩셋)

## 7. 가설 검증: 사내 노트북 전수 조사

팀원들에게 부탁해서 칩셋별 IP를 모아봤다.

| 칩셋 | 공인 IP |
|:--|:--|
| Intel Wi-Fi | `AAA.BBB.0.129` ← 메인 회선 |
| MediaTek (내 Acer) | `CCC.DDD.XX.XXX` ← 백업 회선 |
| 다른 비-Intel | `CCC.DDD.XX.XXX` ← 백업 회선 |

**완벽하게 갈렸다.** 가설 확정.

## 8. 진짜 원인

회사 라우터에 다음과 같은 정책이 걸려 있는 것으로 추정:

```
[클라이언트 MAC OUI별 WAN 분기]
- Intel OUI       → 메인 회선 (고정 IP, AAA.BBB.0.x)
- 그 외 OUI       → 백업 회선 (KT 일반 회선, CCC.DDD.x.x)
```

왜 이렇게 해놓았을지 가능성:

1. **NAC(Network Access Control) 정책** — 사내 표준 디바이스(LG=Intel)만 메인 회선에 들이고, 외부 디바이스는 게스트 회선으로 격리
2. **자산 등록 시스템 누락** — IT가 회선 정책 만들 때 Intel OUI만 화이트리스트에 넣고 다른 vendor 대응을 빠트림

회사 정책이 의도된 것이든 누락이든, **결과적으로 비-Intel 칩셋 디바이스는 GPU 서버 화이트리스트에 안 잡힌 회선으로 떨궈진다.**

## 9. 해결책

### 단기 (당장 작업 시작)

GPU 서버 관리자에게 백업 회선 IP도 화이트리스트 추가 요청:

```
GPU 서버 방화벽에 CCC.DDD.XX.XXX 추가 부탁드립니다.
단, 백업 회선이 동적 IP일 가능성이 있어 추후 변경 시 다시 요청드릴 수 있습니다.
```

### 중기 (근본 해결)

회사 IT 담당자에게 OUI 정책 수정 요청:

```
제 노트북(MAC: 58-02-05-XX-XX-XX)을 메인 회선 화이트리스트에 추가 부탁드립니다.
비-Intel 칩셋이라 자동으로 백업 회선으로 분기되는 것 같습니다.
향후 다른 비-Intel 노트북 입사자도 동일 문제 겪을 것으로 예상됩니다.
```

마지막 줄이 중요하다. "팀 전체 이슈"로 인식되면 우선순위가 올라간다.

### 임시 우회 (위 둘 다 늦을 때)

- **MAC 위장**: 어댑터 속성에서 Locally Administered Address를 Intel 대역으로 임시 변경 (보안 정책 위반 소지 있음, 권장 안 함)
- **USB Wi-Fi 동글** (Intel 칩셋, 2~3만원): 합법적이고 안정적
- **유선 LAN**: 사무실에 LAN 포트 있으면 시도 (유선은 정책이 다를 수도 있음)
- **모바일 핫스팟**: 즉시 가능하지만 그 IP도 등록 필요

## 10. 검증

팀원 LG 노트북(Intel 칩셋, 메인 회선)에서 SSH 시도:

```bash
ssh tta@XXX.XX.XX.XXX
```

**한 번에 접속 성공.** OUI 정책 가설 100% 확정.

## 회고

### 트러블슈팅에서 배운 것

1. **공인 IP의 결정자는 NAT/라우터다.** 노트북 단에서 공인 IP를 정할 수 없다는 사실을 처음에 명확히 인식했어야 했다.
2. **같은 SSID라도 인프라가 같다는 보장은 없다.** AP가 여러 대고 회선이 여러 개면 분기가 가능하다. BSSID, 그리고 WAN까지 봐야 한다.
3. **단순한 가설부터 잘라 나가는 게 효율적이다.** WSL → 네트워크 인터페이스 → 정적 IP → 같은 AP까지 차례로 제거한 덕에, 결정적 단서(같은 AP인데 다른 공인 IP)가 명확히 떠올랐다.
4. **OUI 기반 정책은 실무에서 의외로 흔하다.** NAC 솔루션 쓰는 회사라면 더더욱.

### IT 인프라에 대한 작은 제언

회사가 비-Intel 칩셋을 의도적으로 격리한 게 아니라 **단순 누락**이라면, 디바이스 vendor가 다양해지는 추세에서 이런 정책은 운영 부담을 키운다. **MAC 단위 화이트리스트** 또는 **사용자 단위 인증(802.1X)** 으로 가는 게 장기적으로 더 깔끔하다.

### 5분짜리 문제 같았지만

ID/PW만 받으면 30초 만에 끝날 줄 알았던 작업이 **노트북 칩셋 OUI까지 추적해야 풀리는 문제**가 됐다. 트러블슈팅의 묘미라면 묘미. 그래도 다음에 비슷한 상황 만나면 BSSID부터 비교할 듯.

---

**한 줄 결론**: 회사 와이파이에서 나만 외부 서버에 못 들어간다면, **MAC OUI와 회사 라우터의 회선 분기 정책**을 의심해보자.
