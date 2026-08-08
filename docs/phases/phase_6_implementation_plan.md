# 📋 خطة تنفيذ Phase 6 الاحترافية - التقييم والاختبار الخصمي
**Zyren AI Dev-Team — Multi-Agent SDLC Engine**

> **المرجع:** بناءً على تحليل شامل لـ README.md + جميع خطط Phases 0-5 + الكود الكامل للمشروع (331 ملف، 296/331 اختبار ناجح = 89%)
> **التاريخ:** 2026-07-10 | **الحالة:** Phase 5 مكتمل ✅ | Phase 6 جاري 🟨

---

## 🎯 **الهدف الاستراتيجي لـ Phase 6**

إنشاء منظومة تقييم شاملة ومحايدة تقيس أداء النظام كـ **"نظام كامل"** وليس كوكلاء منفصلين، مع حمايته من الانجراف (drift) والهجمات الخصمية.

**North Star Metric:** SWE-bench Verified % Resolved + Golden Tasks % Resolved

---

## 📊 **تحليل الفجوة (Gap Analysis) - ما موجود vs ما مطلوب**

| متطلب Phase 6 (من README) | الحالة الحالية | ما ينقص للتنفيذ الكامل |
|---------------------------|---------------|-------------------------|
| **Golden Dataset & Calibrated LLM-as-Judge** (κ > 0.6) | ✅ `evals/judges/judge.py` موجود مع prompts متعددة | معايرة القاضي بـ 30-50 مهمة ذهبية + Cohen's κ ≥ 0.6 |
| **Trajectory-First Evaluation** (SWE-bench Verified/Lite) | ⚠️ `evals/swebench/` + `evals/harness.py` هيكل فقط | ربط SWE-bench Lite حقيقي + Golden tasks runner فعال |
| **Router Evals & Anti-Drift Guardrail** | ⚠️ Router موجود (`semantic_router.py`) مع 4 aliases ثابتة، **بدون تقييم دوري** | Shadow evaluation + Immutable Performance Floor + Auto-rollback للـ thresholds |
| **Adversarial Red-Teaming** (PyRIT, garak, OWASP Top 10) | ⚠️ `evals/redteam/attacks.py` بسيط جداً | دمج PyRIT/garak + حملات OWASP 2026 شاملة |

> **ملاحظة هامة:** المعمارية الحالية في Phase 3&4 تستخدم **نماذج aliases ثابتة** (`frontier`, `fast`, `critic`, `fallback`) مع توجيه ذكي (`route_by_complexity` + `SemanticRouter`). هذا **بتصميم متعمد** وليس فجوة. Phase 6 تقيم وتحمي هذا النظام، لا تغيره.

---

## 🏗️ **معمارية Phase 6 المقترحة**

```
┌─────────────────────────────────────────────────────────────────┐
│                    PHASE 6 EVALUATION LAYER                     │
├─────────────────────────────────────────────────────────────────┤
│  ┌──────────────────┐  ┌──────────────────┐  ┌────────────────┐  │
│  │  CALIBRATED      │  │  TRAJECTORY      │  │  ROUTER        │  │
│  │  LLM-AS-JUDGE    │  │  EVALUATION      │  │  EVALS +       │  │
│  │                  │  │                  │  │  ANTI-DRIFT    │  │
│  │ • Cohen's κ >0.6 │  │ • SWE-bench Lite │  │ • Shadow mode  │  │
│  │ • Binary/3-pt    │  │ • Golden tasks   │  │ • Perf floor   │  │
│  │ • Injection-safe │  │ • Error-driven   │  │ • Auto-rollback│  │
│  └────────┬─────────┘  └────────┬─────────┘  └───────┬────────┘  │
│           │                     │                     │           │
│           └─────────────────────┼─────────────────────┘           │
│                                 ▼                                 │
│                    ┌────────────────────────┐                     │
│                    │   ADVERSARIAL          │                     │
│                    │   RED-TEAMING          │                     │
│                    │                        │                     │
│                    │ • PyRIT campaigns      │                     │
│                    │ • garak scans          │                     │
│                    │ • OWASP Top 10 Agentic │                     │
│                    └────────────────────────┘                     │
└─────────────────────────────────────────────────────────────────┘
```

