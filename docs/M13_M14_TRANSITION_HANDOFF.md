# YouTube Shorts Bot V2 — M13 → M14 Geçiş / Talimat Dosyası

**Amaç:** Bu dosya, M13'te tamamlanan kontrollü otomatik optimizasyon katmanını M14 production hardening aşamasına taşımak için hazırlanmıştır. Yeni sohbete bu dosya eklenerek çalışmaya devam edilebilir.

**Son doğrulanmış ana dal:** `9e81fc702d911f666b2f90714b59262fafa35b1e`  
**M13 implementation exit SHA:** `40e264a47e2dd65a597acdb1e4dae5f09cce4aba`  
**M13 exit audit:** `docs/M13_EXIT_AUDIT.md`  
**Son M13 exit:** PASS / COMPLETE  
**Son test doğrulaması:** 310 tests passed (M13 PR #77 CI #502)

---

# 1. PROJENİN ANA HEDEFİ

Repository:

`emrtasknn/youtube-shorts-bot-v2`

Sistem hedefi:

- provider-agnostic
- failure-tolerant
- cost-controlled
- deterministic
- auditable
- human-in-the-loop
- performans verisinden kontrollü öğrenen
- üretim pipeline'ına güvenli biçimde karar aktarabilen
- ileride ölçeklenebilir Shorts üretim sistemi

Temel ilke:

```
Reliability
    ↓
Correctness
    ↓
Video Quality
    ↓
Automation
    ↓
Intelligence
    ↓
Optimization
```

M14'e geçerken bu sıra korunmalıdır.

---

# 2. M9 → M13 GELİŞİM ZİNCİRİ

## M9 — Learning / Recommendation

M9 tamamlandı.

Zincir:

```
Performance Memory
    ↓
Feature Extraction
    ↓
Evidence + Confidence
    ↓
Learning Signal
    ↓
Recommendation Engine
    ↓
Persistence
    ↓
Query
```

M9 özellikleri:

- deterministic
- confidence-aware
- baseline-aware
- insufficient / low / medium / high confidence
- positive/negative/neutral direction
- idempotent recommendation persistence
- deterministic querying

M9 sınırı:

```
Observe → Understand → Recommend
```

Recommendation doğrudan provider veya generator'ı değiştirmez.

---

## M10 — Production Decision

M10 tamamlandı.

Zincir:

```
Recommendation
    ↓
Decision Policy
    ↓
ProductionDecision
    ↓
Generation Input
```

Kontrol edilen dimension'lar:

- angle
- duration_target_seconds
- production_strategy

M10 güvenlikleri:

- minimum confidence
- baseline availability
- positive signal
- deterministic conflict resolution
- applied/rejected audit IDs
- policy version
- stale policy rejection
- recommendation reuse guard
- rollback
- regression coverage

Kritik invariant:

**Recommendation doğrudan production davranışını değiştiremez.**

---

## M11 — Topic Optimization

M11 tamamlandı.

Zincir:

```
Topic Candidate Set
    ↓
Eligibility / Data Quality
    ↓
Topic Evidence
    ↓
Topic Score
    ↓
Topic Selection Decision
    ↓
Production / Generation Boundary
```

M11 özellikleri:

- deterministic topic scoring
- fixed explainable weights
- novelty-aware selection
- historical performance only when comparable
- cold-start safe normalization
- minimum score policy
- deterministic tie-breaking
- persisted TopicSelectionDecision
- production adapter
- M10 compatibility
- regression/failure tests

Kritik invariant:

**Topic optimization, M10 güvenlik sınırını bypass etmez.**

---

## M12 — Controlled Experimentation

M12 tamamlandı.

Zincir:

```
Experiment
    ↓
Deterministic Assignment
    ↓
Outcome Evidence
    ↓
Minimum-Sample-Gated Analysis
    ↓
Explicit Production Adapter
    ↓
Generation Input
```

Desteklenen experiment dimension'ları:

- TOPIC
- ANGLE
- DURATION_TARGET_SECONDS

M12 özellikleri:

- immutable experiment contracts
- deterministic assignment
- ACTIVE-only assignment
- balanced minimum sample requirement
- deterministic winner
- weighted average views
- idempotent persistence
- conflict-safe persistence
- explicit production adapter
- M10/M11 conflict protection
- no autonomous publishing
- no automatic policy mutation

Kritik invariant:

```
Experiment result ≠ automatic production policy
```

---

# 3. M13 — CONTROLLED AUTOMATED OPTIMIZATION

M13 tamamlandı.

M13'ün ana problemi:

M12 bir experiment'ın kazananını bulabiliyordu fakat şu soruya kontrollü ve audit edilebilir bir cevap vermiyordu:

> Hangi şartlarda experiment sonucu production optimization policy'ye terfi ettirilebilir?

M13 bu sınırı ekledi:

```
ExperimentAnalysis
    ↓
OptimizationPolicy Gate
    ↓
OptimizationDecision
    ↓
Production Adapter
    ↓
Generation Input
```

## M13 domain

Eklenen temel kavramlar:

- `OptimizationPolicy`
- `OptimizationDecision`
- `OptimizationDecisionStatus`

Status'ler:

- `PROMOTED`
- `NO_PROMOTION`
- `ROLLED_BACK`

Default policy:

- minimum uplift = **10%**
- minimum confidence = **HIGH**

Confidence bantları:

- 0 → INSUFFICIENT
- 3–5 → LOW
- 6–14 → MEDIUM
- 15+ → HIGH

Promotion için:

1. experiment analysis hazır olmalı
2. winner mevcut olmalı
3. comparable control bulunmalı
4. control performansı kullanılabilir olmalı
5. minimum uplift aşılmalı
6. minimum confidence aşılmalı
7. supported experiment dimension kullanılmalı
8. policy version açıkça belirtilmeli

M13 decision:

- deterministic
- explainable
- auditable
- persisted
- reversible
- conflict-safe

---

# 4. M13 PERSISTENCE / AUDIT

Yeni persistence:

`optimization_decisions`

Migration:

`0010_m13_optimization_decisions`

Audit alanları:

- decision_id
- policy_version
- status
- experiment_id
- dimension
- winner_variant_id
- value
- control_variant_id
- uplift
- confidence
- rationale
- created_at

Persistence conflict-safe olmalıdır.

Aynı karar kimliğiyle farklı içerik sessizce overwrite edilmemelidir.

---

# 5. M13 PRODUCTION BOUNDARY

M13 production adapter:

`OptimizationProductionAdapter`

Kurallar:

### PROMOTED
Explicit generation input üretilebilir.

### NO_PROMOTION
Generation override üretmez.

### ROLLED_BACK
Production'a uygulanamaz.

### M10 conflict
Optimization angle/duration, explicit M10 ProductionDecision değerini sessizce override edemez.

### M11 conflict
Optimization topic, explicit selected M11 TopicSelectionDecision değerini sessizce override edemez.

### Stale policy
Eski optimization policy version reddedilir.

### Provider isolation
Optimization layer hiçbir provider seçmez veya provider configuration değiştirmez.

---

# 6. M13 REVERSIBILITY

Rollback yeni bir decision üretir:

```
PROMOTED
    ↓
ROLLBACK
    ↓
ROLLED_BACK
```

Rollback:

- original decision'ı mutate etmez
- yeni decision ID üretir
- provenance'ı korur
- production adapter tarafından uygulanamaz
- audit history'yi silmez

Kritik invariant:

**Optimization kararları geri alınabilir olmalıdır.**

---

# 7. M13 TEST / CI SONUCU

M13 PR #76:

- controlled optimization policy layer
- CI #497
- 308 tests passed
- Ruff PASS
- format PASS
- mypy PASS
- Alembic PASS
- Docker PASS

Merge SHA:

`2cbd312ab5ad3e80d518784d359b193fd9208703`

M13 PR #77:

- rollback
- optimization safety gate
- stale policy protection
- rollback regression
- CI #502
- **310 tests passed**
- Ruff PASS
- format PASS
- mypy PASS
- Alembic PASS
- Docker PASS

Merge SHA:

`40e264a47e2dd65a597acdb1e4dae5f09cce4aba`

M13 exit audit PR #78:

- `docs/M13_EXIT_AUDIT.md`
- final docs commit:
`9e81fc702d911f666b2f90714b59262fafa35b1e`

M13 status:

**PASS / COMPLETE**

---

# 8. M14'ÜN BAŞLANGIÇ NOKTASI

M14 artık intelligence/optimization feature geliştirmeye devam etmek yerine sistemi production-grade hale getirmelidir.

M13 sonrası temel zincir:

```
Performance Memory
    ↓
Learning
    ↓
Recommendation
    ↓
ProductionDecision
    ↓
TopicSelectionDecision
    ↓
Experimentation
    ↓
OptimizationDecision
    ↓
Generation Input
    ↓
Human Approval
    ↓
Publishing
    ↓
Performance Memory
```

M14 bu zincirin güvenilirliğini, gözlemlenebilirliğini, maliyet kontrolünü ve ölçeklenebilirliğini güçlendirmelidir.

---

# 9. M14 ANA HEDEFLERİ

M14 aşağıdaki alanları production hardening kapsamında ele almalıdır:

## A. Reliability

- retry
- exponential backoff
- circuit breaker
- dead-letter / permanent failure state
- idempotency
- stuck-run detection
- stuck-run recovery
- provider outage handling
- partial failure handling
- safe resume
- duplicate generation prevention

## B. Observability

Structured observability:

- run events
- stage events
- provider events
- provider latency
- provider failures
- retry counts
- fallback events
- QC failures
- publication events
- optimization events
- cost events

Event alanları mümkün olduğunca:

- timestamp
- run_id
- stage
- provider
- model
- latency
- status
- error_code
- cost

ile ilişkilendirilmeli.

## C. Cost Control

- estimated cost
- actual cost
- provider budget
- daily budget
- monthly budget
- quota awareness
- graceful degradation
- expensive provider protection
- cost audit

Testlerde ücretli API kullanılmamalıdır.

## D. Provider Health

Provider başına:

- health status
- latency
- error rate
- 429 count
- quota usage
- cooldown state
- last success
- last failure

gibi ölçümler ileride router kararlarını destekleyebilmelidir.

Provider health, provider-specific business logic'e dönüşmemelidir.

## E. Scale

- queue semantics
- concurrency control
- batch orchestration
- rate limiting
- duplicate prevention
- provider quota awareness
- safe parallel execution

M14'te doğrudan 10/day gibi agresif ölçek hedeflerine atlanmamalı; önce bounded concurrency ve güvenli execution kurulmalıdır.

## F. Security

Production hardening:

- secret handling
- token rotation
- webhook validation
- OAuth credential protection
- sensitive data redaction
- logs içinde secret leakage prevention

Asla secret değerlerini source code, test fixture, log veya dokümana koyma.

## G. Quality / QC

M14 reliability ile birlikte quality gate'leri de güçlendirebilir:

- script completeness
- subtitle completeness
- audio completeness
- scene timing
- visual relevance
- hook quality
- duration consistency
- output artifact integrity

Quality failures retryable/permanent olarak sınıflandırılmalıdır.

---

# 10. M14.0 — İLK GÖREV: REPOSITORY AUDIT

M14'e doğrudan kod yazarak başlanmayacak.

İlk görev:

**M14.0 Repository / Production Hardening Audit**

Audit sırasında:

1. mevcut Run/Stage state machine
2. retry mekanizması
3. provider abstraction
4. provider health
5. cost tracking
6. artifact management
7. logging/event sistemi
8. approval/publishing
9. database schema
10. idempotency
11. failure states
12. Docker/CI
13. secrets/config
14. QC
15. current generation path

incelenmeli.

Audit çıktısı:

- mevcut mimari
- eksikler
- production riskleri
- dosya bazlı değişiklik planı
- dependency graph
- migration ihtiyacı
- test planı
- PR backlog
- risk sıralaması

**Audit tamamlanmadan M14 feature implementation başlamamalıdır.**

---

# 11. M14 ÖNERİLEN FAZLAR

Kesin breakdown M14.0 audit sonrası güncellenecek.

Başlangıç önerisi:

### M14.0 — Production Hardening Audit
Read-only.

### M14.1 — Reliability / Idempotency Contract
- retry contract
- idempotency key
- failure classification
- safe retry boundaries

### M14.2 — Retry / Backoff / Circuit Safety
- bounded retry
- backoff
- provider failure handling
- circuit breaker

### M14.3 — Run Recovery
- stuck run detection
- resumable stages
- dead-letter/permanent failures
- restart safety

### M14.4 — Observability
- structured events
- run/stage/provider metrics
- failure metrics
- optimization metrics

### M14.5 — Cost / Quota Controls
- budgets
- quota tracking
- estimated/actual cost
- graceful degradation

### M14.6 — Provider Health
- health model
- cooldown
- failure rate
- latency
- quota signals

### M14.7 — Scale / Queue / Concurrency
- bounded queue
- concurrency limits
- duplicate prevention
- batch safety

### M14.8 — Security Hardening
- secret redaction
- webhook/OAuth validation
- credential handling

### M14.9 — QC / Production Quality Gate
- stronger deterministic QC
- artifact validation
- retry/permanent failure classification

### M14.10 — Full Failure Regression
Cross-layer failure scenarios.

### M14.11 — M14 Exit Audit
Final production-hardening audit.

Bu sıra audit sonucuna göre değiştirilebilir.

---

# 12. M14'TE KORUNMASI GEREKEN KRİTİK SINIRLAR

M14 hiçbir koşulda:

- M13 OptimizationPolicy gate'i bypass etmemeli
- aktif optimization decision'ı sessizce overwrite etmemeli
- rollback kabiliyetini kaldırmamalı
- M10 ProductionDecision safety'sini bypass etmemeli
- M11 TopicSelectionDecision safety'sini bypass etmemeli
- experiment winner'ını doğrudan production policy yapmamalı
- provider-specific optimization coupling eklememeli
- human approval'ı kaldırmamalı
- uncontrolled autonomous publishing eklememeli
- CI/unit/integration testlerinde ücretli API tüketmemeli

Özellikle:

```
Learning
  ≠
Direct Provider Mutation
```

ve

```
OptimizationDecision
  ≠
Uncontrolled Autonomous Publishing
```

invariant'ları korunmalıdır.

---

# 13. CI / MERGE PROTOKOLÜ

Her M14 PR için:

1. inspect
2. explain
3. smallest safe change
4. implement
5. tests
6. git diff review
7. CI
8. CI green
9. squash merge
10. merge SHA kaydı
11. milestone status güncellemesi

CI green olmadan merge edilmez.

Failure önce sınıflandırılmalı:

- application logic
- assertion
- Ruff
- mypy
- migration
- Docker
- environment

Testlerde:

- fake/mock provider
- no paid API
- no real video generation
- deterministic fixtures

kullanılmalı.

---

# 14. M14'ÜN "DONE" KRİTERİ

M14 tamamlanmış sayılmamalıdır yalnızca yeni feature'lar eklenmişse.

M14 DONE için:

- reliability controlled
- retry bounded
- failures classified
- idempotency proven
- recovery proven
- provider health observable
- cost/quota bounded
- structured observability available
- concurrency bounded
- security hardening verified
- QC production-safe
- human approval preserved
- no uncontrolled autonomous publishing
- migrations green
- unit tests green
- integration tests green
- static checks green
- Docker build green
- failure regression green
- exit audit PASS

olmalıdır.

---

# 15. YENİ SOHBETTE İLK KULLANILACAK TALİMAT

Yeni sohbete bu dosya eklendiğinde şu çerçeveyle çalış:

> Bu dosya YouTube Shorts Bot V2 için M13 → M14 geçiş dosyasıdır.  
> M13 tamamlanmış ve CI doğrulaması yapılmıştır.  
> Önce repository'deki mevcut main durumunu ve M14 entry guardrails'ı doğrula.  
> M14.0 Production Hardening Audit yapmadan kod değiştirme.  
> Audit sonucunda mevcut mimariyi, riskleri, eksikleri, dosya bazlı planı ve küçük PR sırasını çıkar.  
> M14.0 tamamlandıktan sonra yalnızca en küçük güvenli değişikliklerle ilerle.  
> Her PR'da test → diff → CI → green → squash merge protokolünü uygula.  
> M10, M11, M12 ve M13 güvenlik sınırlarını hiçbir aşamada bypass etme.  
> Gerçek ücretli API'leri test/CI sırasında kullanma.  
> Her milestone sonunda audit dokümanı oluştur ve sonraki milestone'a açık bir handoff bırak.

---

# 16. M14 İÇİN REFERANS DOSYALAR

Ana plan:

`YouTube Shorts Bot V2 — Master Plan ve Sistem Mimarisi.md`

M12 exit:

`docs/M12_EXIT_AUDIT.md`

M13 audit:

`docs/M13_OPTIMIZATION_POLICY_AUDIT.md`

M13 exit:

`docs/M13_EXIT_AUDIT.md`

Özellikle M13 exit audit okunmadan M14 implementation'a başlanmamalıdır.

---

# 17. SON DURUM

```
M0  — baseline / foundation
M1  — domain / DB foundation
M2  — reliability foundation
M3  — provider / routing foundation
M4  — production pipeline foundation
M5  — final pilot
M6  — content + visual quality
M7  — performance / production foundations
M8  — performance memory
M9  — learning / recommendation
M10 — production decision
M11 — topic optimization
M12 — controlled experimentation
M13 — controlled automated optimization
M14 — NEXT
```

M13 kapanmıştır.

**Bir sonraki resmi iş: M14.0 — Production Hardening Audit.**

M14'te hedef artık "daha akıllı" olmak değil; mevcut akıllı sistemi **daha güvenilir, gözlemlenebilir, maliyet kontrollü, kurtarılabilir ve ölçeklenebilir** hale getirmektir.
