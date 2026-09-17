from __future__ import annotations

import unittest
import json
from pathlib import Path
import tempfile

from tuition_location_analytics.competitors.diagnostics import channel_overlap_diagnostics
from tuition_location_analytics.competitors.gates import (
    evaluate_exact_observation_provenance_partition,
    evaluate_pilot_acceptance_gates,
    evaluate_retained_relational_integrity,
)
from tuition_location_analytics.competitors.query_integrity import expected_query_records, validate_query_integrity
from tuition_location_analytics.competitors.reporting import coverage_markdown
from tuition_location_analytics.foundation.common import scan_foundation_outputs_for_secrets


class DiagnosticsTests(unittest.TestCase):
    def test_no_population_estimator_key_is_produced(self) -> None:
        result = channel_overlap_diagnostics({"a", "b", "c"}, {"b", "c", "d"}, label_a="s010", label_b="web")
        self.assertNotIn("lincoln_petersen_estimate", result)
        self.assertNotIn("capture_recapture", result)

    def test_jaccard_overlap_computed_correctly(self) -> None:
        result = channel_overlap_diagnostics({"a", "b", "c"}, {"b", "c", "d"}, label_a="s010", label_b="web")
        self.assertAlmostEqual(result["jaccard_overlap"], 2 / 4)
        self.assertEqual(result["overlap_count"], 2)
        self.assertEqual(result["unique_to_s010"], 1)
        self.assertEqual(result["unique_to_web"], 1)

    def test_empty_channels_do_not_divide_by_zero(self) -> None:
        result = channel_overlap_diagnostics(set(), set(), label_a="s010", label_b="web")
        self.assertEqual(result["jaccard_overlap"], 0.0)

    def test_overlap_uses_resolved_branch_ids_not_addresses(self) -> None:
        # Two observations with different raw text can resolve to one branch ID;
        # overlap therefore happens after canonical branch resolution.
        result = channel_overlap_diagnostics({"BRANCH_1"}, {"BRANCH_1"}, label_a="S010", label_b="WEB_SEARCH")
        self.assertEqual(result["overlap_count"], 1)
        self.assertEqual(result["union_count"], 1)