---

## 📦 **المكونات الستة للتنفيذ (6 Components)**

### **Component 1: Calibrated LLM-as-Judge** 🎯
**الملفات الجديدة/المعدلة:**
| الإجراء | الملف | الوصف |
|---------|-------|-------|
| **NEW** | `evals/judges/calibration.py` | معايرة القاضي: human labels ↔ LLM judgments → Cohen's κ |
| **EXISTS** | `evals/judges/calibration_set.yaml` | 30-50 مهمة معايرة مع تسميات بشرية ذهبية (موجود) |
| **MODIFY** | `evals/judges/judge.py` | إضافة: low-precision scoring (binary/3-pt)، injection-safe prompts، randomized order |
| **EXISTS** | `evals/judges/rubrics.yaml` | Rubrics واضحة لكل فئة (موجود) |
| **EXISTS** | `tests/test_phase6_judge_calibration.py` | اختبارات المعايرة (موجود) |

**معايير النجاح:** Cohen's κ ≥ 0.6 على مجموعة المعايرة

---

### **Component 2: Trajectory-First Evaluation Harness** 🎯
**الملفات الجديدة/المعدلة:**
| الإجراء | الملف | الوصف |
|---------|-------|-------|
| **EXISTS** | `evals/harness.py` | `EvaluationHarness` يشغل المهام عبر `WorkflowRunner` كامل (موجود) |
| **MODIFY** | `evals/golden/runner.py` | تحديث: تشغيل المهام الذهبية عبر الـ harness الحقيقي |
| **MODIFY** | `evals/swebench/run_harness.py` | ربط SWE-bench Lite حقيقي (clone + install + run) |
| **EXISTS** | `evals/metrics.py` | Metrics: % Resolved، cost/workflow، latency، pass@k (موجود) |
| **EXISTS** | `tests/test_phase6_trajectory_eval.py` | اختبارات E2E (موجود) |

**المقاييس الأساسية (North Star):**
- **Primary:** SWE-bench Verified % Resolved + Golden Tasks % Resolved
- **Secondary:** Cost per task، latency، iteration count

---

### **Component 3: Router Evaluation & Anti-Drift Guardrail** 🛡️
**يقيّم ويحمي نظام التوجيه الحالي (4 aliases ثابتة + SemanticRouter)**

**الملفات الجديدة/المعدلة:**
| الإجراء | الملف | الوصف |
|---------|-------|-------|
| **NEW** | `evals/router_eval.py` | `RouterEvaluator`: shadow sample % traffic vs frontier model |
| **NEW** | `evals/performance_floor.py` | `PerformanceFloor`: Immutable anchor set (human-verified) |
| **MODIFY** | `src/orchestrator/semantic_router.py` | إضافة: `evaluation_mode` flag، metrics emission |
| **NEW** | `config/router_eval.yaml` | إعدادات: shadow_rate، floor_threshold، rollback_policy |
| **NEW** | `tests/test_phase6_router_eval.py` | اختبارات Anti-drift |

**آلية الحماية (لا تغير التوجيه، فقط تراقبه):**
```
Shadow Evaluation (5% traffic) → Compare vs Frontier Model → 
  If win-rate < floor_threshold → ALERT + AUTO-ROLLBACK routing thresholds
```

**ما لا نفعله في Phase 6 (لأنه تغيير جذري):**
- ❌ Model Discovery / Auto-discovery من NVIDIA API
- ❌ ML-based Model Selection
- ❌ Dynamic Model Capability Registry

---

