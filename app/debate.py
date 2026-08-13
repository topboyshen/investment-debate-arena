from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Any

# This is a curated demo snapshot date in Asia/Shanghai, not a claim that the
# sources were fetched at a precise instant.
EVIDENCE_SNAPSHOT_DATE = "2026-08-13"
TICKER_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9.^-]{0,15}$")
ADVICE_TERMS = ("买入", "卖出", "增持", "减持", "目标价", "确定性推荐")

AAPL_SOURCES = [
    {
        "id": "aapl-q1-2026",
        "source_name": "Apple Newsroom — FY2026 Q1 results",
        "source_url": "https://www.apple.com/newsroom/2026/01/apple-reports-first-quarter-results/",
        "published_at": "2026-01-29T00:00:00Z",
        "evidence_snapshot_date": EVIDENCE_SNAPSHOT_DATE,
        "facts": [
            "Apple 披露 FY2026 Q1 营收为 1,438 亿美元，同比增加 16%。",
            "Apple 披露 FY2026 Q1 稀释后每股收益为 2.84 美元，同比增加 19%。",
            "Apple 表示 iPhone 和服务业务在该季度均创历史新高。",
            "Apple 披露该季度经营现金流接近 540 亿美元，并向股东返还接近 320 亿美元。",
        ],
    },
    {
        "id": "aapl-10k-2025",
        "source_name": "U.S. SEC — Apple 2025 Form 10-K",
        "source_url": "https://www.sec.gov/Archives/edgar/data/320193/000032019325000079/aapl-20250927.htm",
        "published_at": "2025-10-31T00:00:00Z",
        "evidence_snapshot_date": EVIDENCE_SNAPSHOT_DATE,
        "facts": [
            "Apple 的 FY2025 年度报告说明，其产品和服务市场竞争激烈，并存在价格竞争和毛利率压力。",
            "Apple 的 FY2025 年度报告说明，部分关键组件由单一或有限来源供应，供给约束可能影响可得性和成本。",
            "Apple 的 FY2025 年度报告说明，服务、硬件产品和地域市场均受到技术演进、产品周期与宏观环境影响。",
        ],
    },
]


def source_by_id(source_id: str) -> dict[str, Any]:
    for source in AAPL_SOURCES:
        if source["id"] == source_id:
            return source
    raise KeyError(source_id)


def citation(source_id: str) -> dict[str, str]:
    source = source_by_id(source_id)
    return {
        "source_id": source_id,
        "source_name": source["source_name"],
        "source_url": source["source_url"],
        "published_at": source["published_at"],
        "evidence_snapshot_date": source["evidence_snapshot_date"],
    }


def claim(kind: str, text: str, source_ids: list[str], confidence: str) -> dict[str, Any]:
    return {
        "classification": kind,
        "claim": text,
        "confidence": confidence,
        "citations": [citation(source_id) for source_id in source_ids],
    }


def coverage_note(ticker: str) -> tuple[list[dict[str, Any]], list[str]]:
    ticker = ticker.upper().strip()
    if ticker == "AAPL":
        return AAPL_SOURCES, ["aapl-q1-2026", "aapl-10k-2025"]
    return [], []


def local_claim(kind: str, text: str, confidence: str) -> dict[str, Any]:
    return {
        "classification": kind,
        "claim": text,
        "confidence": confidence,
        "citations": [],
        "basis": "internal_coverage_state" if kind == "COVERAGE_NOTICE" else "evidence_gap",
    }