class GatesTests(unittest.TestCase):
    def _base_kwargs(self, **overrides):
        kwargs = dict(
            total_queries=40,
            logged_queries=40,
            query_integrity={"valid": True, "errors": []},
            unique_candidate_count=10,
            attempted_candidate_count=10,
            url_fields=["https://example.com/", None],
            branch_records=[
                {
                    "evidence_status": "confirmed",
                    "status": "current",
                    "has_fresh_operator_evidence": True,
                    "counts_toward_primary_competition": True,
                    "postal_code": "123456",
                    "planning_area": "EXAMPLE",
                    "planning_area_source": "coordinate_derived",
                    "address_signature_is_exact": True,
                }
            ],
            review_queue=[],
            csv_parquet_parity_ok=True,
            checksums_ok=True,
            secret_scan_status="pass",
            geocoding_source="executed",
            selected_pilot_areas={"EXAMPLE"},
            retained_relational_integrity={
                "retained_branch_count": 1,
                "retained_brand_count": 1,
                "invalid_branch_brand_count": 0,
                "invalid_evidence_branch_count": 0,
                "invalid_offering_branch_count": 0,
                "orphan_brand_count": 0,
                "valid": True,
            },
            exact_observation_provenance_partition={
                "expected_exact_observation_count": 1,
                "represented_exactly_once_count": 1,
                "missing_count": 0,
                "duplicated_count": 0,
                "unexpected_count": 0,
                "invalid_provenance_record_count": 0,
                "valid": True,
            },
        )
        kwargs.update(overrides)
        return kwargs

    def test_all_gates_pass_on_clean_input(self) -> None:
        result = evaluate_pilot_acceptance_gates(**self._base_kwargs())
        self.assertTrue(result["all_gates_met"])
        self.assertEqual(result["unmet_gates"], [])
        self.assertTrue(result["ready_for_national_design_approval"])

    def test_incomplete_queries_fails_that_gate_only(self) -> None:
        result = evaluate_pilot_acceptance_gates(**self._base_kwargs(logged_queries=20))
        self.assertIn("all_queries_logged", result["unmet_gates"])
        self.assertFalse(result["all_gates_met"])

    def test_query_reconciliation_failure_fails_gate(self) -> None:
        result = evaluate_pilot_acceptance_gates(
            **self._base_kwargs(query_integrity={"valid": False, "errors": ["bad count"]})
        )
        self.assertIn("query_integrity_reconciled", result["unmet_gates"])

    def test_incomplete_validation_attempts_fails_that_gate(self) -> None:
        result = evaluate_pilot_acceptance_gates(**self._base_kwargs(attempted_candidate_count=7, unique_candidate_count=10))
        self.assertIn("validation_attempts_complete", result["unmet_gates"])

    def test_invalid_url_string_fails_url_gate(self) -> None:
        result = evaluate_pilot_acceptance_gates(**self._base_kwargs(url_fields=["403 blocked", "https://ok.com/"]))
        self.assertIn("urls_valid", result["unmet_gates"])

    def test_possible_branch_counted_in_primary_competition_fails_gate(self) -> None:
        branch = {
            "evidence_status": "possible",
            "status": "unresolved",
            "has_fresh_operator_evidence": False,
            "counts_toward_primary_competition": True,
            "postal_code": "123456",
            "planning_area": "EXAMPLE",
            "planning_area_source": "coordinate_derived",
            "address_signature_is_exact": True,
        }
        result = evaluate_pilot_acceptance_gates(**self._base_kwargs(branch_records=[branch]))
        self.assertIn("primary_competition_uses_confirmed_current_only", result["unmet_gates"])

    def test_planning_area_not_coordinate_derived_fails_gate(self) -> None:
        branch = {
            "evidence_status": "possible",
            "status": "unresolved",
            "has_fresh_operator_evidence": False,
            "counts_toward_primary_competition": False,
            "postal_code": None,
            "planning_area": "TAMPINES",
            "planning_area_source": "search_query",
            "address_signature_is_exact": True,
        }
        result = evaluate_pilot_acceptance_gates(**self._base_kwargs(branch_records=[branch]))
        self.assertIn("planning_areas_coordinate_derived_or_unresolved", result["unmet_gates"])

    def test_do_not_call_ready_merely_because_software_runs(self) -> None:
        # External software verification is not a production-pipeline gate; a
        # content gate still determines readiness.
        result = evaluate_pilot_acceptance_gates(**self._base_kwargs(logged_queries=20))
        self.assertNotIn("tests_and_compilation_pass", result["gates"])
        self.assertFalse(result["ready_for_national_design_approval"])

    def test_missing_review_for_nonconfirmed_branch_fails_gate(self) -> None:
        branch = {
            "branch_id": "B1",
            "evidence_status": "possible",
            "status": "unresolved",
            "has_fresh_operator_evidence": False,
            "counts_toward_primary_competition": False,
            "postal_code": "123456",
            "planning_area": "EXAMPLE",
            "planning_area_source": "coordinate_derived",
            "address_signature_is_exact": True,
        }
        result = evaluate_pilot_acceptance_gates(**self._base_kwargs(branch_records=[branch], review_queue=[]))
        self.assertIn("review_items_enumerated", result["unmet_gates"])

    def test_possible_current_excluded_from_primary_with_review_reason_passes_separation(self) -> None:
        # Current operation can be independently proven while branch-specific
        # subject/level evidence remains incomplete; the branch legitimately
        # stays "possible" with status "current" as long as it is excluded
        # from primary competition and carries an explicit review reason.
        branch = {
            "branch_id": "B1",
            "evidence_status": "possible",
            "status": "current",
            "has_fresh_operator_evidence": False,
            "counts_toward_primary_competition": False,
            "postal_code": "123456",
            "planning_area": "EXAMPLE",
            "planning_area_source": "coordinate_derived",
            "address_signature_is_exact": True,
        }
        review_queue = [
            {
                "entity_reference": "B1",
                "issue_category": "evidence_status_possible",
                "description": "Current operation confirmed; subject/level evidence incomplete.",
            }
        ]
        result = evaluate_pilot_acceptance_gates(
            **self._base_kwargs(branch_records=[branch], review_queue=review_queue)
        )
        self.assertNotIn("possible_branches_retained_not_silently_confirmed", result["unmet_gates"])
        self.assertNotIn("primary_competition_uses_confirmed_current_only", result["unmet_gates"])
        self.assertNotIn("review_items_enumerated", result["unmet_gates"])

    def test_possible_counted_in_primary_fails_separation_gate(self) -> None:
        branch = {
            "branch_id": "B1",
            "evidence_status": "possible",
            "status": "current",
            "has_fresh_operator_evidence": False,
            "counts_toward_primary_competition": True,
            "postal_code": "123456",
            "planning_area": "EXAMPLE",
            "planning_area_source": "coordinate_derived",
            "address_signature_is_exact": True,
        }
        review_queue = [
            {"entity_reference": "B1", "issue_category": "evidence_status_possible", "description": "x"}
        ]
        result = evaluate_pilot_acceptance_gates(
            **self._base_kwargs(branch_records=[branch], review_queue=review_queue)
        )
        self.assertIn("possible_branches_retained_not_silently_confirmed", result["unmet_gates"])
        self.assertIn("primary_competition_uses_confirmed_current_only", result["unmet_gates"])

    def test_possible_missing_uncertainty_disclosure_fails_separation_gate(self) -> None:
        # Not counted toward primary, but no explicit review/uncertainty item
        # exists for this branch -- retained silently rather than disclosed.
        branch = {
            "branch_id": "B1",
            "evidence_status": "possible",
            "status": "current",
            "has_fresh_operator_evidence": False,
            "counts_toward_primary_competition": False,
            "postal_code": "123456",
            "planning_area": "EXAMPLE",
            "planning_area_source": "coordinate_derived",
            "address_signature_is_exact": True,
        }
        result = evaluate_pilot_acceptance_gates(**self._base_kwargs(branch_records=[branch], review_queue=[]))
        self.assertIn("possible_branches_retained_not_silently_confirmed", result["unmet_gates"])

    def test_geocoding_globally_blocked_fails_readiness_gate(self) -> None:
        result = evaluate_pilot_acceptance_gates(**self._base_kwargs(geocoding_source="blocked"))
        self.assertIn("geocoding_executed_or_validated_cache", result["unmet_gates"])
        self.assertFalse(result["all_gates_met"])

    def test_geocoding_executed_passes_readiness_gate(self) -> None:
        result = evaluate_pilot_acceptance_gates(**self._base_kwargs(geocoding_source="executed"))
        self.assertNotIn("geocoding_executed_or_validated_cache", result["unmet_gates"])

    def test_geocoding_validated_cache_passes_readiness_gate(self) -> None:
        result = evaluate_pilot_acceptance_gates(**self._base_kwargs(geocoding_source="cache"))
        self.assertNotIn("geocoding_executed_or_validated_cache", result["unmet_gates"])

    def test_only_executed_or_fixture_validated_cache_sources_pass_geocoding_readiness(self) -> None:
        for source in ("blocked", "unknown", None, ""):
            with self.subTest(source=source):
                result = evaluate_pilot_acceptance_gates(**self._base_kwargs(geocoding_source=source))
                self.assertIn("geocoding_executed_or_validated_cache", result["unmet_gates"])
                self.assertFalse(result["details"]["geocoding_readiness_source_accepted"])

    def test_resolved_retained_branch_outside_selected_geography_fails_explicit_gate(self) -> None:
        branch = dict(self._base_kwargs()["branch_records"][0], planning_area="OUTSIDE")
        result = evaluate_pilot_acceptance_gates(
            **self._base_kwargs(branch_records=[branch])
        )
        self.assertIn("resolved_retained_branches_within_pilot_geography", result["unmet_gates"])
        self.assertEqual(result["details"]["resolved_retained_outside_pilot_geography_count"], 1)

    def test_unresolved_retained_branch_does_not_invent_planning_area(self) -> None:
        branch = dict(
            self._base_kwargs()["branch_records"][0],
            planning_area=None,
            planning_area_source="unresolved_no_coordinate",
        )
        result = evaluate_pilot_acceptance_gates(**self._base_kwargs(branch_records=[branch]))
        self.assertNotIn("resolved_retained_branches_within_pilot_geography", result["unmet_gates"])