### **Component 4: Adversarial Red-Teaming (Production-Grade)** 🔴
**الملفات الجديدة/المعدلة:**
| الإجراء | الملف | الوصف |
|---------|-------|-------|
| **NEW** | `evals/redteam/pyrit_runner.py` | دمج **PyRIT (Microsoft)** لحملات حقن محفز/اختراق أهداف |
| **NEW** | `evals/redteam/garak_runner.py` | دمج **garak (NVIDIA)** لمسح الثغرات |
| **NEW** | `evals/redteam/owasp_agentic.yaml` | اختبارات **OWASP Top 10 for Agentic Apps 2026** |
| **MODIFY** | `evals/redteam/attacks.py` | توسيع: multi-turn jailbreaks، tool-use privilege escalation، goal hijacking |
| **NEW** | `evals/redteam/campaigns/` | مجلد الحملات الدورية (CI/CD ready) |
| **NEW** | `tests/test_phase6_redteam.py` | اختبارات refusals حتمية |

**OWASP Top 10 Agentic 2026 Coverage:**
1. ⬜ Prompt Injection (Direct/Indirect)
2. ⬜ Tool Use Privilege Escalation  
3. ⬜ Goal Hijacking
4. ⬜ Multi-turn Jailbreaks
5. ⬜ Data Exfiltration via Tools
6. ⬜ Agent Identity Spoofing
7. ⬜ Unauthorized Tool Chaining
8. ⬜ Memory Poisoning
9. ⬜ Planning & Execution Divergence
10. ⬜ Supply Chain (MCP/Tools)

---

### **Component 5: Evaluation Orchestration & Reporting** 📊
**الملفات الجديدة:**
| الإجراء | الملف | الوصف |
|---------|-------|-------|
| **NEW** | `evals/orchestrator.py` | `EvaluationOrchestrator`: ينسق جميع التقييمات (judge + trajectory + router + redteam) |
| **NEW** | `evals/report.py` | تقرير موحد: JSON + Markdown + Dashboard data |
| **NEW** | `scripts/run_phase6_eval.py` | Entry point: `python scripts/run_phase6_eval.py --suite all` |
| **MODIFY** | `Makefile` | إضافة: `make eval-phase6`، `make eval-swebench`، `make redteam` |

---

### **Component 6: CI/CD Integration & Automation** ⚙️
**الملفات الجديدة:**
| الإجراء | الملف | الوصف |
|---------|-------|-------|
| **NEW** | `.github/workflows/phase6-eval.yml` | Weekly: Golden tasks + Router eval + Red-team |
| **NEW** | `.github/workflows/swebench.yml` | Monthly: SWE-bench Lite full run |
| **NEW** | `evals/ci_thresholds.yaml` | عتبات النجاح/الفشل للـ CI |
| **MODIFY** | `docs/phases/phase_6_implementation_plan.md` | توثيق Phase 6 محدث (هذا الملف) |

---

## 📅 **خطة التنفيذ التفصيلية (5-6 أسابيع)**

| الأسبوع | المكون | التسليمات (Deliverables) | معيار القبول |
|---------|---------|---------------------------|--------------|
| **Week 1** | **Component 1** | Calibration set + Judge calibration + κ ≥ 0.6 | ✅ Cohen's κ > 0.6 على 30 مهمة |
| **Week 2** | **Component 2** | Evaluation Harness + Golden runner + SWE-bench Lite wiring | ✅ يشغل 11 golden tasks + SWE-bench placeholder |
| **Week 3** | **Component 3** | Router shadow eval + Performance floor + Auto-rollback | ✅ يكتشف انجراف >5% في <24h، Rollback تلقائي |
| **Week 4** | **Component 4** | PyRIT + garak integration + OWASP 10 campaigns | ✅ جميع حملات OWASP تمر (blocked) |
| **Week 5** | **Component 5** | Unified orchestrator + Reports + CLI | ✅ `make eval-phase6` ينتج تقرير موحد |
| **Week 6** | **Component 6** | CI/CD workflows + Thresholds + Documentation | ✅ Weekly CI passes، تقارير في `reports/` |

---

## ⚙️ **التغييرات في التبعيات (New Dependencies)**