def build_roles(ticker: str, thesis: str, source_ids: list[str], sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    is_aapl = ticker == "AAPL"
    if not is_aapl:
        coverage_text = f"原型资料库尚未加载 {ticker} 的发行人特定披露；系统不会把用户观点改写为公司事实。"
        return [
            {
                "role": "多头研究员",
                "focus": "寻找需要由后续披露验证的正向驱动",
                "research_question": f"针对用户命题“{thesis}”，寻找可验证的正向驱动。",
                "claims": [
                    local_claim("COVERAGE_NOTICE", coverage_text, "high"),
                    local_claim("INFERENCE", "用户提交的观点可以作为待证假设，但目前缺少发行人特定证据。", "low"),
                    local_claim("SCENARIO", "若补充的监管披露支持收入、利润率或现金流改善，正向论点才具备进一步讨论基础。", "low"),
                ],
            },
            {
                "role": "空头研究员",
                "focus": "识别研究证据空白和反例",
                "research_question": f"针对用户命题“{thesis}”，寻找能够证伪它的披露和反例。",
                "claims": [
                    local_claim("COVERAGE_NOTICE", coverage_text, "high"),
                    local_claim("INFERENCE", "在缺少可追溯披露前，任何方向性结论都容易把叙事当作事实。", "high"),
                    local_claim("SCENARIO", "若后续披露显示经营指标恶化，原始观点需要重新界定或放弃。", "low"),
                ],
            },
            {
                "role": "财务分析师",
                "focus": "建立可审计的财务验证清单",
                "research_question": f"针对用户命题“{thesis}”，确定需要核对的财务报表与口径。",
                "claims": [
                    local_claim("COVERAGE_NOTICE", coverage_text, "high"),
                    local_claim("INFERENCE", "应先取得最近两期财务报表、现金流量表与管理层讨论，再评价观点的财务基础。", "high"),
                    local_claim("SCENARIO", "若收入增长、现金转换和资本开支趋势相互矛盾，财务叙事不能成立。", "medium"),
                ],
            },
            {
                "role": "产业研究员",
                "focus": "识别行业结构尚缺的输入",
                "research_question": f"针对用户命题“{thesis}”，识别必须补充的行业与竞争资料。",
                "claims": [
                    local_claim("COVERAGE_NOTICE", coverage_text, "high"),
                    local_claim("INFERENCE", "未取得行业份额、供需与竞争者资料前，产业优势或劣势均不应视为已证实。", "high"),
                    local_claim("SCENARIO", "若行业需求、价格或竞争格局与原观点相反，推演路径会失效。", "medium"),
                ],
            },
            {
                "role": "事实核查员",
                "focus": "核对事实覆盖范围与引用完整性",
                "research_question": f"针对用户命题“{thesis}”，区分用户输入、外部事实和待验证推断。",
                "claims": [
                    local_claim("COVERAGE_NOTICE", coverage_text, "high"),
                    local_claim("INFERENCE", "用户输入被保留为研究假设，而不是引用支持的事实。", "high"),
                    local_claim("SCENARIO", "补充监管文件、公司业绩材料与独立行业资料后，才可进行来源交叉核验。", "medium"),
                ],
            },
        ]

    return [
        {
            "role": "多头研究员",
            "focus": "寻找已披露经营强度与观点之间的可检验联系",
            "claims": [
                claim("FACT", "Apple 披露 FY2026 Q1 营收同比增加 16%，并称 iPhone 与服务业务均创历史新高。", ["aapl-q1-2026"], "high"),
                claim("INFERENCE", "用户提交的观点可与近期收入、盈利和服务业务强度形成待验证的正向假设，但单一季度不能证明趋势持续。", ["aapl-q1-2026"], "medium"),
                claim("SCENARIO", "若后续披露继续显示服务收入韧性、现金流稳定和主要产品需求延续，正向研究情景获得更多支持。", ["aapl-q1-2026"], "low"),
            ],
        },
        {
            "role": "空头研究员",
            "focus": "检验竞争、供给和周期风险是否足以反驳观点",
            "claims": [
                claim("FACT", "Apple 在 FY2025 年度报告中披露，市场竞争激烈，存在价格竞争与毛利率压力；部分关键组件来自单一或有限来源。", ["aapl-10k-2025"], "high"),
                claim("INFERENCE", "近期强劲业绩不能消除竞争、产品周期和供应约束带来的潜在波动，因此不应将单季表现外推为确定趋势。", ["aapl-q1-2026", "aapl-10k-2025"], "medium"),
                claim("SCENARIO", "若需求正常化、竞争加剧或关键组件约束推高成本，原有正向叙事可能承压。", ["aapl-10k-2025"], "low"),
            ],
        },
        {
            "role": "财务分析师",
            "focus": "区分已披露数据与财务解释",
            "claims": [
                claim("FACT", "Apple 披露 FY2026 Q1 稀释后每股收益为 2.84 美元，同比增加 19%，经营现金流接近 540 亿美元。", ["aapl-q1-2026"], "high"),
                claim("INFERENCE", "收入、每股收益和经营现金流同时增长与盈利质量改善相一致，但需要后续期间和具体口径进一步验证。", ["aapl-q1-2026"], "medium"),
                claim("SCENARIO", "若后续利润率、营运资本或现金转换恶化，即使收入保持增长，财务论证也会减弱。", ["aapl-q1-2026"], "low"),
            ],
        },
        {
            "role": "产业研究员",
            "focus": "将公司披露映射到行业变量",
            "claims": [
                claim("FACT", "Apple 的年度报告将技术变化、产品周期、价格竞争、供应链和宏观环境列为影响业务结果的重要因素。", ["aapl-10k-2025"], "high"),
                claim("INFERENCE", "服务业务纪录与活跃设备基础可能增强生态韧性，但行业竞争和产品迭代仍决定持续性。", ["aapl-q1-2026", "aapl-10k-2025"], "medium"),
                claim("SCENARIO", "若竞争对手以更低成本或更快迭代改变用户选择，或供应链发生扰动，产业侧假设需要下调。", ["aapl-10k-2025"], "low"),
            ],
        },
        {
            "role": "事实核查员",
            "focus": "核验来源、时间和事实层级",
            "claims": [
                claim("FACT", "本次演示的公司特定事实分别来自 Apple FY2026 Q1 业绩发布和 Apple FY2025 Form 10-K。", ["aapl-q1-2026", "aapl-10k-2025"], "high"),
                claim("INFERENCE", "用户观点以及各角色对持续性的解释均为推断，不能被表述为公司已披露事实。", ["aapl-q1-2026", "aapl-10k-2025"], "high"),
                claim("SCENARIO", "后续季度业绩、现金流、竞争与供应链证据将决定现有叙事是否继续成立。", ["aapl-q1-2026", "aapl-10k-2025"], "medium"),
            ],
        },
    ]


def build_chief_review(ticker: str, thesis: str, sources: list[dict[str, Any]]) -> dict[str, list[str]]:
    if ticker == "AAPL":
        return {
            "consensus": [
                "近期披露显示强劲的单季收入、每股收益和经营现金流，且服务业务表现突出。",
                "用户观点应被理解为待验证的研究假设，而非已证实结论。",
            ],
            "disagreements": [
                "多头侧更重视近期经营动能；空头侧更重视竞争、产品周期和供应约束。",
                "财务改善的持续性仍需通过后续季度利润率、现金转换和业务结构验证。",
            ],
            "key_evidence": [
                "FY2026 Q1 营收同比增加 16%，稀释后每股收益同比增加 19%。",
                "FY2025 年度报告披露竞争、价格压力和部分关键组件供应集中风险。",
            ],
            "questions": [
                "近期收入和服务业务动能在后续季度是否延续？",
                "利润率、营运资本与经营现金流的变化是否与收入增长相匹配？",
                "竞争、产品周期与供应链约束是否改变风险收益结构？",
            ],
            "failure_conditions": [
                "后续披露显示主要业务需求、利润率或现金转换明显弱于当前论证前提。",
                "竞争或供应链压力造成成本、可得性或产品节奏显著恶化。",
                "关键事实无法由新的发行人披露或独立行业资料重复验证。",
            ],
        }
    return {
        "consensus": ["当前没有加载该代码的发行人特定演示资料；所有公司层面命题均处于待验证状态，不能形成事实共识。"],
        "disagreements": ["用户观点可能有正反两面，但缺少可追溯披露，尚不具备实质性辩论基础。"],
        "key_evidence": ["需要补充最近财务报告、管理层讨论、行业资料和可验证市场数据。"],
        "questions": ["该证券所属市场与发行主体是否已正确识别？", "最近财务期间、报告货币和行业口径是什么？"],
        "failure_conditions": ["若无法取得可追溯的一手资料，任何公司特定论证都应停止。"],
    }


def ensure_safe(result: dict[str, Any]) -> None:
    generated_content = {
        "claims": [role["claims"] for role in result["roles"]],
        "chief_review": result["chief_review"],
        "research_notice": result["research_notice"],
    }
    rendered = str(generated_content)
    for term in ADVICE_TERMS:
        if term in rendered:
            raise ValueError(f"Unsafe advice term found: {term}")
    for role in result["roles"]:
        labels = {item["classification"] for item in role["claims"]}
        expected = (
            {"FACT", "INFERENCE", "SCENARIO"}
            if result["coverage_status"] == "issuer_demo_loaded"
            else {"COVERAGE_NOTICE", "INFERENCE", "SCENARIO"}
        )
        if labels != expected:
            raise ValueError(f"Role {role['role']} is missing a required classification")
        for item in role["claims"]:
            if item["classification"] == "FACT" and not item["citations"]:
                raise ValueError("Every factual claim must retain a citation record")
            if item["classification"] == "COVERAGE_NOTICE" and item.get("basis") != "internal_coverage_state":
                raise ValueError("Coverage notices must identify their internal basis")


def normalize_input(ticker: str, thesis: str) -> tuple[str, str]:
    if type(ticker) is not str or type(thesis) is not str:
        raise ValueError("ticker and thesis must be strings")
    normalized_ticker = ticker.upper().strip()
    normalized_thesis = thesis.strip()
    if not TICKER_PATTERN.fullmatch(normalized_ticker):
        raise ValueError("ticker must be 1-16 characters using A-Z, 0-9, dot, caret or hyphen")
    if not normalized_thesis:
        raise ValueError("thesis must not be empty")
    if len(normalized_thesis) > 600:
        raise ValueError("thesis must be at most 600 characters")
    return normalized_ticker, normalized_thesis


def build_debate(ticker: str, thesis: str) -> dict[str, Any]:
    normalized_ticker, normalized_thesis = normalize_input(ticker, thesis)
    sources, source_ids = coverage_note(normalized_ticker)
    roles = build_roles(normalized_ticker, normalized_thesis, source_ids, sources)
    for role in roles:
        role.setdefault(
            "research_question",
            f"针对用户命题“{normalized_thesis}”，{role['focus']}。",
        )
    result = {
        "ticker": normalized_ticker,
        "user_thesis": normalized_thesis,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "prototype_mode": True,
        "research_notice": "研究过程结构化演示：不构成个性化财务建议，不提供确定性交易指令。",
        "coverage_status": "issuer_demo_loaded" if normalized_ticker == "AAPL" else "no_issuer_specific_demo_data",
        "coverage_notice": (
            None
            if normalized_ticker == "AAPL"
            else f"原型资料库尚未加载 {normalized_ticker} 的发行人特定披露；以下内容是研究清单，不是公司事实。"
        ),
        "sources": sources,
        "roles": roles,
        "chief_review": build_chief_review(normalized_ticker, normalized_thesis, sources),
    }
    ensure_safe(result)
    return result
