# tests/unit/test_rrf.py
"""Unit tests for services.retrieval.rrf. Pure logic — no database needed."""

from __future__ import annotations

import unittest
import uuid

from services.retrieval.rrf import reciprocal_rank_fusion


class ReciprocalRankFusionTests(unittest.TestCase):
    def test_basic_fusion_formula(self) -> None:
        a, b = uuid.uuid4(), uuid.uuid4()
        result = dict(reciprocal_rank_fusion([[a, b]], k=60))
        self.assertAlmostEqual(result[a], 1 / 61)
        self.assertAlmostEqual(result[b], 1 / 62)

    def test_deduplicates_and_sums_contributions(self) -> None:
        a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        list1 = [a, b]
        list2 = [c, a]  # a also appears here, at rank 2
        result = reciprocal_rank_fusion([list1, list2], k=60)
        result_dict = dict(result)

        self.assertEqual(len(result), 3)  # exactly one entry per chunk_id
        expected_a = 1 / (60 + 1) + 1 / (60 + 2)
        self.assertAlmostEqual(result_dict[a], expected_a)
        self.assertGreater(result_dict[a], 1 / (60 + 1))

    def test_chunk_in_both_lists_outranks_single_list_chunk(self) -> None:
        a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        list1 = [b, a]
        list2 = [b, c]
        result = reciprocal_rank_fusion([list1, list2], k=60)
        ranked_ids = [chunk_id for chunk_id, _ in result]
        self.assertEqual(ranked_ids[0], b)

    def test_results_sorted_descending(self) -> None:
        a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        result = reciprocal_rank_fusion([[a, b, c]], k=60)
        scores = [score for _, score in result]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_configurable_k_changes_scores(self) -> None:
        a = uuid.uuid4()
        result_k60 = dict(reciprocal_rank_fusion([[a]], k=60))
        result_k10 = dict(reciprocal_rank_fusion([[a]], k=10))
        self.assertGreater(result_k10[a], result_k60[a])

    def test_raises_on_non_positive_k(self) -> None:
        a = uuid.uuid4()
        with self.assertRaises(ValueError):
            reciprocal_rank_fusion([[a]], k=0)

    def test_empty_lists_returns_empty(self) -> None:
        self.assertEqual(reciprocal_rank_fusion([]), [])
        self.assertEqual(reciprocal_rank_fusion([[]]), [])