class RetainedRelationalIntegrityTests(unittest.TestCase):
    def _clean(self) -> dict:
        return evaluate_retained_relational_integrity(
            branch_records=[{"branch_id": "B1", "brand_id": "BR1"}],
            brand_records=[{"brand_id": "BR1"}],
            evidence_records=[{"branch_id": "B1"}],
            offering_records=[{"branch_id": "B1"}],
        )

    def test_clean_retained_relational_state_passes(self) -> None:
        self.assertTrue(self._clean()["valid"])

    def test_orphan_brand_fails(self) -> None:
        result = evaluate_retained_relational_integrity(
            branch_records=[{"branch_id": "B1", "brand_id": "BR1"}],
            brand_records=[{"brand_id": "BR1"}, {"brand_id": "ORPHAN"}],
            evidence_records=[], offering_records=[],
        )
        self.assertFalse(result["valid"])
        self.assertEqual(result["orphan_brand_count"], 1)

    def test_broken_branch_evidence_and_offering_foreign_keys_fail(self) -> None:
        result = evaluate_retained_relational_integrity(
            branch_records=[{"branch_id": "B1", "brand_id": "MISSING_BRAND"}],
            brand_records=[],
            evidence_records=[{"branch_id": "MISSING_EVIDENCE_BRANCH"}],
            offering_records=[{"branch_id": "MISSING_OFFERING_BRANCH"}],
        )
        self.assertFalse(result["valid"])
        self.assertEqual(result["invalid_branch_brand_count"], 1)
        self.assertEqual(result["invalid_evidence_branch_count"], 1)
        self.assertEqual(result["invalid_offering_branch_count"], 1)

    def test_relational_failure_fails_explicit_gate(self) -> None:
        integrity = self._clean() | {"valid": False, "orphan_brand_count": 1}
        result = evaluate_pilot_acceptance_gates(
            **GatesTests()._base_kwargs(retained_relational_integrity=integrity)
        )
        self.assertIn("retained_relational_integrity", result["unmet_gates"])


