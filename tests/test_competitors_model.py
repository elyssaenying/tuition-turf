from __future__ import annotations

import unittest
from pathlib import Path
import json
import tempfile
from unittest.mock import patch

import pyarrow.parquet as pq

from tuition_location_analytics.competitors.dedup import deduplicate_branch_candidates
from tuition_location_analytics.competitors.cli import (
    _blocked_geocoding_result,
    _apply_coordinate_geography_policy,
    _config_paths,
    _excluded_wrong_area_record,
    _load_validation_index,
    _lookup_validation_for_branch,
    _prepare_run_output_directories,
    _retained_branch_records_only,
    _validations_for_branch,
    compute_run_id,
)
from tuition_location_analytics.competitors.geocode import OneMapUnavailable
from tuition_location_analytics.competitors.evidence import evaluate_branch_evidence
from tuition_location_analytics.competitors.identity import (
    branch_id,
    evidence_id,
    normalize_address,
    normalize_brand_name,
    normalize_postal_code,
    offering_id,
)
from tuition_location_analytics.competitors.status import (
    count_current_branches,
    count_distinct_brands,
    record_relocation,
)
from tuition_location_analytics.foundation.common import write_csv, write_parquet


class IdentityAndNormalizationTests(unittest.TestCase):
    def test_normalize_brand_name_is_case_and_whitespace_only(self) -> None:
        self.assertEqual(normalize_brand_name("  Example   Math  Centre "), "EXAMPLE MATH CENTRE")

    def test_normalize_address_standardises_unit_spacing_without_merging_different_units(self) -> None:
        self.assertEqual(normalize_address("123 Example Rd #1 - 01"), "123 EXAMPLE RD #1-01")
        self.assertNotEqual(normalize_address("123 Example Rd #01-01"), normalize_address("123 Example Rd #01-02"))

    def test_normalize_postal_code_pads_five_digit_and_rejects_invalid(self) -> None:
        self.assertEqual(normalize_postal_code("12345"), "012345")
        self.assertEqual(normalize_postal_code("123456"), "123456")
        self.assertIsNone(normalize_postal_code(None))
        self.assertIsNone(normalize_postal_code("abc"))
        self.assertIsNone(normalize_postal_code("1234"))

    def test_ids_are_deterministic_and_distinguish_distinct_entities(self) -> None:
        first = branch_id("EXAMPLE MATH", "123 EXAMPLE RD", "#01-01")
        second = branch_id("EXAMPLE MATH", "123 EXAMPLE RD", "#01-01")
        third = branch_id("EXAMPLE MATH", "123 EXAMPLE RD", "#01-02")
        self.assertEqual(first, second)
        self.assertNotEqual(first, third)

    def test_offering_and_evidence_ids_differ_by_component(self) -> None:
        branch = branch_id("EXAMPLE MATH", "123 EXAMPLE RD", "#01-01")
        primary = offering_id(branch, "mathematics", "P5")
        secondary = offering_id(branch, "mathematics", "S1")
        self.assertNotEqual(primary, secondary)
        first_evidence = evidence_id(branch, "S009", "2026-09-01", "branch_address_or_existence")
        second_evidence = evidence_id(branch, "S009", "2026-09-02", "branch_address_or_existence")
        self.assertNotEqual(first_evidence, second_evidence)


class ImmutableRunOutputDirectoryTests(unittest.TestCase):
    def test_new_run_id_creates_child_directories_without_overwriting_earlier_run(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cutoff = "2026-09-15"
            legacy_processed = root / "data/processed/competitors" / f"pilot-{cutoff}"
            legacy_reports = root / "data/interim/competitors/reports" / f"pilot-{cutoff}"
            legacy_processed.mkdir(parents=True)
            legacy_reports.mkdir(parents=True)
            (legacy_processed / "branches.csv").write_text("immutable-old-processed", encoding="utf-8")
            (legacy_reports / "data-quality-report.json").write_text("immutable-old-report", encoding="utf-8")

            processed, reports = _prepare_run_output_directories(
                root,
                reportable_output_root="data/interim/competitors/reports",
                analysis_cutoff=cutoff,
                run_id="competitors_pilot_new",
            )

            self.assertEqual(processed, legacy_processed / "competitors_pilot_new")
            self.assertEqual(reports, legacy_reports / "competitors_pilot_new")
            self.assertEqual((legacy_processed / "branches.csv").read_text(encoding="utf-8"), "immutable-old-processed")
            self.assertEqual(
                (legacy_reports / "data-quality-report.json").read_text(encoding="utf-8"),
                "immutable-old-report",
            )

    def test_existing_run_id_directory_fails_before_any_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_dir = root / "data/processed/competitors/pilot-2026-09-15/competitors_pilot_existing"
            run_dir.mkdir(parents=True)
            sentinel = run_dir / "sentinel.txt"
            sentinel.write_text("do not overwrite", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "refusing to overwrite"):
                _prepare_run_output_directories(
                    root,
                    reportable_output_root="data/interim/competitors/reports",
                    analysis_cutoff="2026-09-15",
                    run_id="competitors_pilot_existing",
                )
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "do not overwrite")


