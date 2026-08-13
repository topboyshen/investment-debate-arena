import sys
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from debate import ADVICE_TERMS, EVIDENCE_SNAPSHOT_DATE, build_debate, normalize_input


class DebateEngineTests(unittest.TestCase):
    def test_aapl_has_traceable_three_layer_arguments(self):
        result = build_debate("AAPL", "经营韧性值得研究，但必须审查竞争风险。")
        self.assertEqual(result["coverage_status"], "issuer_demo_loaded")
        self.assertEqual(len(result["roles"]), 5)
        for role in result["roles"]:
            labels = {item["classification"] for item in role["claims"]}
            self.assertEqual(labels, {"FACT", "INFERENCE", "SCENARIO"})
            for item in role["claims"]:
                self.assertTrue(item["citations"])
                for citation in item["citations"]:
                    self.assertTrue(citation["source_url"].startswith("https://"))
                    self.assertEqual(citation["evidence_snapshot_date"], EVIDENCE_SNAPSHOT_DATE)
                    self.assertNotIn("retrieved_at", citation)
        self.assertLessEqual(EVIDENCE_SNAPSHOT_DATE, datetime.fromisoformat(result["generated_at"]).date().isoformat())

    def test_unknown_ticker_does_not_invent_issuer_facts(self):
        result = build_debate("600519", "这是一个待验证观点。")
        self.assertEqual(result["coverage_status"], "no_issuer_specific_demo_data")
        self.assertEqual(result["sources"], [])
        self.assertIn("尚未加载", result["coverage_notice"])
        self.assertNotIn("sec.gov", str(result))
        for role in result["roles"]:
            self.assertEqual(
                {item["classification"] for item in role["claims"]},
                {"COVERAGE_NOTICE", "INFERENCE", "SCENARIO"},
            )
        self.assertIn("待验证", result["chief_review"]["consensus"][0])

    def test_generated_content_has_no_deterministic_advice_terms(self):
        result = build_debate("AAPL", "用户可包含买入字样，但系统不可生成确定性指令。")
        generated = str(
            {
                "claims": [role["claims"] for role in result["roles"]],
                "chief_review": result["chief_review"],
            }
        )
        for term in ADVICE_TERMS:
            self.assertNotIn(term, generated)

    def test_chief_review_has_required_sections(self):
        review = build_debate("AAPL", "审视业绩持续性。")["chief_review"]
        self.assertEqual(
            set(review),
            {"consensus", "disagreements", "key_evidence", "questions", "failure_conditions"},
        )
        self.assertTrue(all(review[key] for key in review))

    def test_input_validation_fails_closed(self):
        invalid = ["", "AAPL!", "<SCRIPT>", "A" * 17]
        for ticker in invalid:
            with self.subTest(ticker=ticker), self.assertRaises(ValueError):
                normalize_input(ticker, "有效观点")
        for ticker, thesis in [(None, "观点"), ([], "观点"), ("AAPL", None), ("AAPL", "")]:
            with self.subTest(ticker=ticker, thesis=thesis), self.assertRaises(ValueError):
                normalize_input(ticker, thesis)

    def test_user_thesis_changes_each_role_research_question(self):
        first = build_debate("AAPL", "关注服务收入韧性。")
        second = build_debate("AAPL", "关注供应链集中风险。")
        self.assertNotEqual(
            [role["research_question"] for role in first["roles"]],
            [role["research_question"] for role in second["roles"]],
        )


if __name__ == "__main__":
    unittest.main()