class ExactObservationProvenancePartitionTests(unittest.TestCase):
    def _record(self, *ids: str) -> dict:
        return {"source_candidate_ids_json": json.dumps(sorted(ids))}

    def test_retained_and_excluded_partition_passes_and_excludes_vague_leads(self) -> None:
        result = evaluate_exact_observation_provenance_partition(
            expected_observation_ids={"OBS1", "OBS2", "OBS3"},
            retained_branches=[self._record("OBS1")],
            excluded_branches=[self._record("OBS2", "OBS3")],
        )
        self.assertTrue(result["valid"])
        self.assertEqual(result["expected_exact_observation_count"], 3)
        self.assertEqual(result["represented_exactly_once_count"], 3)

    def test_missing_observation_fails(self) -> None:
        result = evaluate_exact_observation_provenance_partition(
            expected_observation_ids={"OBS1", "OBS2"}, retained_branches=[self._record("OBS1")], excluded_branches=[]
        )
        self.assertFalse(result["valid"])
        self.assertEqual(result["missing_count"], 1)

    def test_observation_in_retained_and_excluded_outputs_fails(self) -> None:
        result = evaluate_exact_observation_provenance_partition(
            expected_observation_ids={"OBS1"},
            retained_branches=[self._record("OBS1")],
            excluded_branches=[self._record("OBS1")],
        )
        self.assertFalse(result["valid"])
        self.assertEqual(result["duplicated_count"], 1)

    def test_unexpected_observation_fails(self) -> None:
        result = evaluate_exact_observation_provenance_partition(
            expected_observation_ids={"OBS1"}, retained_branches=[self._record("OBS1", "VAGUE1")], excluded_branches=[]
        )
        self.assertFalse(result["valid"])
        self.assertEqual(result["unexpected_count"], 1)

    def test_invalid_partition_fails_the_explicit_fifteenth_gate(self) -> None:
        kwargs = GatesTests()._base_kwargs(
            exact_observation_provenance_partition={
                "expected_exact_observation_count": 2,
                "represented_exactly_once_count": 1,
                "missing_count": 1,
                "duplicated_count": 0,
                "unexpected_count": 0,
                "invalid_provenance_record_count": 0,
                "valid": False,
            }
        )
        result = evaluate_pilot_acceptance_gates(**kwargs)
        self.assertIn("exact_observation_provenance_partition_complete", result["unmet_gates"])