class ExcludedBranchProvenanceTests(unittest.TestCase):
    def test_excluded_branch_with_two_observations_preserves_both_and_validation_provenance(self) -> None:
        branch = {
            "branch_id": "BRANCH_EXCLUDED",
            "brand_name": "Example Mathematics",
            "address_raw": "1 Example Road",
            "source_candidate_ids": ["OBS2", "OBS1"],
        }
        validations = [
            {
                "source_observation_ids": ["OBS2", "OBS1", "OBS_NOT_THIS_BRANCH"],
                "failure_reason": "Verified outside the pilot planning area.",
            }
        ]
        record = _excluded_wrong_area_record(branch, validations)
        self.assertEqual(json.loads(record["source_candidate_ids_json"]), ["OBS1", "OBS2"])
        self.assertEqual(json.loads(record["validation_attempt_source_observation_ids_json"]), ["OBS1", "OBS2"])
        self.assertEqual(record["validation_attempt_count"], 1)
        self.assertEqual(record["reason"], "Verified outside the pilot planning area.")

    def test_excluded_provenance_csv_parquet_schema_parity_and_branch_fk(self) -> None:
        record = _excluded_wrong_area_record(
            {
                "branch_id": "BRANCH_EXCLUDED",
                "brand_name": "Example Mathematics",
                "address_raw": "1 Example Road",
                "source_candidate_ids": ["OBS1", "OBS2"],
            },
            [{"source_observation_ids": ["OBS1", "OBS2"], "failure_reason": "outside area"}],
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            csv_path = root / "excluded_wrong_area.csv"
            parquet_path = root / "excluded_wrong_area.parquet"
            write_csv(csv_path, [record])
            write_parquet(parquet_path, [record])
            csv_columns = csv_path.read_text(encoding="utf-8").splitlines()[0].split(",")
            table = pq.read_table(parquet_path)
            self.assertEqual(csv_columns, table.column_names)
            self.assertEqual(table.num_rows, 1)
            self.assertIn(table.to_pylist()[0]["branch_id"], {"BRANCH_EXCLUDED"})


class CoordinateDerivedPilotGeographyTests(unittest.TestCase):
    def _branch(self, branch_id: str = "B1", searched: str = "CHANGI") -> dict:
        return {
            "branch_id": branch_id,
            "brand_name": "Example Mathematics",
            "address_raw": "1 Example Road",
            "source_candidate_ids": ["OBS1", "OBS2"],
            "planning_area_searched": searched,
        }

    def _geocode(self, branch_id: str = "B1", *, resolved: bool = True) -> dict:
        return {
            branch_id: {
                "status": "resolved" if resolved else "no_exact_postal_coordinate",
                "longitude_wgs84": 103.8 if resolved else None,
                "latitude_wgs84": 1.3 if resolved else None,
            }
        }

    def test_resolved_outside_selected_geography_is_excluded_with_complete_provenance(self) -> None:
        validation = {"source_observation_ids": ["OBS1", "OBS2"], "failure_reason": "other"}
        with patch("tuition_location_analytics.competitors.cli.planning_area_for_coordinate", return_value="OUTSIDE"):
            retained, excluded, reviews = _apply_coordinate_geography_policy(
                branches=[self._branch()], geocode_by_branch=self._geocode(), polygons=object(),
                selected_pilot_areas={"CHANGI"}, validation_index={"OBS1": validation, "OBS2": validation},
            )
        self.assertEqual(retained, [])
        self.assertEqual(reviews, [])
        self.assertEqual(len(excluded), 1)
        self.assertEqual(excluded[0]["reason"], "coordinate_derived_outside_pilot_geography")
        self.assertEqual(json.loads(excluded[0]["source_candidate_ids_json"]), ["OBS1", "OBS2"])
        self.assertEqual(json.loads(excluded[0]["validation_attempt_source_observation_ids_json"]), ["OBS1", "OBS2"])

    def test_inside_area_mismatch_is_retained_and_flagged(self) -> None:
        with patch("tuition_location_analytics.competitors.cli.planning_area_for_coordinate", return_value="TAMPINES"):
            retained, excluded, reviews = _apply_coordinate_geography_policy(
                branches=[self._branch()], geocode_by_branch=self._geocode(), polygons=object(),
                selected_pilot_areas={"CHANGI", "TAMPINES"}, validation_index={},
            )
        self.assertEqual(len(retained), 1)
        self.assertEqual(excluded, [])
        self.assertEqual(retained[0]["planning_area"], "TAMPINES")
        self.assertEqual(reviews[0]["issue_category"], "planning_area_searched_derived_mismatch")

    def test_unresolved_coordinate_remains_retained_and_flagged_without_area_inference(self) -> None:
        with patch("tuition_location_analytics.competitors.cli.planning_area_for_coordinate", return_value=None):
            retained, excluded, reviews = _apply_coordinate_geography_policy(
                branches=[self._branch()], geocode_by_branch=self._geocode(resolved=False), polygons=object(),
                selected_pilot_areas={"CHANGI"}, validation_index={},
            )
        self.assertEqual(len(retained), 1)
        self.assertEqual(excluded, [])
        self.assertIsNone(retained[0]["planning_area"])
        self.assertEqual(reviews[0]["issue_category"], "planning_area_unresolved")

    def test_excluded_branch_is_removed_from_retained_evidence_offering_and_channel_inputs(self) -> None:
        retained_ids = {"B_RETAINED"}
        evidence = _retained_branch_records_only(
            [{"branch_id": "B_RETAINED"}, {"branch_id": "B_EXCLUDED"}], retained_ids
        )
        offerings = _retained_branch_records_only(
            [{"branch_id": "B_RETAINED"}, {"branch_id": "B_EXCLUDED"}], retained_ids
        )
        channel_diagnostic_rows = _retained_branch_records_only(
            [{"branch_id": "B_RETAINED"}, {"branch_id": "B_EXCLUDED"}], retained_ids
        )
        self.assertEqual([row["branch_id"] for row in evidence], ["B_RETAINED"])
        self.assertEqual([row["branch_id"] for row in offerings], ["B_RETAINED"])
        self.assertEqual([row["branch_id"] for row in channel_diagnostic_rows], ["B_RETAINED"])


class EvidenceStatusTests(unittest.TestCase):
    def _obs(self, obs_type: str, scope: str, observed_at: str = "2026-09-10", polarity: str = "supports") -> dict:
        return {
            "evidence_id": f"E_{obs_type}_{scope}_{observed_at}",
            "observation_type": obs_type,
            "evidence_scope": scope,
            "observed_at": observed_at,
            "polarity": polarity,
        }

    def test_confirmed_requires_all_three_fresh_operator_controlled_elements(self) -> None:
        observations = [
            self._obs("branch_address_or_existence", "operator_controlled"),
            self._obs("mathematics_subject", "operator_controlled"),
            self._obs("level_overlap", "operator_controlled"),
        ]
        result = evaluate_branch_evidence(observations, analysis_cutoff="2026-09-13")
        self.assertEqual(result["status"], "confirmed")

    def test_directory_alone_never_yields_confirmed(self) -> None:
        observations = [
            self._obs("branch_address_or_existence", "directory"),
            self._obs("mathematics_subject", "directory"),
            self._obs("level_overlap", "directory"),
        ]
        result = evaluate_branch_evidence(observations, analysis_cutoff="2026-09-13")
        self.assertEqual(result["status"], "possible")

    def test_acra_registration_alone_never_yields_confirmed(self) -> None:
        observations = [self._obs("branch_address_or_existence", "legal_entity")]
        result = evaluate_branch_evidence(observations, analysis_cutoff="2026-09-13")
        self.assertNotEqual(result["status"], "confirmed")

    def test_search_snippet_alone_is_not_a_positive_or_exclusion_signal(self) -> None:
        observations = [self._obs("branch_address_or_existence", "search_snippet")]
        result = evaluate_branch_evidence(observations, analysis_cutoff="2026-09-13")
        self.assertEqual(result["status"], "possible")

    def test_stale_operator_evidence_is_possible_not_confirmed(self) -> None:
        observations = [
            self._obs("branch_address_or_existence", "operator_controlled", observed_at="2026-01-01"),
            self._obs("mathematics_subject", "operator_controlled"),
            self._obs("level_overlap", "operator_controlled"),
        ]
        result = evaluate_branch_evidence(observations, analysis_cutoff="2026-09-13", freshness_days=30)
        self.assertEqual(result["status"], "possible")

    def test_explicit_exclusion_evidence_yields_excluded(self) -> None:
        observations = [self._obs("branch_online_only", "operator_controlled")]
        result = evaluate_branch_evidence(observations, analysis_cutoff="2026-09-13")
        self.assertEqual(result["status"], "excluded")

    def test_conflicting_evidence_yields_unresolved_not_a_guess(self) -> None:
        observations = [
            self._obs("branch_closed", "directory"),
            self._obs("branch_address_or_existence", "operator_controlled"),
            self._obs("mathematics_subject", "operator_controlled"),
            self._obs("level_overlap", "operator_controlled"),
        ]
        result = evaluate_branch_evidence(observations, analysis_cutoff="2026-09-13")
        self.assertEqual(result["status"], "unresolved")

    def test_no_evidence_at_all_is_unresolved(self) -> None:
        result = evaluate_branch_evidence([], analysis_cutoff="2026-09-13")
        self.assertEqual(result["status"], "unresolved")

    def test_multi_subject_centre_can_still_be_confirmed_on_mathematics_alone(self) -> None:
        # A multi-subject centre's evidence includes non-mathematics subjects too,
        # but only the mathematics + level elements are required for confirmation.
        observations = [
            self._obs("branch_address_or_existence", "operator_controlled"),
            self._obs("mathematics_subject", "operator_controlled"),
            self._obs("level_overlap", "operator_controlled"),
        ]
        result = evaluate_branch_evidence(observations, analysis_cutoff="2026-09-13")
        self.assertEqual(result["status"], "confirmed")


class DedupTests(unittest.TestCase):
    def _candidate(self, candidate_id, brand, address, postal, unit=None):
        return {
            "candidate_id": candidate_id,
            "brand_name": brand,
            "address_raw": address,
            "postal_code": postal,
            "unit": unit,
        }

    def test_exact_duplicate_records_collapse_to_one_branch(self) -> None:
        candidates = [
            self._candidate("c1", "Example Math", "123 Example Rd", "123456", "#01-01"),
            self._candidate("c2", "example math", "123 EXAMPLE RD", "123456", "#01-01"),
        ]
        result = deduplicate_branch_candidates(candidates)
        self.assertEqual(len(result["branches"]), 1)
        self.assertEqual(result["branches"][0]["source_candidate_count"], 2)

    def test_different_units_at_same_postal_remain_separate_branches(self) -> None:
        candidates = [
            self._candidate("c1", "Example Math", "123 Example Rd", "123456", "#01-01"),
            self._candidate("c2", "Example Math", "123 Example Rd", "123456", "#02-02"),
        ]
        result = deduplicate_branch_candidates(candidates)
        self.assertEqual(len(result["branches"]), 2)
        self.assertEqual(result["quality"]["review_queue_count"], 0)

    def test_different_locations_of_same_brand_count_as_separate_branches(self) -> None:
        candidates = [
            self._candidate("c1", "Example Math", "1 Road A", "111111", "#01-01"),
            self._candidate("c2", "Example Math", "2 Road B", "222222", "#01-01"),
        ]
        result = deduplicate_branch_candidates(candidates)
        self.assertEqual(len(result["branches"]), 2)

    def test_missing_and_present_unit_at_same_brand_postal_is_flagged_not_merged(self) -> None:
        candidates = [
            self._candidate("c1", "Example Math", "123 Example Rd", "123456", "#01-01"),
            self._candidate("c2", "Example Math", "123 Example Rd", "123456", None),
        ]
        result = deduplicate_branch_candidates(candidates)
        self.assertEqual(len(result["branches"]), 2)  # not merged
        categories = {item["issue_category"] for item in result["review_queue"]}
        self.assertIn("ambiguous_unit_within_postal", categories)

    def test_blk_variant_and_missing_unit_merge_with_one_supported_canonical_branch(self) -> None:
        candidates = [
            {
                **self._candidate("c1", "Example Math", "818 Woodlands Street 82", None),
                "canonical_address": "818 Woodlands Street 82",
                "canonical_postal_code": "730818",
                "canonical_unit": "#01-419",
            },
            self._candidate("c2", "Example Math", "Blk 818 Woodlands Street 82", None),
        ]
        result = deduplicate_branch_candidates(candidates)
        self.assertEqual(len(result["branches"]), 1)
        self.assertEqual(result["branches"][0]["source_candidate_ids"], ["c1", "c2"])
        self.assertEqual(result["quality"]["candidate_specific_missing_unit_resolution_count"], 1)

    def test_missing_unit_merges_only_when_canonical_identity_is_complete(self) -> None:
        candidates = [
            {
                **self._candidate("c1", "Example Math", "123 Example Road #01-01", None, "#01-01"),
                "canonical_address": "123 Example Road",
                "canonical_postal_code": "123456",
                "canonical_unit": "#01-01",
            },
            self._candidate("c2", "Example Math", "123 Example Road", None),
        ]
        result = deduplicate_branch_candidates(candidates)
        self.assertEqual(len(result["branches"]), 1)
        self.assertEqual(result["branches"][0]["postal_code"], "123456")

    def test_different_known_units_remain_separate_with_canonical_evidence(self) -> None:
        candidates = [
            {
                **self._candidate("c1", "Example Math", "123 Example Road #01-01", "123456", "#01-01"),
                "canonical_address": "123 Example Road",
                "canonical_postal_code": "123456",
                "canonical_unit": "#01-01",
            },
            self._candidate("c2", "Example Math", "123 Example Road #02-02", "123456", "#02-02"),
        ]
        result = deduplicate_branch_candidates(candidates)
        self.assertEqual(len(result["branches"]), 2)

    def test_conflicting_identity_evidence_is_reviewed_not_force_merged(self) -> None:
        candidates = [
            {
                **self._candidate("c1", "Example Math", "123 Example Road #01-01", "123456", "#01-01"),
                "canonical_address": "123 Example Road",
                "canonical_postal_code": "123456",
                "canonical_unit": "#01-01",
            },
            {**self._candidate("c2", "Example Math", "123 Example Road", "123456"), "identity_conflict": True},
        ]
        result = deduplicate_branch_candidates(candidates)
        self.assertEqual(len(result["branches"]), 2)
        self.assertIn("conflicting_identity_evidence", {item["issue_category"] for item in result["review_queue"]})

    def test_missing_postal_code_is_never_geocoded_and_is_flagged(self) -> None:
        candidates = [self._candidate("c1", "Example Math", "123 Example Rd", None)]
        result = deduplicate_branch_candidates(candidates)
        self.assertIsNone(result["branches"][0]["postal_code"])
        categories = {item["issue_category"] for item in result["review_queue"]}
        self.assertIn("missing_or_invalid_postal_code", categories)

    def test_brand_alias_resolves_to_canonical_brand_without_fuzzy_matching(self) -> None:
        candidates = [
            self._candidate("c1", "Example Math (Old Name)", "1 Road A", "111111", "#01-01"),
            self._candidate("c2", "Example Math", "2 Road B", "222222", "#01-01"),
        ]
        alias_map = {"EXAMPLE MATH (OLD NAME)": "EXAMPLE MATH"}
        result = deduplicate_branch_candidates(candidates, brand_alias_to_canonical=alias_map)
        brand_names = {row["normalized_brand_name"] for row in result["branches"]}
        self.assertEqual(brand_names, {"EXAMPLE MATH"})

    def test_candidate_specific_canonical_fields_apply_before_deduplication(self) -> None:
        candidates = [
            {
                **self._candidate("c1", "Example Math", "10 Example Road, Block A #01-01", None, "#01-01"),
                "canonical_address": "10 Example Road",
                "canonical_postal_code": "123456",
                "canonical_unit": "#01-01",
            },
            {
                **self._candidate("c2", "Example Math", "10 Example Rd", "123456", None),
                "canonical_address": "10 Example Road",
                "canonical_postal_code": "123456",
                "canonical_unit": "#01-01",
            },
        ]
        result = deduplicate_branch_candidates(candidates)
        self.assertEqual(len(result["branches"]), 1)
        self.assertEqual(result["branches"][0]["source_candidate_count"], 2)

    def test_known_tim_gan_postal_is_applied_before_deduplication(self) -> None:
        candidate = {
            **self._candidate("c1", "Tim Gan Math", "Blk 201A Tampines St 21 #01-1061", None, "#01-1061"),
            "canonical_address": "201A Tampines Street 21",
            "canonical_postal_code": "521201",
            "canonical_unit": "#01-1061",
        }
        result = deduplicate_branch_candidates([candidate])
        self.assertEqual(result["branches"][0]["postal_code"], "521201")


class CandidateSpecificValidationTests(unittest.TestCase):
    def test_aggregate_attempt_is_diagnostic_not_branch_validation(self) -> None:
        direct, diagnostics = _load_validation_index([
            {"brand_name": "Example", "address_key": "AGGREGATE_ALL_ADDRESSES"},
        ])
        branch = {"normalized_brand_name": "EXAMPLE", "source_candidate_ids": ["OBS1"]}
        self.assertIsNone(_lookup_validation_for_branch(branch, direct))
        self.assertEqual(len(diagnostics["EXAMPLE"]), 1)

    def test_merged_branch_preserves_all_validation_provenance_but_one_coverage_unit(self) -> None:
        first = {"brand_name": "Example", "address_key": "A", "source_observation_ids": ["OBS1"]}
        second = {"brand_name": "Example", "address_key": "B", "source_observation_ids": ["OBS2"]}
        direct, _ = _load_validation_index([first, second])
        branch = {"normalized_brand_name": "EXAMPLE", "source_candidate_ids": ["OBS1", "OBS2"]}
        self.assertEqual(_validations_for_branch(branch, direct), [first, second])
        self.assertIs(_lookup_validation_for_branch(branch, direct), first)

    def test_coordinate_change_changes_run_identity(self) -> None:
        base = [{"branch_id": "B1", "status": "resolved", "longitude_wgs84": 103.8, "latitude_wgs84": 1.3}]
        moved = [{**base[0], "longitude_wgs84": 103.8001}]
        first = compute_run_id(material_input_checksums=["a"], analysis_cutoff="2026-09-13", geocode_decisions=base, geocode_cache_checksum="cache")
        second = compute_run_id(material_input_checksums=["a"], analysis_cutoff="2026-09-13", geocode_decisions=moved, geocode_cache_checksum="cache")
        self.assertNotEqual(first, second)

    def test_validation_ledger_is_loaded_from_the_private_configured_reference(self) -> None:
        root = Path(__file__).resolve().parents[1]
        paths = _config_paths(root)
        self.assertIn("data/interim/competitors/", str(paths["validation_attempts"]))
        self.assertTrue(paths["validation_attempts"].exists())
        self.assertFalse((root / "config/competitors/pilot_validation_attempts.json").exists())

    def test_private_validation_batches_are_candidate_specific_and_dimensioned(self) -> None:
        root = Path(__file__).resolve().parents[1]
        paths = _config_paths(root)
        attempts = json.loads(paths["validation_attempts"].read_text(encoding="utf-8"))["attempts"]
        dimensions = {
            "physical_teaching_address",
            "postal_code_and_unit",
            "current_operation",
            "mathematics_offering",
            "p1_s4_level_coverage",
        }
        for batch_name, expected_count in (("batch-01", 10), ("batch-02", 15), ("batch-03", 15), ("batch-04", 16)):
            batch = json.loads(
                (root / f"data/interim/competitors/validation-batches/{batch_name}.private.json").read_text(encoding="utf-8")
            )
            expected_ids = {source_id for row in batch["candidates"] for source_id in row["source_observation_ids"]}
            batch_attempts = [
                row for row in attempts if set(row.get("source_observation_ids", [])) & expected_ids
            ]
            actual_ids = {source_id for row in batch_attempts for source_id in row["source_observation_ids"]}
            self.assertEqual(batch["status"], "completed")
            self.assertEqual(len(batch["candidates"]), expected_count)
            self.assertEqual(actual_ids, expected_ids)
            self.assertTrue(all(row["address_key"] != "AGGREGATE_ALL_ADDRESSES" for row in batch_attempts))
            self.assertTrue(all(set(row["evidence_dimensions"]) == dimensions for row in batch_attempts))

class BranchVersusBrandCountingTests(unittest.TestCase):
    def test_branch_count_is_not_brand_count(self) -> None:
        branches = [
            {"branch_id": "B1", "brand_id": "BRAND_A", "status": "current"},
            {"branch_id": "B2", "brand_id": "BRAND_A", "status": "current"},
            {"branch_id": "B3", "brand_id": "BRAND_B", "status": "current"},
        ]
        self.assertEqual(count_current_branches(branches), 3)
        self.assertEqual(count_distinct_brands(branches), 2)

    def test_relocated_previous_site_is_not_double_counted(self) -> None:
        previous = {"branch_id": "B1", "brand_id": "BRAND_A", "status": "current"}
        new = {"branch_id": "B2", "brand_id": "BRAND_A", "status": "current"}
        result = record_relocation(previous, new, effective_date_known=True, source_ref="operator_page")
        branches = [result["previous_branch"], result["new_branch"]]
        self.assertEqual(count_current_branches(branches), 1)
        self.assertEqual(result["previous_branch"]["status"], "relocated")
        self.assertEqual(result["new_branch"]["previous_branch_id"], "B1")

    def test_relocation_requires_two_distinct_branch_ids(self) -> None:
        branch = {"branch_id": "B1", "brand_id": "BRAND_A", "status": "current"}
        with self.assertRaises(ValueError):
            record_relocation(branch, branch, effective_date_known=True, source_ref="x")


class BlockedGeocodingResultTests(unittest.TestCase):
    """cli._blocked_geocoding_result: the safe global-blocker -> per-branch mapping."""

    def test_each_onemap_unavailable_category_maps_to_a_distinct_blocked_status(self) -> None:
        geocode_input = [{"branch_id": "B1", "postal_code": "123456"}]
        for category in ("missing_credentials", "authentication", "network", "invalid_auth_response"):
            error = OneMapUnavailable(category, f"safe message for {category}")
            result = _blocked_geocoding_result(error, geocode_input)
            self.assertEqual(result["records"][0]["status"], f"blocked_{category}")
            self.assertEqual(result["source"], "blocked")

    def test_branch_without_postal_code_keeps_accurate_status_even_when_blocked(self) -> None:
        geocode_input = [
            {"branch_id": "B1", "postal_code": "123456"},
            {"branch_id": "B2", "postal_code": None},
        ]
        error = OneMapUnavailable("missing_credentials", "OneMap credentials are unavailable")
        result = _blocked_geocoding_result(error, geocode_input)
        by_id = {row["branch_id"]: row["status"] for row in result["records"]}
        self.assertEqual(by_id["B1"], "blocked_missing_credentials")
        self.assertEqual(by_id["B2"], "missing_postal_code")

    def test_no_credential_or_response_body_value_appears_in_persisted_result(self) -> None:
        geocode_input = [{"branch_id": "B1", "postal_code": "123456"}]
        error = OneMapUnavailable("authentication", "OneMap authentication rejected with HTTP 401")
        result = _blocked_geocoding_result(error, geocode_input)
        serialized = json.dumps(result)
        self.assertNotIn("ONEMAP_EMAIL", serialized)
        self.assertNotIn("PASSWORD", serialized)
        self.assertFalse(result["summary"]["token_persisted"])
        self.assertFalse(result["summary"]["raw_authentication_response_recorded"])
        self.assertFalse(result["summary"]["raw_search_responses_recorded"])


if __name__ == "__main__":
    unittest.main()
