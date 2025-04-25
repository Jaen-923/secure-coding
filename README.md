# 🛡️ Secure Coding

Tiny Second-hand Shopping Platform을 개발하며,
사용자 인증, 상품 거래, 포인트 송금 기능을 포함한 전 과정을 보안 중심으로 구현하였습니다.

<br>

⭐️보안 강화 조치

- 사용자 비밀번호 해시화(bcrypt 사용)
- 개발용 console.log/print문 삭제로 민감 정보 노출 방지
- 비밀번호 규칙 검증(길이, 특수문자 포함 등) 적용
- CORS 설정을 통한 교차 출처 접근 제어
- SQL Injection 방지를 위한 파라미터 바인딩 사용
- 민감 정보(.env에 저장한 시크릿 키 등) 외부 노출 방지
  
<br>

---

<br>

### 사전 요구사항

- Python 3.x
- [Miniconda 또는 Anaconda](https://docs.anaconda.com/free/miniconda/index.html) 설치

<br>
<br>

### 설치 및 실행 방법

#### 1. 저장소 클론

```bash
git clone https://github.com/Jaen-923/secure-coding
cd secure-coding
```

#### 2. Conda 환경 생성

```bash
conda env create -f enviroments.yaml
conda activate secure-coding  
```

#### 3. 추가 패키지 설치
```bash
pip install python-dotenv flask-cors bcrypt
```

#### 4. 서버 실행
```bash
python app.py
```