```toml
# pyproject.toml - Phase 6 additions
dependencies = [
    # ... existing ...
    # Evaluation & Judging
    "deepeval>=1.0",           # LLM-as-Judge framework
    "promptfoo>=0.10",         # Alternative judge/eval
    # Red-teaming
    "pyrit>=1.0",              # Microsoft PyRIT
    "garak>=0.10",             # NVIDIA garak
    # SWE-bench
    "swebench>=2.0",           # SWE-bench harness
    # Statistics
    "scipy>=1.13",             # Cohen's kappa
    "scikit-learn>=1.5",       # Agreement metrics
]
```

---

## 🔑 **القرارات التصميمية الحرجة (Key Design Decisions)**

| القرار | التبرير |
|---------|---------|
| **Trajectory-first, not agent-first** | README واضح: "Primary metric = end-to-end task success" - لا نقيس الوكلاء منفصلين إلا عند تراجع النظام |
| **Low-precision scoring (binary/3-pt)** | يقلل التباين (variance) في LLM-as-Judge، يتوافق مع ورقة "LLM-as-Judge best practices" |
| **Injection-safe prompts** | كل judge prompts تعامل كـ untrusted input - منع حقن المحفزات في التقييم نفسه |
| **Immutable Performance Floor** | مجموعة مهام ثابتة (human-verified) لا تتغير أبداً - أي تحسين للـ router يجب أن يمر عليها أولاً |
| **Shadow evaluation % traffic** | لا يؤثر على الإنتاج، يكتشف الانجراف مبكراً |
| **PyRIT + garak معاً** | PyRIT للحملات الموجهة، garak للمسح الواسع - مكملان لبعضهما |
| **حماية التوجيه الحالي، لا تغييره** | المعمارية الحالية (4 aliases + SemanticRouter) مكتملة بتصميم - Phase 6 تقيم وتحمي فقط |

---

## ✅ **Definition of Done - Phase 6**

| المعيار | الهدف |
|----------|-------|
| **Calibrated Judge** | Cohen's κ ≥ 0.6 على 30+ مهمة معايرة |
| **Golden Tasks** | 100% من المهام الذهبية الـ 11 تعمل وتنتج تقارير |
| **SWE-bench Lite** | Harness يشغل 300 مهمة (أو subset) وينتج % Resolved |
| **Router Anti-Drift** | Shadow eval يكتشف انجراف >5% في <24h، Rollback تلقائي |
| **Red-Team** | جميع حملات OWASP Top 10 2026 تمر (blocked) |
| **Unified Report** | تقرير واحد JSON + Markdown يضم كل المقاييس |
| **CI Integration** | Weekly workflow أخضر، Monthly SWE-bench workflow |
| **Documentation** | `docs/phases/phase_6_implementation_plan.md` محدث |

---

## ❓ **أسئلة مفتوحة تحتاج قرارك قبل البدء**

1. **مفاتيح API:** هل لديك مفاتيح لـ OpenAI/Anthropic/Google لتشغيل التقييمات الحقيقية؟ (يمكن البدء بـ dry-run)
2. **SWE-bench:** هل نبدأ بـ **Lite (300)** أم **Verified (500)**؟ Lite أسرع للـ CI.
3. **PyRIT/garak:** هل تفضل تثبيتهما كـ dependencies أم تشغيلهما عبر Docker containers منفصلة؟
4. **CI/CD:** هل نستخدم GitHub Actions أم GitLab CI؟ (المشروع الحالي يبدو GitHub)
5. **Budget:** ما الميزانية الأسبوعية المستهدفة لتكاليف LLM في التقييم؟ (لضبط `session_budget_usd`)

---

## 🚀 **الخطوة التالية المقترحة**

> **Week 1 Kick-off:** ابدأ بـ **Component 1** (Calibrated LLM-as-Judge) لأن:
> 1. هو الأساس الذي سيستخدمه باقي المكونات
> 2. `evals/judges/judge.py` موجود وجاهز للتوسيع
> 3. `evals/judges/calibration_set.yaml` و `rubrics.yaml` موجودين بالفعل
> 4. اختبار