class QueryIntegrityTests(unittest.TestCase):
    def _protocol(self):
        root = Path(__file__).resolve().parents[1]
        areas = json.loads((root / "config/competitors/pilot_planning_areas.json").read_text())
        templates = json.loads((root / "config/competitors/discovery_templates.json").read_text())
        run = json.loads((root / "config/competitors/pilot_run.json").read_text())
        return areas, templates, run

    def test_exact_protocol_and_ledger_counts_reconcile(self) -> None:
        areas, templates, run = self._protocol()
        queries = [dict(row, executed_at="2026-09-13", zero_result=False, distinct_candidates_surfaced=1, blocked=False) for row in expected_query_records(areas, templates, run)]
        observations = [
            {"observation_id": f"O{i}", "query_id": query["query_id"], "brand_name": f"Example {i}", "address_raw": f"{i} Road"}
            for i, query in enumerate(queries)
        ]
        result = validate_query_integrity(queries=queries, observations=observations, pilot_areas=areas, discovery_templates=templates, run_config=run)
        self.assertTrue(result["valid"])

    def test_count_mismatch_fails_reconciliation(self) -> None:
        areas, templates, run = self._protocol()
        queries = [dict(row, executed_at="2026-09-13", zero_result=False, distinct_candidates_surfaced=1, blocked=False) for row in expected_query_records(areas, templates, run)]
        queries[0]["distinct_candidates_surfaced"] = 2
        observations = [
            {"observation_id": f"O{i}", "query_id": query["query_id"], "brand_name": f"Example {i}", "address_raw": f"{i} Road"}
            for i, query in enumerate(queries)
        ]
        result = validate_query_integrity(queries=queries, observations=observations, pilot_areas=areas, discovery_templates=templates, run_config=run)
        self.assertFalse(result["valid"])
        self.assertIn(f"distinct_candidates_surfaced mismatch: {queries[0]['query_id']}", result["errors"])


class OutputBoundaryTests(unittest.TestCase):
    def test_coverage_report_distinguishes_discovery_yield_from_coordinate_location_count(self) -> None:
        report = {
            "run_id": "competitors_pilot_test",
            "analysis_cutoff": "2026-09-15",
            "raw_observation_count": 1,
            "exact_address_observation_count": 1,
            "vague_lead_count": 0,
            "unique_candidate_address_count": 1,
            "excluded_wrong_area_count": 0,
            "branch_count": 1,
            "brand_count": 1,
            "channel_diagnostics": {
                "S010_count": 0, "WEB_SEARCH_count": 1, "overlap_count": 0,
                "unique_to_S010": 0, "unique_to_WEB_SEARCH": 1,
                "jaccard_overlap": 0.0, "estimator_statement": "No estimator.",
            },
            "evidence_status_counts": {"confirmed": 1},
            "validation_attempted_count": 1,
            "validation_attempt_coverage_rate": 1.0,
            "brand_level_access_diagnostic_count": 0,
            "missing_postal_count": 0,
            "missing_postal_rate": 0.0,
            "geocode_status_counts": {"resolved_exact_postal_unique_coordinate": 1},
            "per_planning_area_discovery_yield": {"CHANGI": 1},
            "per_planning_area_location_count": {"TAMPINES": 1},
            "open_review_queue_count": 0,
            "acceptance_gates": {"all_gates_met": True, "unmet_gates": [], "ready_for_national_design_approval": True},
            "limitations": [],
            "publication_boundary": {"s010_evidence": "private_ignored", "public_release_authorized": False},
            "protocol_completion": "40/40 frozen queries logged",
        }
        rendered = coverage_markdown(report)
        self.assertIn("Discovery-query yield by searched area", rendered)
        self.assertIn("coordinate-derived planning area", rendered)
        self.assertNotIn("per_planning_area_yield", rendered)

    def test_final_reportable_output_is_in_secret_scan_scope(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            processed = root / "data/processed/competitors/pilot"
            reports = root / "data/interim/competitors/reports/pilot"
            reports.mkdir(parents=True)
            (reports / "completion-report.md").write_text("api_key=synthetic-secret-value")
            result = scan_foundation_outputs_for_secrets(
                root, processed_dir=processed, report_dir=reports, credential_values=()
            )
            self.assertEqual(result["status"], "fail")
            self.assertEqual(result["finding_paths"], ["data/interim/competitors/reports/pilot/completion-report.md"])
            self.assertNotIn("synthetic-secret-value", str(result))

    def test_pilot_s010_output_root_is_private_and_ignored(self) -> None:
        root = Path(__file__).resolve().parents[1]
        config = json.loads((root / "config/competitors/pilot_run.json").read_text())
        self.assertEqual(config["publication_boundary"]["s010_evidence"], "private_ignored")
        self.assertFalse(config["publication_boundary"]["public_release_authorized"])
        self.assertTrue(config["publication_boundary"]["reportable_output_root"].startswith("data/interim/"))


if __name__ == "__main__":
    unittest.main()
